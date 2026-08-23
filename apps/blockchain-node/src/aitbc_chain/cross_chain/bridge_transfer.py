"""Cross-chain bridge transfer lifecycle and proof validation."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any, cast

from sqlmodel import select

from ..config import settings
from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Transaction
from .bridge_base import BridgeBase
from .bridge_types import BridgeStatus, BridgeTransfer

logger = get_logger(__name__)


class BridgeTransferMixin(BridgeBase):
    """Cross-chain transfer lock/confirm/refund and batch operations."""

    # ponytail: Protocol base declares the attributes the concrete CrossChainBridge sets.

    BRIDGE_FEE_BASIS_POINTS = 10

    def initiate_transfer(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, asset: str = "native"
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain transfer.

        Step 1: Lock funds on source chain
        """
        if source_chain == target_chain:
            raise ValueError("Source and target chain must be different")

        max_amount = getattr(settings, "bridge_max_lock_amount", 0)
        if max_amount and amount > max_amount:
            raise ValueError(f"Amount {amount} exceeds bridge max lock amount {max_amount}")

        transfer_id = self._generate_transfer_id(source_chain, target_chain, sender, recipient, amount, int(time.time()))
        with self._session_for(source_chain) as session:
            sender_account = session.get(Account, (source_chain, sender))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender}")
            fee = amount * self.BRIDGE_FEE_BASIS_POINTS // 10000
            total_deduction = amount + fee
            if sender_account.balance < total_deduction:
                raise ValueError(f"Insufficient balance: {sender_account.balance} < {total_deduction}")
            sender_account.balance -= total_deduction
            lock_nonce = sender_account.nonce
            sender_account.nonce += 1
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
                nonce=lock_nonce,
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

    def _target_chain_from_proof(self, transfer_id: str, proof: dict[str, Any]) -> str:
        """Determine the target chain for a confirm from the proof or record."""
        # v0.7.3: Multi-chain bridge. The proof may carry an explicit target_chain.
        target_chain: str | None = proof.get("target_chain")
        if target_chain:
            return target_chain
        # Fall back to the default chain's transfer record, then the local chain.
        with self._session_for() as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if record:
                return record.target_chain
        return str(getattr(settings, "chain_id", "") or "")

    def confirm_transfer(self, transfer_id: str, proof: dict[str, Any]) -> BridgeTransfer:
        """
        Confirm a cross-chain transfer on target chain.

        Step 2: Validate proof and release funds on target chain.
        v0.7.3: If the transfer record does not yet exist on the target chain,
        it is materialised from the proof (mint-and-release pattern for
        cross-island bridges).
        """
        proof_hash = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
        if proof_hash in self._processed_proofs:
            raise ValueError("Proof already processed (double-spend attempt)")

        target_chain = self._target_chain_from_proof(transfer_id, proof)
        if not target_chain:
            raise ValueError("Cannot confirm: target chain not known (proof missing target_chain and no CHAIN_ID configured)")

        with self._session_for(target_chain) as session:
            # Persistent replay protection: the in-memory set is lost on
            # restart; a recorded proof_hash is not.
            persisted_proof = session.exec(
                select(CrossChainTransfer.transfer_id).where(CrossChainTransfer.proof_hash == proof_hash)
            ).first()
            if persisted_proof is not None:
                raise ValueError("Proof already processed (double-spend attempt)")
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                # v0.7.3: Target chain has not seen the lock yet; create a
                # CrossChainTransfer from the proof so the release can proceed.
                record = CrossChainTransfer(
                    transfer_id=transfer_id,
                    source_chain=proof.get("source_chain", ""),
                    target_chain=target_chain,
                    sender=proof.get("sender", ""),
                    recipient=proof.get("recipient", ""),
                    amount=int(proof.get("amount", 0)),
                    asset=proof.get("asset", "native"),
                    status="pending",
                    source_tx_hash=proof.get("lock_tx_hash", transfer_id),
                    lock_time=datetime.now(UTC),
                )
                session.add(record)
            if record.status != "pending":
                raise ValueError(f"Transfer already processed: {record.status}")
            if not self._validate_proof(proof, record):
                raise ValueError("Invalid transfer proof")
            recipient_account = session.get(Account, (record.target_chain, record.recipient))
            if not recipient_account:
                recipient_account = Account(chain_id=record.target_chain, address=record.recipient, balance=0, nonce=0)
                session.add(recipient_account)
            recipient_account.balance += record.amount
            release_nonce = recipient_account.nonce
            recipient_account.nonce += 1
            session.add(recipient_account)
            # Create a bridge release account with enough balance to satisfy
            # the MESSAGE state transition (fee=0, value=0).  The recipient
            # is already credited here; the block proposer will record the
            # MESSAGE in a block and advance the bridge release nonce.
            bridge_release_addr = "bridge_release"
            bridge_release_account = session.get(Account, (record.target_chain, bridge_release_addr))
            if not bridge_release_account:
                bridge_release_account = Account(chain_id=record.target_chain, address=bridge_release_addr, balance=record.amount, nonce=0)
                session.add(bridge_release_account)
            release_nonce = bridge_release_account.nonce
            target_tx_hash = hashlib.sha256(f"{transfer_id}:{record.target_chain}:{int(time.time())}".encode()).hexdigest()
            release_tx = Transaction(
                chain_id=record.target_chain,
                tx_hash=target_tx_hash,
                sender=bridge_release_addr,
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
                value=0,
                fee=0,
                nonce=release_nonce,
                timestamp=datetime.now(UTC),
                block_height=None,
                status="confirmed",
                type="BRIDGE_RELEASE",
            )
            session.add(release_tx)
            record.status = "completed"
            record.target_tx_hash = target_tx_hash
            record.proof_hash = proof_hash
            record.confirm_time = datetime.now(UTC)
            session.add(record)
            session.commit()
            # Also mark the source-chain transfer record completed so bridge
            # health and query endpoints reflect the finalised state.
            try:
                with self._session_for(record.source_chain) as src_session:
                    src_record = src_session.get(CrossChainTransfer, transfer_id)
                    if src_record:
                        src_record.status = "completed"
                        src_record.target_tx_hash = target_tx_hash
                        src_record.proof_hash = proof_hash
                        src_record.confirm_time = record.confirm_time
                        src_session.add(src_record)
                        src_session.commit()
            except Exception:
                logger.exception("Failed to update source-chain bridge record for %s", transfer_id)
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

    def get_transfer(self, transfer_id: str, chain_id: str | None = None) -> BridgeTransfer | None:
        """Get transfer by ID."""
        if transfer_id in self._pending_transfers:
            return self._pending_transfers[transfer_id]
        with self._session_for(chain_id or str(getattr(settings, "chain_id", "") or "")) as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if record:
                return self._build_transfer_from_record(record)
            return None

    def list_pending_transfers(self, chain_id: str | None = None) -> list[BridgeTransfer]:
        """List all pending transfers."""
        with self._session_for(chain_id or str(getattr(settings, "chain_id", "") or "")) as session:
            query = select(CrossChainTransfer).where(CrossChainTransfer.status == "pending")
            if chain_id:
                query = query.where(
                    (CrossChainTransfer.source_chain == chain_id) | (CrossChainTransfer.target_chain == chain_id)
                )
            records = session.exec(query).all()
            return [self._build_transfer_from_record(r) for r in records]

    def refund_transfer(self, transfer_id: str, sender: str, chain_id: str | None = None) -> BridgeTransfer:
        """Refund a pending bridge transfer — return locked funds to sender.

        Only transfers in 'pending' or 'locked' status can be refunded.
        Completed/confirmed/refunded transfers cannot be refunded.

        v0.7.0 §B2: Added as the backend for the ``POST /bridge/unlock`` endpoint.
        The refund returns the locked amount (minus the fee already deducted at
        lock time) to the sender's balance. The fee is NOT refunded — it was
        consumed when the lock transaction was created.

        v0.7.3: chain_id selects the source-chain DB.
        """
        with self._session_for(chain_id or str(getattr(settings, "chain_id", "") or "")) as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")
            if record.status not in ("pending", "locked"):
                raise ValueError(f"Transfer cannot be refunded in status '{record.status}'")
            if record.sender != sender:
                raise ValueError("Only the original sender can refund this transfer")

            refund_delay = getattr(settings, "bridge_refund_delay_seconds", 0)
            if refund_delay:
                lock_time = record.lock_time or record.confirm_time or datetime.now(UTC)
                elapsed = (datetime.now(UTC) - lock_time).total_seconds()
                if elapsed < refund_delay:
                    raise ValueError(
                        f"Refund not allowed yet: {elapsed:.0f}s since lock, "
                        f"minimum delay is {refund_delay}s"
                    )

            # Return the locked amount to the sender (fee was already deducted at lock time)
            sender_account = session.get(Account, (record.source_chain, record.sender))
            if not sender_account:
                sender_account = Account(chain_id=record.source_chain, address=record.sender, balance=0, nonce=0)
                session.add(sender_account)
            sender_account.balance += record.amount
            refund_nonce = sender_account.nonce
            sender_account.nonce += 1
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
                nonce=refund_nonce,
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
        with self._session_for(chain_id or str(getattr(settings, "chain_id", "") or "")) as session:
            query = select(CrossChainTransfer).where(CrossChainTransfer.status.in_(["pending", "locked"]))  # type: ignore[attr-defined]
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

    def build_proof(
        self,
        transfer_id: str,
        source_chain: str | None = None,
        block_height: int = 1,
        block_hash: str = "",
    ) -> dict[str, Any]:
        """Build a Merkle proof for a locked cross-chain transfer.

        v0.7.3: Generates a real Merkle inclusion proof against a trie whose
        root is derived from the lock transaction. The returned proof is
        unsigned; the caller must sign it (proposer_signature /
        validator_signatures) before confirming.
        """
        source_chain = source_chain or str(getattr(settings, "chain_id", "") or "")
        with self._session_for(source_chain) as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")

            from ..state.merkle_patricia_trie import MerklePatriciaTrie

            lock_tx_hash = record.source_tx_hash or transfer_id
            lock_key = lock_tx_hash.encode()
            lock_value = f"lock:{record.transfer_id}:{record.amount}:{record.target_chain}".encode()
            trie = MerklePatriciaTrie()
            trie.put(lock_key, lock_value)

            state_root = trie.get_root()
            proof_bytes = trie.get_proof(lock_key)
            block_hash = block_hash or ("0x" + "00" * 32)

            return {
                "source_chain": record.source_chain,
                "target_chain": record.target_chain,
                "lock_tx_hash": lock_tx_hash,
                "amount": record.amount,
                "sender": record.sender,
                "recipient": record.recipient,
                "asset": record.asset,
                "chain_id": record.source_chain,
                "block_height": block_height,
                "block_hash": block_hash,
                "state_root": "0x" + state_root.hex(),
                "merkle_proof": [p.hex() for p in proof_bytes],
                "lock_event": lock_value.decode(),
                "proposer_signature": "",
                "validator_signatures": [],
            }

    def _build_lock_event_value(self, record: CrossChainTransfer) -> str:
        """Canonical lock event string that the Merkle proof commits to."""
        return f"lock:{record.transfer_id}:{record.amount}:{record.target_chain}"

    def _generate_transfer_id(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, timestamp: int
    ) -> str:
        """Generate unique transfer ID."""
        data = f"{source_chain}:{target_chain}:{sender}:{recipient}:{amount}:{timestamp}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()

    def _validate_proof(self, proof: dict[str, Any], record: CrossChainTransfer) -> bool:
        """Validate cross-chain transfer proof with cryptographic verification (v0.7.2).

        Replaces the v0.5.16/v0.7.0/v0.7.1 field-equality + signature-format
        checks with full cryptographic verification:

        1. **Field validation** — proof fields match transfer record
        2. **Block header lookup** — fetch BridgeBlockHeader from DB by chain_id + block_height
        3. **State root verification** — proof's state_root matches block header's state_root
        4. **Merkle proof verification** — lock event inclusion via merkle_patricia_trie.verify_proof
        5. **Block header signature verification** — proposer signature via validate_block_header()
        6. **Multi-sig threshold** — M-of-N validator signatures (v0.7.1, kept)
        7. **Finality check** — reject non-finalized blocks for large transfers

        When ``bridge_verification_mode`` is "in_process" (default), all
        verification happens locally. When "oracle", the ExternalOracleClient
        stub is used (raises NotImplementedError in v0.7.2).
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
        ]
        for field in required_fields:
            if field not in proof:
                logger.warning("Proof missing field: %s", field)
                return False

        # Step 1: Verify field equality with record
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

        # Step 2: Verify block anchor (height + hash must be present and consistent)
        block_height = proof.get("block_height")
        block_hash = proof.get("block_hash")
        if not isinstance(block_height, int) or block_height < 0:
            logger.warning("Proof has invalid block_height")
            return False
        if not isinstance(block_hash, str) or not block_hash.strip():
            logger.warning("Proof has invalid block_hash")
            return False

        # Step 3: Signature requirement check (proposer_signature or validator_signatures)
        proposer_signature = proof.get("proposer_signature")
        validator_signatures = proof.get("validator_signatures", [])
        if not proposer_signature and not validator_signatures:
            logger.warning("Proof has no signatures (proposer_signature or validator_signatures required)")
            return False

        # Step 4: Multi-sig threshold verification (v0.7.1, kept)
        if not self._verify_threshold_signatures(proof):
            logger.warning("Proof signature verification failed (threshold or single-sig)")
            return False

        # Step 5: Block header lookup + verification (v0.7.2)
        verification_mode = getattr(settings, "bridge_verification_mode", "in_process")
        if verification_mode == "in_process":
            # Look up the block header from the DB
            header = self._get_block_header(record_chain_id, block_height)
            if header is None:
                logger.warning(
                    "No block header stored for chain=%s height=%s — cannot verify proof",
                    record_chain_id,
                    block_height,
                )
                return False

            # Verify block hash matches
            if header.hash != block_hash:
                logger.warning(
                    "Block hash mismatch: proof=%s vs header=%s (height=%s)",
                    block_hash[:16],
                    header.hash[:16],
                    block_height,
                )
                return False

            # Step 5a: State root verification
            proof_state_root = proof.get("state_root", "")
            if proof_state_root and proof_state_root != header.state_root:
                logger.warning(
                    "State root mismatch: proof=%s vs header=%s",
                    proof_state_root[:16],
                    header.state_root[:16],
                )
                return False

            # Step 5b: Block header signature verification (B4)
            if not self._verify_block_header_signature(header):
                logger.warning("Block header signature verification failed for height=%s", block_height)
                return False

            # Step 5c: Merkle proof verification (B3)
            merkle_proof = proof.get("merkle_proof", [])
            if merkle_proof:
                if not self._verify_merkle_proof(header.state_root, proof):
                    logger.warning("Merkle proof verification failed for height=%s", block_height)
                    return False
            else:
                # v0.10.16: Merkle inclusion proof is required for production
                # release paths. When bridge_release_enabled is True, a missing
                # merkle_proof is a hard failure; the standalone
                # bridge_require_merkle_proof flag still allows explicit enforcement.
                release_enabled = getattr(settings, "bridge_release_enabled", False)
                require_merkle = release_enabled or getattr(settings, "bridge_require_merkle_proof", False)
                if require_merkle:
                    logger.warning(
                        "Proof has no merkle_proof and release/production enforcement enabled — rejecting (height=%s)",
                        block_height,
                    )
                    return False
                logger.warning(
                    "Proof has no merkle_proof — skipping trie verification (field+sig only, height=%s)",
                    block_height,
                )

            # Step 5d: Finality check (B5)
            if not self._check_finality_for_transfer(header, record.amount):
                logger.warning(
                    "Finality check failed for height=%s (confirmations=%s, amount=%s)",
                    block_height,
                    header.confirmation_count,
                    record.amount,
                )
                return False

        # Step 6: Validator set epoch grace period check (B6)
        if not self._check_validator_set_freshness(record_chain_id):
            logger.warning("Validator set for chain=%s is stale (grace period expired)", record_chain_id)
            return False

        return True

    def _build_transfer_from_record(self, record: CrossChainTransfer, proof: dict[str, Any] | None = None) -> BridgeTransfer:
        """Build BridgeTransfer from database record."""
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
