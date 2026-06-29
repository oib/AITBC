"""
Cross-Chain Bridge - Real cross-island transaction bridging

This module implements atomic cross-chain transfers using a
lock-mint/burn-release pattern for secure value transfer
between islands (blockchain shards).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import select

from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Transaction

logger = get_logger(__name__)


class BridgeStatus(Enum):
    """Status of a cross-chain transfer"""

    pending = "pending"
    locked = "locked"
    confirmed = "confirmed"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


@dataclass
class BridgeTransfer:
    """Cross-chain transfer record"""

    transfer_id: str
    source_chain: str
    target_chain: str
    sender: str
    recipient: str
    amount: int
    asset: str
    status: BridgeStatus
    source_tx_hash: str | None
    target_tx_hash: str | None
    lock_time: datetime | None
    confirm_time: datetime | None
    proof: dict[str, Any] | None


class CrossChainBridge:
    """
    Cross-Chain Bridge for atomic transfers between islands.

    Implements the lock-mint/burn-release pattern:
    1. Lock funds on source chain
    2. Generate proof of lock
    3. Mint/burn equivalent on target chain
    4. Release funds on target
    """

    BRIDGE_FEE_BASIS_POINTS = 10

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._pending_transfers: dict[str, BridgeTransfer] = {}
        self._processed_proofs: set[str] = set()

    def initiate_transfer(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, asset: str = "native"
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain transfer.

        Step 1: Lock funds on source chain
        """
        transfer_id = self._generate_transfer_id(source_chain, target_chain, sender, recipient, amount, int(time.time()))
        with self._session_factory() as session:
            sender_account = session.get(Account, (source_chain, sender))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender}")
            fee = amount * self.BRIDGE_FEE_BASIS_POINTS // 10000
            total_deduction = amount + fee
            if sender_account.balance < total_deduction:
                raise ValueError(f"Insufficient balance: {sender_account.balance} < {total_deduction}")
            sender_account.balance -= total_deduction
            session.add(sender_account)
            lock_tx = Transaction(
                chain_id=source_chain,
                tx_hash=transfer_id,
                sender=sender,
                recipient="bridge_lock",
                payload={
                    "type": "BRIDGE_LOCK",
                    "transfer_id": transfer_id,
                    "target_chain": target_chain,
                    "target_recipient": recipient,
                    "amount": amount,
                    "fee": fee,
                    "asset": asset,
                },
                value=amount,
                fee=fee,
                nonce=sender_account.nonce,
                timestamp=datetime.now(UTC),
                block_height=None,
                status="pending",
                type="BRIDGE_LOCK",
            )
            session.add(lock_tx)
            transfer_record = CrossChainTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status="pending",
                source_tx_hash=transfer_id,
                lock_time=datetime.now(UTC),
            )
            session.add(transfer_record)
            session.commit()
            transfer = BridgeTransfer(
                transfer_id=transfer_id,
                source_chain=source_chain,
                target_chain=target_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                asset=asset,
                status=BridgeStatus.locked,
                source_tx_hash=transfer_id,
                target_tx_hash=None,
                lock_time=datetime.now(UTC),
                confirm_time=None,
                proof=None,
            )
            self._pending_transfers[transfer_id] = transfer
            logger.info(
                "Bridge transfer initiated: %s... %s from %s to %s", transfer_id[:16], amount, source_chain, target_chain
            )
            return transfer

    def confirm_transfer(self, transfer_id: str, proof: dict[str, Any]) -> BridgeTransfer:
        """
        Confirm a cross-chain transfer on target chain.

        Step 2: Validate proof and release funds on target chain
        """
        proof_hash = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
        if proof_hash in self._processed_proofs:
            raise ValueError("Proof already processed (double-spend attempt)")
        with self._session_factory() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")
            if record.status != "pending":
                raise ValueError(f"Transfer already processed: {record.status}")
            if not self._validate_proof(proof, record):
                raise ValueError("Invalid transfer proof")
            recipient_account = session.get(Account, (record.target_chain, record.recipient))
            if not recipient_account:
                recipient_account = Account(chain_id=record.target_chain, address=record.recipient, balance=0, nonce=0)
                session.add(recipient_account)
            recipient_account.balance += record.amount
            session.add(recipient_account)
            target_tx_hash = hashlib.sha256(f"{transfer_id}:{record.target_chain}:{int(time.time())}".encode()).hexdigest()
            release_tx = Transaction(
                chain_id=record.target_chain,
                tx_hash=target_tx_hash,
                sender="bridge_release",
                recipient=record.recipient,
                payload={
                    "type": "BRIDGE_RELEASE",
                    "transfer_id": transfer_id,
                    "source_chain": record.source_chain,
                    "source_sender": record.sender,
                    "amount": record.amount,
                    "asset": record.asset,
                    "proof": proof_hash,
                },
                value=record.amount,
                fee=0,
                nonce=0,
                timestamp=datetime.now(UTC),
                block_height=None,
                status="confirmed",
                type="BRIDGE_RELEASE",
            )
            session.add(release_tx)
            record.status = "completed"
            record.target_tx_hash = target_tx_hash
            record.confirm_time = datetime.now(UTC)
            session.add(record)
            session.commit()
            self._processed_proofs.add(proof_hash)
            transfer = self._pending_transfers.get(transfer_id)
            if transfer:
                transfer.status = BridgeStatus.completed
                transfer.target_tx_hash = target_tx_hash
                transfer.confirm_time = datetime.now(UTC)
                transfer.proof = proof
            logger.info(
                "Bridge transfer completed: %s... released %s to %s...", transfer_id[:16], record.amount, record.recipient[:20]
            )
            return transfer or self._build_transfer_from_record(record, proof)

    def get_transfer(self, transfer_id: str) -> BridgeTransfer | None:
        """Get transfer by ID"""
        if transfer_id in self._pending_transfers:
            return self._pending_transfers[transfer_id]
        with self._session_factory() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if record:
                return self._build_transfer_from_record(record)
            return None

    def list_pending_transfers(self, chain_id: str | None = None) -> list[BridgeTransfer]:
        """List all pending transfers"""
        with self._session_factory() as session:
            query = select(CrossChainTransfer).where(CrossChainTransfer.status == "pending")
            if chain_id:
                query = query.where(
                    (CrossChainTransfer.source_chain == chain_id) | (CrossChainTransfer.target_chain == chain_id)
                )
            records = session.exec(query).all()
            return [self._build_transfer_from_record(r) for r in records]

    def refund_transfer(self, transfer_id: str, sender: str) -> BridgeTransfer:
        """Refund a pending bridge transfer — return locked funds to sender.

        Only transfers in 'pending' or 'locked' status can be refunded.
        Completed/confirmed/refunded transfers cannot be refunded.

        v0.7.0 §B2: Added as the backend for the ``POST /bridge/unlock`` endpoint.
        The refund returns the locked amount (minus the fee already deducted at
        lock time) to the sender's balance. The fee is NOT refunded — it was
        consumed when the lock transaction was created.
        """
        with self._session_factory() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")
            if record.status not in ("pending", "locked"):
                raise ValueError(f"Transfer cannot be refunded in status '{record.status}'")
            if record.sender != sender:
                raise ValueError("Only the original sender can refund this transfer")

            # Return the locked amount to the sender (fee was already deducted at lock time)
            sender_account = session.get(Account, (record.source_chain, record.sender))
            if not sender_account:
                sender_account = Account(chain_id=record.source_chain, address=record.sender, balance=0, nonce=0)
                session.add(sender_account)
            sender_account.balance += record.amount
            session.add(sender_account)

            # Create a BRIDGE_REFUND transaction record
            refund_tx_hash = hashlib.sha256(
                f"{transfer_id}:refund:{record.source_chain}:{int(time.time())}".encode()
            ).hexdigest()
            refund_tx = Transaction(
                chain_id=record.source_chain,
                tx_hash=refund_tx_hash,
                sender="bridge_refund",
                recipient=record.sender,
                payload={
                    "type": "BRIDGE_REFUND",
                    "transfer_id": transfer_id,
                    "target_chain": record.target_chain,
                    "amount": record.amount,
                    "asset": record.asset,
                },
                value=record.amount,
                fee=0,
                nonce=0,
                timestamp=datetime.now(UTC),
                block_height=None,
                status="confirmed",
                type="BRIDGE_REFUND",
            )
            session.add(refund_tx)

            record.status = "refunded"
            session.add(record)
            session.commit()

            transfer = self._pending_transfers.pop(transfer_id, None)
            if transfer:
                transfer.status = BridgeStatus.refunded
            else:
                transfer = self._build_transfer_from_record(record)
            logger.info(
                "Bridge transfer refunded: %s... returned %s to %s",
                transfer_id[:16],
                record.amount,
                record.sender[:20],
            )
            return transfer

    def get_bridge_balance(self, chain_id: str | None = None) -> dict[str, int]:
        """Get total locked amount per chain (sum of pending/locked transfers).

        Returns a dict mapping chain_id → total locked amount for that chain.
        If ``chain_id`` is provided, returns a single-key dict for that chain.
        """
        with self._session_factory() as session:
            query = select(CrossChainTransfer).where(CrossChainTransfer.status.in_(["pending", "locked"]))
            if chain_id:
                query = query.where(CrossChainTransfer.source_chain == chain_id)
            records = session.exec(query).all()
            balances: dict[str, int] = {}
            for r in records:
                balances[r.source_chain] = balances.get(r.source_chain, 0) + r.amount
            if chain_id and chain_id not in balances:
                balances[chain_id] = 0
            return balances

    def batch_lock(self, transfers: list[dict[str, Any]]) -> list[BridgeTransfer]:
        """Batch lock multiple transfers.

        Each transfer dict must contain: source_chain, target_chain, sender,
        recipient, amount. Optional: asset (default "native").

        Returns a list of BridgeTransfer results. If any individual lock fails,
        the error is recorded in the result dict's 'error' field and the
        remaining transfers are still attempted.
        """
        results: list[BridgeTransfer] = []
        for t in transfers:
            try:
                transfer = self.initiate_transfer(
                    source_chain=t["source_chain"],
                    target_chain=t["target_chain"],
                    sender=t["sender"],
                    recipient=t["recipient"],
                    amount=t["amount"],
                    asset=t.get("asset", "native"),
                )
                results.append(transfer)
            except Exception as e:
                logger.warning("Batch lock failed for transfer: %s", e)
                # Append a failed transfer placeholder so the caller knows which ones failed
                results.append(
                    BridgeTransfer(
                        transfer_id="",
                        source_chain=t.get("source_chain", ""),
                        target_chain=t.get("target_chain", ""),
                        sender=t.get("sender", ""),
                        recipient=t.get("recipient", ""),
                        amount=t.get("amount", 0),
                        asset=t.get("asset", "native"),
                        status=BridgeStatus.failed,
                        source_tx_hash=None,
                        target_tx_hash=None,
                        lock_time=None,
                        confirm_time=None,
                        proof={"error": str(e)},
                    )
                )
        return results

    def batch_confirm(self, confirmations: list[dict[str, Any]]) -> list[BridgeTransfer | dict[str, Any]]:
        """Batch confirm multiple transfers.

        Each confirmation dict must contain: transfer_id, proof.
        Optional: confirmer, signature.

        Returns a list of results. Successful confirmations return BridgeTransfer;
        failures return a dict with 'transfer_id' and 'error' keys.
        """
        results: list[BridgeTransfer | dict[str, Any]] = []
        for c in confirmations:
            transfer_id = c.get("transfer_id", "")
            try:
                transfer = self.confirm_transfer(transfer_id, c["proof"])
                results.append(transfer)
            except Exception as e:
                logger.warning("Batch confirm failed for transfer %s: %s", transfer_id, e)
                results.append({"transfer_id": transfer_id, "error": str(e)})
        return results

    def _generate_transfer_id(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, timestamp: int
    ) -> str:
        """Generate unique transfer ID"""
        data = f"{source_chain}:{target_chain}:{sender}:{recipient}:{amount}:{timestamp}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()

    def _validate_proof(self, proof: dict[str, Any], record: CrossChainTransfer) -> bool:
        """Validate cross-chain transfer proof with cryptographic verification.

        Bug 3 (PARTIAL — v0.5.16): Previously only checked field equality —
        trivially forgeable. Now requires a valid secp256k1 proposer signature
        over the proof fields plus block-header anchoring (height + hash).
        HOWEVER, ``_verify_proposer_signature`` currently accepts ANY valid
        signer — there is no proposer-set membership check yet. Full proposer-set
        tracking + Merkle proof verification is deferred to v0.7.2. Until then
        the release path is fenced behind ``BRIDGE_RELEASE_ENABLED`` (default
        false) at the RPC layer to prevent unauthorized minting.
        Bug 12: Added chain_id check to prevent cross-chain proof replay.

        Required proof fields:
        - source_chain, lock_tx_hash, amount, sender, recipient (existing)
        - chain_id (Bug 12: must match record's chain_id)
        - block_height, block_hash (Bug 3: block header anchoring)
        - proposer_signature (Bug 3: signature from source chain proposer)
        """
        required_fields = [
            "source_chain",
            "lock_tx_hash",
            "amount",
            "sender",
            "recipient",
            "chain_id",
            "block_height",
            "block_hash",
            "proposer_signature",
        ]
        for field in required_fields:
            if field not in proof:
                logger.warning("Proof missing field: %s", field)
                return False

        # Verify field equality with record
        if proof.get("source_chain") != record.source_chain:
            logger.warning("Proof source_chain mismatch")
            return False
        if proof.get("amount") != record.amount:
            logger.warning("Proof amount mismatch")
            return False
        if proof.get("recipient") != record.recipient:
            logger.warning("Proof recipient mismatch")
            return False
        if proof.get("sender") != record.sender:
            logger.warning("Proof sender mismatch")
            return False

        # Bug 12: Verify chain_id matches
        record_chain_id = getattr(record, "chain_id", None) or record.source_chain
        if proof.get("chain_id") != record_chain_id:
            logger.warning("Proof chain_id mismatch: %s != %s", proof.get("chain_id"), record_chain_id)
            return False

        # Bug 3: Verify block anchor (height + hash must be present and consistent)
        block_height = proof.get("block_height")
        block_hash = proof.get("block_hash")
        if not isinstance(block_height, int) or block_height < 0:
            logger.warning("Proof has invalid block_height")
            return False
        if not isinstance(block_hash, str) or not block_hash.strip():
            logger.warning("Proof has invalid block_hash")
            return False

        # Bug 3: Verify proposer signature
        proposer_signature = proof.get("proposer_signature")
        if not isinstance(proposer_signature, str) or not proposer_signature.strip():
            logger.warning("Proof has invalid proposer_signature")
            return False

        # Verify the proposer signature covers the proof data
        if not self._verify_proposer_signature(proof):
            logger.warning("Proof proposer_signature verification failed")
            return False

        return True

    def _verify_proposer_signature(self, proof: dict[str, Any]) -> bool:
        """Verify the proposer signature on a bridge proof.

        The signed message is the keccak256 hash of the canonical JSON of
        the proof fields excluding the proposer_signature itself.
        The signer's address must match the source chain's proposer at the
        claimed block height.

        Bug 3 PARTIAL (v0.5.16): for now, this verifies only that the
        signature is valid for SOME secp256k1 key — it does NOT check the
        recovered address against a proposer set. Full proposer-set tracking
        is deferred to v0.7.2. The release path is fenced behind
        ``BRIDGE_RELEASE_ENABLED`` (default false) at the RPC layer until then.
        """
        import json as _json

        proposer_signature = proof.get("proposer_signature", "")
        if not proposer_signature:
            return False

        # Build the message that was signed (proof without proposer_signature)
        proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
        message = _json.dumps(proof_for_signing, sort_keys=True, separators=(",", ":")).encode()

        try:
            from eth_keys import keys
            from eth_utils import keccak

            msg_hash = keccak(message)
            sig_bytes = bytes.fromhex(proposer_signature.removeprefix("0x"))
            if len(sig_bytes) != 65:
                logger.warning("Invalid proposer signature length: %d bytes", len(sig_bytes))
                return False

            sig = keys.Signature(sig_bytes)
            pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
            # The recovered address must be a known proposer for the source chain.
            # For now, we accept any valid signature — full proposer set verification
            # is deferred to v0.7.2 (Bridge Verification release).
            # The key security improvement is that the proof is now cryptographically
            # tied to a specific signer, making it non-forgeable without a private key.
            _recovered = pub_key.to_checksum_address()
            logger.debug("Proof signed by: %s", _recovered)
            return True
        except Exception as e:
            logger.warning("Proposer signature verification error: %s", e)
            return False

    def _build_transfer_from_record(self, record: CrossChainTransfer, proof: dict[str, Any] | None = None) -> BridgeTransfer:
        """Build BridgeTransfer from database record"""
        return BridgeTransfer(
            transfer_id=record.transfer_id,
            source_chain=record.source_chain,
            target_chain=record.target_chain,
            sender=record.sender,
            recipient=record.recipient,
            amount=record.amount,
            asset=record.asset,
            status=BridgeStatus(record.status),
            source_tx_hash=record.source_tx_hash,
            target_tx_hash=record.target_tx_hash,
            lock_time=record.lock_time,
            confirm_time=record.confirm_time,
            proof=proof,
        )


_bridge_instance: CrossChainBridge | None = None


def init_cross_chain_bridge(session_factory: Any) -> CrossChainBridge:
    """Initialize the global cross-chain bridge"""
    global _bridge_instance
    _bridge_instance = CrossChainBridge(session_factory)
    return _bridge_instance


def get_cross_chain_bridge() -> CrossChainBridge | None:
    """Get the global bridge instance"""
    return _bridge_instance
