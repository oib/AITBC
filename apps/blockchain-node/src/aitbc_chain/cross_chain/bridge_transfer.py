"""Cross-chain bridge transfer lifecycle and proof validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import raiseload
from sqlmodel import select

from aitbc.utils.env import is_production

from ..config import settings
from ..logger import get_logger
from ..models import Account, Block, BridgeBlockHeader, CrossChainTransfer, Transaction
from ..state.bridge_credit import (
    BRIDGE_SIGNATURE_FIELD,
    bridge_credit_private_key,
    sign_bridge_credit,
    sign_bridge_lock,
)
from .bridge_base import BridgeBase
from .bridge_leaf import lock_leaf_v2_active, lock_leaf_value, unknown_lock_leaf
from .bridge_types import BRIDGE_LOCKS_PAUSED_DETAIL, BridgeLocksPausedError, BridgeStatus, BridgeTransfer

logger = get_logger(__name__)


class BridgeTransferMixin(BridgeBase):
    """Cross-chain transfer lock/confirm/refund and batch operations."""

    # Protocol base declares the attributes the concrete CrossChainBridge sets.

    BRIDGE_FEE_BASIS_POINTS = 10

    def _enforce_lock_cap(self, amount: int) -> None:
        """Per-lock cap gate for ``initiate_transfer``.

        Fail-closed (BR-3): when locks are enabled and
        ``bridge_max_lock_amount`` is unset or 0 on a production node
        (``ENVIRONMENT``/``APP_ENV``/``NODE_ENV``), the lock is refused with
        an explicit error and a clear log line — an uncapped production node
        can never lock by accident. Development and test environments keep
        the historical "0 = unlimited" behaviour. With a positive cap the
        over-cap lock is refused in every environment.
        """
        max_amount = getattr(settings, "bridge_max_lock_amount", 0)
        if not max_amount:
            if is_production():
                logger.error(
                    "bridge lock refused: BRIDGE_MAX_LOCK_AMOUNT is unset or 0 "
                    "while locks are enabled in production (fail-closed)"
                )
                raise ValueError(
                    "Bridge locks refused: BRIDGE_MAX_LOCK_AMOUNT is unset or 0; "
                    "production nodes must set an explicit per-lock cap"
                )
            return
        if amount > max_amount:
            raise ValueError(f"Amount {amount} exceeds bridge max lock amount {max_amount}")

    def _enforce_signing_key(self, source_chain: str) -> None:
        """BRIDGE-INTAKE-KEY-1 (#675): admission gate on the release-signing key.

        A lock admitted on a host whose process cannot sign emits a
        signature-less ``BRIDGE_LOCK`` that drains-and-skips at apply
        (v9+) and can never sign the ``BRIDGE_RELEASE`` credit
        (v5+) — the Lock-A/Lock-B incidents: the intake looks accepted
        and the transfer silently stalls at release time. Check the key
        *before* any funds move: warn loudly everywhere, refuse the lock
        outright in production (same fail-closed posture as
        ``_enforce_lock_cap`` — a misdirected production intake must fail
        fast instead of vanishing). Development/test environments keep
        the warn-and-proceed behaviour so key-less single-node setups
        still work below the signature heights.

        When an authority is configured (``bridge_release_authority`` /
        ``BRIDGE_RELEASE_AUTHORITY``, falling back to the escrow
        settlement address), the configured key must also derive to that
        address — a wrong key fails validation identically to a missing
        one.
        """
        key = bridge_credit_private_key()
        if key:
            from aitbc.crypto.signature_recovery import canonical_address

            from ..state.bridge_credit import bridge_release_authority_env

            authority = bridge_release_authority_env()
            if authority:
                try:
                    from aitbc.crypto.crypto import derive_ethereum_address

                    derived = canonical_address(derive_ethereum_address(key))
                except Exception as e:
                    logger.warning(
                        "bridge lock on %s: could not derive address from the configured release signing key (%s); "
                        "the BRIDGE_LOCK/BRIDGE_RELEASE signatures may fail validation",
                        source_chain,
                        e,
                    )
                    return
                if derived != authority:
                    msg = (
                        f"bridge lock refused on {source_chain}: the configured release signing key derives to "
                        f"{derived}, not the bridge release authority {authority} "
                        "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY mismatch); "
                        "locks admitted here would fail signature validation downstream"
                    )
                    if is_production():
                        logger.error(msg)
                        raise ValueError(msg)
                    logger.warning("%s — proceeding anyway (non-production)", msg)
            return
        msg = (
            f"bridge lock on {source_chain}: this process holds no bridge release signing key "
            "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); the BRIDGE_LOCK is emitted "
            "unsigned and the release credit can never be signed — the transfer will drain-and-skip "
            "at apply and stall at release time"
        )
        if is_production():
            logger.error("%s — refusing the lock (fail-closed)", msg)
            raise ValueError(
                "Bridge locks refused: no release signing key configured "
                "(BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                "this node cannot sign the release for admitted locks"
            )
        logger.warning("%s — proceeding anyway (non-production)", msg)

    def _sign_bridge_credit(self, credit: dict[str, Any], tx_hash: str, payload: dict[str, Any] | None = None) -> None:
        """Attach the bridge authority signature to an issued credit (in place).

        Pre-registered ``Transaction`` rows keep it inside ``payload`` (the row
        has no signature column); flat mempool dicts carry it at top level.
        Consensus verifies it against the ``bridge_release_authority`` chain
        parameter from v5 — a credit issued with no signing key configured
        still records, but will be rejected once v5 is active.
        """
        key = bridge_credit_private_key()
        if not key:
            logger.warning(
                "bridge credit issued without a signing key (BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                "it will fail v5+ validation"
            )
            return
        signature = sign_bridge_credit(credit, tx_hash, key)
        if payload is not None:
            payload[BRIDGE_SIGNATURE_FIELD] = signature
        else:
            credit[BRIDGE_SIGNATURE_FIELD] = signature

    def initiate_transfer(
        self,
        source_chain: str,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        asset: str = "native",
        release_amount: int | None = None,
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain transfer.

        Step 1: Lock funds on source chain

        ``release_amount`` optionally overrides the amount credited on the
        target chain (GAP-47 cross-chain swaps quote a converted amount).
        ``None`` releases the locked amount — the plain bridge behavior.
        """
        # Pause gate — the single chokepoint every lock request funnels
        # through (/bridge/lock, /swap, /cross-chain/bridge). Raising here
        # rather than only in the routes
        # covers internal callers too: while paused no new BRIDGE_LOCK
        # envelope is signed, so no valid lock can reach the mempool —
        # nothing downstream needs to refuse it for the pause to hold.
        if getattr(settings, "bridge_locks_paused", False):
            raise BridgeLocksPausedError(BRIDGE_LOCKS_PAUSED_DETAIL)
        if source_chain == target_chain:
            raise ValueError("Source and target chain must be different")
        if release_amount is not None and release_amount < 0:
            raise ValueError("release_amount must be non-negative")

        self._enforce_lock_cap(amount)

        # BRIDGE-INTAKE-KEY-1 (#675): refuse/warn before any funds move when
        # this process cannot sign the lock (v9) or the release credit (v5).
        self._enforce_signing_key(source_chain)

        # v0.24.1: bridge locks must be initiated on the node that produces
        # the source chain. Initiating a lock on a follower would update the
        # local follower DB, which is then overwritten by the next state sync
        # from the producer, producing state-root mismatches and unlocked
        # source funds.  Single-node tests do not set a default peer, so the
        # guard is skipped when there is no upstream RPC to follow.
        has_peer = bool(getattr(settings, "default_peer_rpc_url", None))
        if has_peer:
            local_chains = [
                c.strip() for c in (getattr(settings, "block_production_chains", "") or "").split(",") if c.strip()
            ]
            if source_chain not in local_chains:
                raise ValueError(
                    f"Source chain {source_chain} is not produced by this node; initiate the lock on the source chain producer"
                )

        transfer_id = self._generate_transfer_id(source_chain, target_chain, sender, recipient, amount, int(time.time()))
        with self._session_for(source_chain) as session:
            sender_account = session.get(Account, (source_chain, sender))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender}")
            fee = amount * self.BRIDGE_FEE_BASIS_POINTS // 10000
            total_deduction = amount + fee
            if sender_account.balance < total_deduction:
                raise ValueError(f"Insufficient balance: {sender_account.balance} < {total_deduction}")
            lock_nonce = sender_account.nonce
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            if not block_scoped:
                sender_account.balance -= total_deduction
                sender_account.nonce += 1
                session.add(sender_account)

            # v0.7.3: put the bridge lock in the mempool so the next block
            # produced by this node will include it and anchor the event in a
            # real block header.
            from ..mempool import get_mempool

            timestamp = datetime.now(UTC)
            # v9: the lock carries the bridge authority's signature over its
            # semantic fields (state/bridge_credit.py) — a forged lock was a
            # theft of the target-chain credit. `chain_id` travels inside the
            # body because the signed message binds source_chain from it; the
            # pre-registered row's chain_id column produces the same field.
            lock_body = {
                "from": sender,
                "to": "bridge_lock",
                "amount": amount,
                "fee": fee,
                "type": "BRIDGE_LOCK",
                "transfer_id": transfer_id,
                "target_chain": target_chain,
                "target_recipient": recipient,
                "asset": asset,
                "nonce": lock_nonce,
                "chain_id": source_chain,
                "timestamp": timestamp.isoformat(),
            }
            lock_key = bridge_credit_private_key()
            if lock_key:
                lock_body[BRIDGE_SIGNATURE_FIELD] = sign_bridge_lock(lock_body, transfer_id, lock_key)
            else:
                logger.warning(
                    "BRIDGE_LOCK issued without a signing key (BRIDGE_RELEASE_PRIVATE_KEY/ESCROW_RELEASE_PRIVATE_KEY); "
                    "it will fail v9+ validation"
                )
            mempool = get_mempool()
            mempool.add(
                lock_body,
                chain_id=source_chain,
                tx_hash=transfer_id,
            )

            if not block_scoped:
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
                        **(
                            {BRIDGE_SIGNATURE_FIELD: lock_body[BRIDGE_SIGNATURE_FIELD]}
                            if BRIDGE_SIGNATURE_FIELD in lock_body
                            else {}
                        ),
                    },
                    value=amount,
                    fee=fee,
                    nonce=lock_nonce,
                    timestamp=timestamp,
                    block_height=None,
                    status="confirmed",
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
                release_amount=release_amount,
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

    def _lock_record_from_source(
        self, transfer_id: str, proof: dict[str, Any], target_chain: str
    ) -> CrossChainTransfer | None:
        """Target-chain copy of the lock record this node wrote on the source chain.

        When the node hosts the source chain in a separate store (the relayer
        case), the record ``initiate_transfer`` wrote there is node-authored
        and is the trusted source of the payout fields. Returns None when the
        lock is not known locally.
        """
        source_chain = proof.get("source_chain")
        if not source_chain or source_chain == target_chain or not self._chain_db_ready(source_chain):
            return None
        with self._session_for(source_chain) as src_session:
            src = src_session.get(CrossChainTransfer, transfer_id)
            if src is None or src.source_chain != source_chain or src.target_chain != target_chain:
                return None
            return CrossChainTransfer(
                transfer_id=src.transfer_id,
                source_chain=src.source_chain,
                target_chain=src.target_chain,
                sender=src.sender,
                recipient=src.recipient,
                amount=src.amount,
                asset=src.asset,
                status=src.status,
                source_tx_hash=src.source_tx_hash,
                lock_time=src.lock_time,
                release_amount=src.release_amount,
            )

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
            # F1: the fields a release pays out on (amount, recipient, target
            # chain) must come from a record this node wrote when it served the
            # lock, or be bound by the proof's Merkle leaf. A record built from
            # the proof alone used to be checked against itself.
            proof_built_record = False
            if not record:
                record = self._lock_record_from_source(transfer_id, proof, target_chain)
            if not record:
                # v0.7.3: the lock is on another node; materialise the record
                # from the proof, but only persist it once the proof verifies.
                proof_built_record = True
                record = CrossChainTransfer(
                    transfer_id=transfer_id,
                    source_chain=proof.get("source_chain", ""),
                    target_chain=target_chain,
                    sender=proof.get("sender", ""),
                    recipient=proof.get("recipient", ""),
                    amount=proof.get("amount", 0),
                    asset=proof.get("asset", "native"),
                    status="pending",
                    source_tx_hash=transfer_id,
                    lock_time=datetime.now(UTC),
                )
            if record.status != "pending":
                raise ValueError(f"Transfer already processed: {record.status}")
            if not self._validate_proof(proof, record, require_leaf_binding=proof_built_record):
                raise ValueError("Invalid transfer proof")
            session.add(record)
            # GAP-47: cross-chain swaps may release a converted amount that
            # differs from the locked amount; plain bridges release `amount`.
            release_amount = record.release_amount if record.release_amount is not None else record.amount
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            if not block_scoped:
                recipient_account = session.get(Account, (record.target_chain, record.recipient))
                if not recipient_account:
                    recipient_account = Account(chain_id=record.target_chain, address=record.recipient, balance=0, nonce=0)
                    session.add(recipient_account)
                recipient_account.balance += release_amount
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
                    bridge_release_account = Account(
                        chain_id=record.target_chain, address=bridge_release_addr, balance=release_amount, nonce=0
                    )
                    session.add(bridge_release_account)
                release_nonce = bridge_release_account.nonce
            else:
                release_nonce = 0
            target_tx_hash = hashlib.sha256(f"{transfer_id}:{record.target_chain}:{int(time.time())}".encode()).hexdigest()
            if not block_scoped:
                release_payload = {
                    "type": "BRIDGE_RELEASE",
                    "transfer_id": transfer_id,
                    "source_chain": record.source_chain,
                    "source_sender": record.sender,
                    "target_chain": record.target_chain,
                    "amount": release_amount,
                    "asset": record.asset,
                    "proof": proof_hash,
                }
                # v5+ consensus requires the bridge authority signature over
                # the credit's semantic fields — sign the row-shaped view the
                # proposer sweep will rebuild (value=0: the credit already
                # happened above; the row anchors the record).
                self._sign_bridge_credit(
                    {
                        "type": "BRIDGE_RELEASE",
                        "to": record.recipient,
                        "value": 0,
                        "fee": 0,
                        "nonce": release_nonce,
                        "payload": release_payload,
                    },
                    target_tx_hash,
                    payload=release_payload,
                )
                release_tx = Transaction(
                    chain_id=record.target_chain,
                    tx_hash=target_tx_hash,
                    sender="bridge_release",
                    recipient=record.recipient,
                    payload=release_payload,
                    value=0,
                    fee=0,
                    nonce=release_nonce,
                    timestamp=datetime.now(UTC),
                    block_height=None,
                    status="confirmed",
                    type="BRIDGE_RELEASE",
                )
                session.add(release_tx)
            if block_scoped:
                from ..mempool import get_mempool

                mempool = get_mempool()
                # Semantic fields go inside ``payload`` — the same shape the
                # pre-registered Transaction row carries. The sealer persists
                # ``tx_data["payload"]`` and ``/rpc/blocks-range`` serves the
                # row, so a flat dict would drop bridge_signature (and
                # lock_tx_hash) from everything range-synced validators see:
                # at v5+ a bulk-synced node would fail the signature check and
                # silently skip the credit while gossip-fed nodes apply it.
                # ``bridge_credit_message`` reads payload-first, so the signed
                # bytes are identical to the old flat shape.
                credit_payload = {
                    "type": "BRIDGE_RELEASE",
                    "transfer_id": transfer_id,
                    "source_chain": record.source_chain,
                    "source_sender": record.sender,
                    "target_chain": record.target_chain,
                    "amount": release_amount,
                    "asset": record.asset,
                    "proof": proof_hash,
                }
                credit_dict = {
                    "from": "bridge_release",
                    "to": record.recipient,
                    "amount": release_amount,
                    "fee": 0,
                    "type": "BRIDGE_RELEASE",
                    "nonce": release_nonce,
                    "timestamp": (record.confirm_time or datetime.now(UTC)).isoformat(),
                    "payload": credit_payload,
                }
                self._sign_bridge_credit(credit_dict, target_tx_hash, payload=credit_payload)
                mempool.add(
                    credit_dict,
                    chain_id=record.target_chain,
                    tx_hash=target_tx_hash,
                )
            record.status = "confirmed"
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
                        src_record.status = "confirmed"
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
                transfer.status = BridgeStatus.confirmed
                transfer.target_tx_hash = target_tx_hash
                transfer.confirm_time = datetime.now(UTC)
                transfer.proof = proof
            logger.info(
                "Bridge transfer confirmed (release pending): %s... released %s to %s...",
                transfer_id[:16],
                release_amount,
                record.recipient[:20],
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
                    raise ValueError(f"Refund not allowed yet: {elapsed:.0f}s since lock, minimum delay is {refund_delay}s")

            # Return the locked amount to the sender (fee was already deducted at lock time)
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            if not block_scoped:
                sender_account = session.get(Account, (record.source_chain, record.sender))
                if not sender_account:
                    sender_account = Account(chain_id=record.source_chain, address=record.sender, balance=0, nonce=0)
                    session.add(sender_account)
                sender_account.balance += record.amount
                refund_nonce = sender_account.nonce
                sender_account.nonce += 1
                session.add(sender_account)
            else:
                refund_nonce = 0

            # Create a BRIDGE_REFUND transaction record
            refund_tx_hash = hashlib.sha256(
                f"{transfer_id}:refund:{record.source_chain}:{int(time.time())}".encode()
            ).hexdigest()
            if not block_scoped:
                refund_payload = {
                    "type": "BRIDGE_REFUND",
                    "transfer_id": transfer_id,
                    # v6: consensus binds the refund to the sealed BRIDGE_LOCK it
                    # repays — the lock's tx_hash on this (source) chain.
                    "lock_tx_hash": record.source_tx_hash or transfer_id,
                    "source_chain": record.source_chain,
                    "target_chain": record.target_chain,
                    "amount": record.amount,
                    "asset": record.asset,
                }
                # v5+ consensus requires the bridge authority signature; and
                # like the release row, value=0 — the sender was already
                # credited above, the sealed row only anchors the record
                # (a nonzero value would double-credit at apply).
                self._sign_bridge_credit(
                    {
                        "type": "BRIDGE_REFUND",
                        "to": record.sender,
                        "value": 0,
                        "fee": 0,
                        "nonce": refund_nonce,
                        "payload": refund_payload,
                    },
                    refund_tx_hash,
                    payload=refund_payload,
                )
                refund_tx = Transaction(
                    chain_id=record.source_chain,
                    tx_hash=refund_tx_hash,
                    sender="bridge_refund",
                    recipient=record.sender,
                    payload=refund_payload,
                    value=0,
                    fee=0,
                    nonce=refund_nonce,
                    timestamp=datetime.now(UTC),
                    block_height=None,
                    status="confirmed",
                    type="BRIDGE_REFUND",
                )
                session.add(refund_tx)
            if block_scoped:
                from ..mempool import get_mempool

                mempool = get_mempool()
                # Same payload-shaping as the release above: lock_tx_hash must
                # survive into the persisted row — the v6 refund-binding probe
                # reads prior.payload["lock_tx_hash"], and validators that see
                # only the row (blocks-range sync) need bridge_signature in it.
                credit_payload = {
                    "type": "BRIDGE_REFUND",
                    "transfer_id": transfer_id,
                    "lock_tx_hash": record.source_tx_hash or transfer_id,
                    "source_chain": record.source_chain,
                    "target_chain": record.target_chain,
                    "amount": record.amount,
                    "asset": record.asset,
                }
                credit_dict = {
                    "from": "bridge_refund",
                    "to": record.sender,
                    "amount": record.amount,
                    "fee": 0,
                    "type": "BRIDGE_REFUND",
                    "nonce": refund_nonce,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": credit_payload,
                }
                self._sign_bridge_credit(credit_dict, refund_tx_hash, payload=credit_payload)
                mempool.add(
                    credit_dict,
                    chain_id=record.source_chain,
                    tx_hash=refund_tx_hash,
                )
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

        v0.7.3: Looks up the source block that includes the lock, rebuilds the
        bridge event trie from all BRIDGE_LOCK transactions in that block, and
        returns the block-signed proposer/validator signatures plus the Merkle
        proof for this transfer.
        """
        source_chain = source_chain or str(getattr(settings, "chain_id", "") or "")
        with self._session_for(source_chain) as session:
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")

            # Prefer the block that recorded the lock transaction.
            lock_tx = session.exec(
                select(Transaction).where(
                    Transaction.chain_id == source_chain,
                    Transaction.tx_hash == (record.source_tx_hash or transfer_id),
                )
            ).first()
            if lock_tx and lock_tx.block_height:
                block_height = lock_tx.block_height
            elif lock_tx is not None and not block_hash:
                # The lock exists but is not sealed into a block yet — a proof
                # built now would anchor to the wrong block. Report the real
                # state instead of falling back to the default height.
                raise ValueError(f"Lock transaction {record.source_tx_hash or transfer_id} is not sealed in a block yet")

            block = session.exec(
                select(Block).where(
                    Block.chain_id == source_chain,
                    Block.height == block_height,
                )
            ).first()
            if block is None:
                raise ValueError(f"Source block not found: {source_chain} height {block_height}")

            from ..state.merkle_patricia_trie import MerklePatriciaTrie

            trie = MerklePatriciaTrie()
            # GAP-47: detect lock txs by the persisted ``type`` column, not
            # only ``payload["type"]`` — under block-scoped pre-registration
            # the mempool entry carries no ``payload`` key, so the sealed row
            # has ``payload={}`` and the column is the only reliable marker.
            lock_txs = [
                tx for tx in block.transactions if (tx.type or (tx.payload or {}).get("type", "")).upper() == "BRIDGE_LOCK"
            ]
            transfer_ids = [tx.tx_hash for tx in lock_txs]
            records = session.exec(
                select(CrossChainTransfer).where(
                    CrossChainTransfer.source_chain == source_chain,
                    CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
                )
            ).all()
            record_map = {r.transfer_id: r for r in records}
            for tx in lock_txs:
                tx_record = record_map.get(tx.tx_hash)
                if tx_record is None:
                    value = unknown_lock_leaf(tx.tx_hash)
                else:
                    value = self._build_lock_event_value(tx_record, block.height)
                trie.put(tx.tx_hash.encode(), value.encode())

            computed_root = "0x" + trie.get_root().hex()
            if computed_root != (block.bridge_state_root or ""):
                raise ValueError("Computed bridge state root does not match block")

            lock_tx_hash = record.source_tx_hash or transfer_id
            lock_value = self._build_lock_event_value(record, block.height).encode()
            proof_bytes = trie.get_proof(lock_tx_hash.encode())

            validator_signatures: list[str] = []
            if block.block_metadata:
                try:
                    metadata = json.loads(block.block_metadata)
                    validator_signatures = [
                        a.get("signature", "") for a in metadata.get("attestations", []) if a.get("signature")
                    ]
                except Exception:
                    validator_signatures = []

            # Issue #670: the sealed metadata may carry fewer attestations than
            # the proof-side multisig threshold needs — the attestation gate
            # seals blocks with attestations=[] whenever the PBFT commit
            # certificate covers effective_min, and such proofs stall on
            # "Threshold not met 1/2" forever. Top the signature list up to the
            # configured threshold with fresh signatures over THIS sealed
            # block's canonical header message; verification is unchanged
            # (same message shape, same membership check).
            validator_signatures = self._augment_proof_validator_signatures(block, source_chain, validator_signatures)

            return {
                "source_chain": record.source_chain,
                "target_chain": record.target_chain,
                "lock_tx_hash": lock_tx_hash,
                "amount": record.amount,
                "sender": record.sender,
                "recipient": record.recipient,
                "asset": record.asset,
                "chain_id": record.source_chain,
                "block_height": block.height,
                "block_hash": block.hash,
                "proposer": block.proposer,
                "parent_hash": block.parent_hash,
                "state_root": block.state_root or "",
                "bridge_state_root": block.bridge_state_root or "",
                "merkle_proof": [p.hex() for p in proof_bytes],
                "lock_event": lock_value.decode(),
                "proposer_signature": block.signature,
                "validator_signatures": validator_signatures,
            }

    @staticmethod
    def _proof_header_message(block: Block) -> dict[str, Any]:
        """Canonical header message for this sealed block — verifier-identical.

        Built via ``aitbc.bridge.build_verification_message``, the same builder
        ``_verify_header_threshold_signatures`` runs on the mirrored header.
        The field set is identical to ``poa._block_header_message``
        (chain_id, height, hash, parent_hash, proposer, state_root,
        bridge_state_root), so signatures produced here recover on the verify
        side without any verifier change.
        """
        from aitbc.bridge import build_verification_message
        from aitbc.bridge.types import BridgeBlockHeader as _VerificationHeader

        return build_verification_message(
            _VerificationHeader(
                chain_id=block.chain_id,
                height=block.height,
                hash=block.hash,
                parent_hash=block.parent_hash,
                proposer=block.proposer,
                state_root=block.state_root or "",
                bridge_state_root=block.bridge_state_root or "",
            )
        )

    def _local_validator_key_map(self) -> dict[str, str]:
        """Validator address → private key held by this node (VALIDATOR_KEYS JSON)."""
        raw = getattr(settings, "validator_keys", "") or ""
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("VALIDATOR_KEYS is not valid JSON; local proof signing unavailable")
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(a): str(k) for a, k in data.items() if a and k}

    def _proof_source_validator_set(self, source_chain: str) -> Any | None:
        """Validator set for the source chain, registered set first.

        Falls back to the VALIDATOR_SET env JSON when the bridge registry has
        no set for the node's own chain — on a producing node env is the
        membership source of truth, and without it proof augmentation has no
        membership list to top up against.
        """
        vset = None
        try:
            vset = self.get_validator_set(source_chain)
        except Exception as e:
            logger.debug("Validator set lookup failed for %s: %s", source_chain, e)
        if vset is not None:
            return vset
        raw = getattr(settings, "validator_set", "") or ""
        own_chain = str(getattr(settings, "chain_id", "") or "")
        if not raw.strip() or source_chain != own_chain:
            return vset
        try:
            from aitbc.bridge.types import ValidatorInfo, ValidatorSet

            members = json.loads(raw)
            validators = [
                ValidatorInfo(
                    address=str(v["address"]),
                    public_key=str(v.get("public_key") or v.get("pubkey") or ""),
                    chain_id=source_chain,
                    epoch=0,
                    is_active=bool(v.get("is_active", True)),
                )
                for v in members
                if isinstance(v, dict) and v.get("address")
            ]
            if not validators:
                return None
            return ValidatorSet(
                chain_id=source_chain,
                epoch=0,
                validators=validators,
                threshold=int(getattr(settings, "bridge_multisig_threshold", 3)),
                total=len(validators),
            )
        except Exception as e:
            logger.warning("Failed to parse VALIDATOR_SET for proof augmentation: %s", e)
            return None

    def _augment_proof_validator_signatures(
        self,
        block: Block,
        source_chain: str,
        validator_signatures: list[str],
    ) -> list[str]:
        """Top up ``validator_signatures`` until the multisig threshold is met.

        Issue #670: blocks sealed on a PBFT commit certificate carry
        ``attestations=[]`` (or fewer than the threshold) in their metadata,
        and a proof copied verbatim from them fails the bc-2-side
        ``_verify_threshold_signatures`` membership/threshold check forever.

        The signatures added here are over the sealed block's canonical
        header message — the exact shape the verifier rebuilds — so this
        strengthens provability without weakening verification. Sources, in
        order: (a) validator keys held locally (``VALIDATOR_KEYS``), (b) a
        best-effort remote attestation round via ``RemoteAttestationService``
        for the still-missing count. Failures degrade to the sealed set.
        """
        try:
            return self._augment_proof_validator_signatures_impl(block, source_chain, validator_signatures)
        except Exception:
            logger.exception(
                "Proof signature augmentation failed for block %s height %s — keeping sealed attestations",
                source_chain,
                block.height,
            )
            return validator_signatures

    def _augment_proof_validator_signatures_impl(
        self,
        block: Block,
        source_chain: str,
        validator_signatures: list[str],
    ) -> list[str]:
        from aitbc.bridge import check_threshold, recover_all_signers

        threshold = int(getattr(settings, "bridge_multisig_threshold", 3) or 0)
        if threshold <= 1:
            return validator_signatures

        vset = self._proof_source_validator_set(source_chain)
        if vset is None:
            return validator_signatures

        message = self._proof_header_message(block)
        proposer_sig = block.signature or ""
        all_sigs = list(validator_signatures)
        if proposer_sig and proposer_sig not in all_sigs:
            all_sigs.append(proposer_sig)
        signers = recover_all_signers(message, all_sigs)
        meets, count, deduped = check_threshold(signers, vset, threshold)
        if meets:
            # Cheap path: sealed attestations + proposer already satisfy the
            # threshold — keep the proof byte-identical to before.
            return validator_signatures

        needed = threshold - count
        logger.info(
            "Bridge proof for %s height %s has %d/%d signers; collecting %d more",
            source_chain,
            block.height,
            count,
            threshold,
            needed,
        )
        covered = {s.lower() for s in deduped}
        member_addrs = {a.lower() for a in vset.addresses}
        collected = list(validator_signatures)

        local_keys = self._local_validator_key_map()
        needed = self._top_up_local_proof_signatures(block, message, local_keys, member_addrs, covered, collected, needed)

        # (b) remote attestation round for whatever is still missing.
        if needed > 0:
            needed = self._top_up_remote_proof_signatures(
                block, source_chain, message, local_keys, member_addrs, covered, collected, needed
            )

        if needed > 0:
            logger.warning(
                "Bridge proof for %s height %s remains below threshold after augmentation "
                "(%d signer(s) still missing); peers can only re-attest while the block "
                "is at/near their tip",
                source_chain,
                block.height,
                needed,
            )
        return collected

    def _top_up_local_proof_signatures(
        self,
        block: Block,
        message: dict[str, Any],
        local_keys: dict[str, str],
        member_addrs: set[str],
        covered: set[str],
        collected: list[str],
        needed: int,
    ) -> int:
        # (a) local validator keys — always reachable in this process.
        from aitbc.crypto.consensus_signing import sign_consensus_message
        from aitbc.crypto.signature_recovery import canonical_address

        for address, private_key in local_keys.items():
            if needed <= 0:
                break
            try:
                canon = canonical_address(address).lower()
            except Exception:
                canon = address.lower()
            if canon == (block.proposer or "").lower() or canon in covered or canon not in member_addrs:
                continue
            try:
                signature = sign_consensus_message(message, private_key)
            except Exception as e:
                logger.warning("Failed to sign proof attestation with local key %s: %s", address, e)
                continue
            collected.append(signature)
            covered.add(canon)
            needed -= 1
        return needed

    def _top_up_remote_proof_signatures(
        self,
        block: Block,
        source_chain: str,
        message: dict[str, Any],
        local_keys: dict[str, str],
        member_addrs: set[str],
        covered: set[str],
        collected: list[str],
        needed: int,
    ) -> int:
        from aitbc.bridge import recover_all_signers

        for att in self._collect_remote_proof_attestations(block, source_chain, needed, local_keys):
            signature = str(att.get("signature") or "")
            if not signature:
                continue
            try:
                recovered = recover_all_signers(message, [signature])
            except Exception:
                recovered = []
            if not recovered:
                continue
            signer = recovered[0].lower()
            if signer in covered or signer not in member_addrs:
                continue
            collected.append(signature)
            covered.add(signer)
            needed -= 1
            if needed <= 0:
                break
        return needed

    def _collect_remote_proof_attestations(
        self,
        block: Block,
        source_chain: str,
        needed: int,
        local_keys: dict[str, str],
    ) -> list[dict[str, str]]:
        """Best-effort remote attestations over the sealed block's header.

        Reuses ``RemoteAttestationService.collect_attestations`` — the same
        gossip request the proposer publishes at seal time — so peers re-sign
        the identical canonical header message. Two inherent limits:

        - ``collect_attestations`` returns immediately when the node holds no
          validator keys, so this path is only live on nodes that produce.
        - v9 attesters re-verify the request's transaction set against their
          own parent state; a sealed block is attestable only while it is
          still the peer's tip (the "late request" branch), so this helps the
          prompt relayer pass right after sealing, not historical rebuilds.

        ``build_proof`` is synchronous and may run while the app event loop is
        blocked by its own caller, so the collection always runs on a
        dedicated loop in a worker thread. Backends whose publish path is
        bound to the main loop simply fail and degrade to zero answers.
        """
        if needed <= 0 or not local_keys:
            return []
        try:
            from ..consensus.remote_attestation import RemoteAttestationService
        except Exception as e:
            logger.debug("Remote attestation service unavailable for proof build: %s", e)
            return []

        envelopes: list[dict[str, Any]] = [tx.envelope for tx in (block.transactions or []) if isinstance(tx.envelope, dict)]
        service = RemoteAttestationService(
            source_chain,
            local_keys,
            session_factory=lambda: self._session_for(source_chain),
        )
        timeout = float(getattr(settings, "bridge_proof_attestation_timeout_seconds", 2.0) or 0.0)
        if timeout <= 0:
            return []

        result: dict[str, Any] = {}

        def _run() -> None:
            try:
                result["atts"] = asyncio.run(
                    service.collect_attestations(block, needed, timeout=timeout, transactions=envelopes)
                )
            except Exception as e:  # noqa: BLE001 - best-effort path, any failure degrades to sealed set
                result["err"] = e

        worker = threading.Thread(target=_run, name="bridge-proof-attestations", daemon=True)
        worker.start()
        worker.join(timeout + 5.0)
        if worker.is_alive():
            logger.warning("Remote proof attestation collection timed out for %s height %s", source_chain, block.height)
            return []
        if "err" in result:
            logger.debug("Remote proof attestation collection failed: %s", result["err"])
            return []
        return list(result.get("atts") or [])

    def _build_lock_event_value(self, record: CrossChainTransfer, height: int | None) -> str:
        """Canonical lock event string the source block at ``height`` committed to."""
        return lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, height)

    def _generate_transfer_id(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, timestamp: int
    ) -> str:
        """Generate unique transfer ID."""
        data = f"{source_chain}:{target_chain}:{sender}:{recipient}:{amount}:{timestamp}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()

    def _proof_binds_payout_fields(self, proof: dict[str, Any], record: CrossChainTransfer) -> bool:
        """True when the proof's Merkle leaf commits to every field the release pays on.

        Only the recipient-bound leaf (``bridge_lock_leaf_v2_height``) covers
        the recipient, so a proof from an older source block cannot stand on
        its own and is refused.
        """
        amount = proof.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            logger.warning("Proof amount must be a positive integer")
            return False
        if not proof.get("merkle_proof"):
            logger.warning("Proof-built transfer record needs a Merkle inclusion proof; rejecting")
            return False
        if not lock_leaf_v2_active(proof.get("block_height")):
            logger.warning(
                "Lock for %s is not on this node and its source block (height=%s) predates the "
                "recipient-bound leaf; rejecting",
                record.transfer_id[:16],
                proof.get("block_height"),
            )
            return False
        return True

    def _validate_proof(self, proof: dict[str, Any], record: CrossChainTransfer, require_leaf_binding: bool = False) -> bool:
        """Validate cross-chain transfer proof with cryptographic verification (v0.7.3).

        ``require_leaf_binding`` is set when ``record`` was built from the
        proof itself: the field checks below then compare the proof with
        itself, so the proof must carry a recipient-bound leaf and a Merkle
        inclusion proof against a stored header, or it is refused.
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
        if proof.get("target_chain") is not None and proof.get("target_chain") != record.target_chain:
            logger.warning("Proof target_chain mismatch")
            return False

        # F1: the proven key and leaf must be the ones this transfer's fields
        # produce. Without this the Merkle check below only proves that *some*
        # lock exists — not that it carries this amount, recipient or target.
        if proof.get("lock_tx_hash") != (getattr(record, "source_tx_hash", None) or record.transfer_id):
            logger.warning("Proof lock_tx_hash does not match the transfer record")
            return False
        if require_leaf_binding and not self._proof_binds_payout_fields(proof, record):
            return False
        if proof.get("merkle_proof"):
            expected_event = self._build_lock_event_value(record, proof.get("block_height"))
            if proof.get("lock_event") != expected_event:
                logger.warning("Proof lock_event does not match the transfer fields")
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

        # Step 5: Block header lookup + verification (v0.7.2)
        header: BridgeBlockHeader | None = None
        verification_mode = getattr(settings, "bridge_verification_mode", "in_process")
        if verification_mode == "in_process":
            # F2: only a header this node stored can anchor a proof. A header
            # built from the proof would let the proof choose its own roots,
            # proposer and confirmation_count.
            header = self._get_block_header(record_chain_id, block_height)
            if header is None:
                logger.warning("No stored block header for chain=%s height=%s; rejecting proof", record_chain_id, block_height)
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

            # Step 5a: Bridge state root verification
            proof_bridge_root = proof.get("bridge_state_root") or proof.get("state_root", "")
            expected_bridge_root = header.bridge_state_root or header.state_root
            if proof_bridge_root and proof_bridge_root != expected_bridge_root:
                logger.warning(
                    "Bridge state root mismatch: proof=%s vs header=%s",
                    proof_bridge_root[:16],
                    expected_bridge_root[:16],
                )
                return False

            # Step 5b: Block header signature verification (B4)
            if not self._verify_block_header_signature(header):
                logger.warning("Block header signature verification failed for height=%s", block_height)
                return False

            # Step 5c: Merkle proof verification (B3)
            merkle_proof = proof.get("merkle_proof", [])
            if merkle_proof:
                merkle_state_root = header.bridge_state_root or header.state_root
                if not self._verify_merkle_proof(merkle_state_root, proof):
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

        elif require_leaf_binding:
            logger.warning("Proof-built transfer record needs in-process Merkle verification; rejecting")
            return False

        # Step 4: Multi-sig threshold verification (v0.7.1, kept)
        # Moved to occur after the BridgeBlockHeader is available.
        if not self._verify_threshold_signatures(proof, header=header):
            logger.warning("Proof signature verification failed (threshold or single-sig)")
            return False

        # Step 6: Validator set epoch grace period check (B6) — epoch-aware:
        # the current epoch is authoritative; superseded epochs get the grace
        # window. A proof's validator_epoch of 0/absent resolves to latest.
        if not self._check_validator_set_freshness(record_chain_id, proof.get("validator_epoch") or None):
            logger.warning("Validator set for chain=%s is stale (grace period expired)", record_chain_id)
            return False

        return True

    def _finalize_confirmed_transfers(self, chain_id: str) -> int:
        """Move 'confirmed' transfers to 'completed' once the release tx is in a block.

        A transfer is only considered finalised when the BRIDGE_RELEASE
        transaction has been sealed into a produced block on the target chain.
        """
        finalized = 0
        with self._session_for(chain_id) as session:
            records = session.exec(
                select(CrossChainTransfer).where(
                    CrossChainTransfer.target_chain == chain_id,
                    CrossChainTransfer.status == "confirmed",
                    CrossChainTransfer.target_tx_hash.is_not(None),  # type: ignore[union-attr]
                )
            ).all()
            for record in records:
                tx = session.exec(
                    select(Transaction).where(
                        Transaction.chain_id == chain_id,
                        Transaction.tx_hash == record.target_tx_hash,
                        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                    )
                ).first()
                if not tx:
                    continue
                record.status = "completed"
                session.add(record)
                # Mirror the final state on the source chain.
                try:
                    with self._session_for(record.source_chain) as src_session:
                        src_record = src_session.get(CrossChainTransfer, record.transfer_id)
                        if src_record and src_record.status != "completed":
                            src_record.status = "completed"
                            src_record.target_tx_hash = record.target_tx_hash
                            src_record.proof_hash = record.proof_hash
                            src_record.confirm_time = record.confirm_time
                            src_session.add(src_record)
                            src_session.commit()
                except Exception:
                    logger.exception("Failed to update source-chain bridge record for %s", record.transfer_id)
                session.commit()
                finalized += 1
                in_memory = self._pending_transfers.get(record.transfer_id)
                if in_memory:
                    in_memory.status = BridgeStatus.completed
                    in_memory.target_tx_hash = record.target_tx_hash
                    in_memory.confirm_time = record.confirm_time
        return finalized

    def _known_chains(self) -> list[str]:
        """All chain IDs this node may hold bridge state for.

        Union of ``supported_chains`` (locally produced/followed chains),
        ``bridge_supported_chains`` (chains the bridge is configured to
        serve) and the node's default ``chain_id``.
        """
        seen: set[str] = set()
        for raw in (
            getattr(settings, "supported_chains", ""),
            getattr(settings, "bridge_supported_chains", ""),
            str(getattr(settings, "chain_id", "") or ""),
        ):
            for chain in str(raw or "").split(","):
                chain = chain.strip()
                if chain:
                    seen.add(chain)
        return sorted(seen)

    def _chain_db_ready(self, chain_id: str) -> bool:
        """True when this node holds an initialized bridge store for ``chain_id``.

        ``bridge_supported_chains`` may list chains produced by other nodes;
        this node holds no store for those, and the db layer refuses to
        create or open one. Probe the file's existence, mark the chain
        unavailable, and let the finalizer skip it — transfers targeting it
        keep their honest non-terminal state.

        The negative verdict is re-probed every
        ``bridge_chain_unavailable_retry_seconds`` (default 300): a probe that
        failed on a transient condition (store file not yet created, sqlite
        lock held by the producing process during startup) must not silence
        the chain for the rest of the process's lifetime — a permanent cache
        entry is exactly how a finalizer pass goes quiet with only a single
        INFO line to show for it.
        """
        unavailable = getattr(self, "_unavailable_bridge_chains", None)
        if unavailable is None:
            self._unavailable_bridge_chains: dict[str, float] = {}
            unavailable = self._unavailable_bridge_chains
        retry_after = float(getattr(settings, "bridge_chain_unavailable_retry_seconds", 300))
        failed_at = unavailable.get(chain_id)
        if failed_at is not None and (time.monotonic() - failed_at) < retry_after:
            return False
        try:
            with self._session_for(chain_id) as session:
                # Select the full row, not a single column: a stale DB may
                # have the table without GAP-47 columns (release_amount etc.)
                # and only a full-row select detects that.
                session.exec(select(CrossChainTransfer).limit(1)).first()
            if failed_at is not None:
                unavailable.pop(chain_id, None)
                logger.info(
                    "Bridge store for chain %s became available on re-probe; resuming finalizer passes for it",
                    chain_id,
                )
            return True
        except Exception as e:
            unavailable[chain_id] = time.monotonic()
            log = logger.debug if failed_at is not None else logger.info
            log(
                "Bridge store for chain %s is not initialized on this node (%s); "
                "skipping it in finalizer passes — transfers targeting it stay pending",
                chain_id,
                e,
            )
            return False

    def _sync_local_chain_headers(self, chain_id: str) -> int:
        """Store bridge block headers for locally known blocks of ``chain_id``.

        GAP-47: the bridge proof path needs stored ``BridgeBlockHeader`` rows
        to verify finality, but nothing ever populated them — the RPC intake
        endpoint is admin-gated and no internal caller existed. A node that
        produces (or fully syncs) a chain already holds the authoritative
        signed headers in its ``block`` table, so mirror them into
        ``bridge_block_header`` here. ``store_block_header`` derives
        confirmation counts and finality from stored data, so this also makes
        ``_check_finality_for_transfer`` reachable for real transfers.
        """
        with self._session_for(chain_id) as session:
            try:
                head = session.exec(
                    select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)  # type: ignore[attr-defined]
                ).first()
            except Exception:
                return 0
            if head is None:
                return 0
            last_stored = session.exec(
                select(BridgeBlockHeader.height)
                .where(BridgeBlockHeader.chain_id == chain_id)
                .order_by(BridgeBlockHeader.height.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            finality_blocks = int(getattr(settings, "bridge_finality_blocks", 6))
            if last_stored is None:
                # First run: backfill only the recent finality window — older
                # headers cannot become relevant to a pending transfer and a
                # full-history backfill would needlessly grow the table.
                start_height = max(0, head.height - 2 * finality_blocks - 5)
            else:
                start_height = int(last_stored) + 1
            # Bounded per pass: an unbounded select loads every block from the
            # gap start to the chain head into memory at once, and a node that
            # has been down long enough for that to matter is exactly the node
            # that cannot afford it. A host behind by more than one batch
            # catches up over successive passes rather than in one, which still
            # converges with room to spare: 500 headers every
            # ``bridge_monitor_interval`` (60s) against roughly one block a
            # minute of production. Both halves -- the bound and the
            # convergence -- are pinned by test_bridge_header_sync_bound.py.
            batch = max(1, int(getattr(settings, "bridge_header_sync_batch", 500)))
            new_blocks = session.exec(
                # Only header fields are stored below — suppress the selectin
                # transactions/receipts eager-loads, they are wasted work here.
                select(Block)
                .options(raiseload("*"))
                .where(Block.chain_id == chain_id, Block.height >= start_height)
                .order_by(Block.height.asc())  # type: ignore[attr-defined]
                .limit(batch)
            ).all()
        stored = 0
        for block in new_blocks:
            try:
                self.store_block_header(  # type: ignore[attr-defined]
                    {
                        "chain_id": block.chain_id,
                        "height": block.height,
                        "hash": block.hash,
                        "parent_hash": block.parent_hash,
                        "proposer": block.proposer,
                        "state_root": block.state_root or "",
                        "bridge_state_root": block.bridge_state_root or "",
                        "signature": block.signature or "",
                    }
                )
                stored += 1
            except Exception:
                logger.exception("Failed to store bridge header for %s height=%s", chain_id, block.height)
                break
        return stored

    def _relay_pending_transfers(self, chain_id: str) -> int:
        """Confirm pending source-chain transfers whose lock has finality.

        GAP-47 relayer: for each transfer locked on ``chain_id``, once the
        lock transaction is sealed in a block and that block's stored header
        has enough confirmations, build the real Merkle proof and run the
        normal ``confirm_transfer`` verification + release path. Transfers
        that cannot yet settle (lock unsealed, finality pending, validator
        set missing) stay ``pending`` — the honest intermediate state.

        Scope (#662): this process only relays transfers whose target is its
        OWN ``settings.chain_id``. ``confirm_transfer`` queues the
        BRIDGE_RELEASE into this process's mempool, and only the proposer of
        this node's own chain drains that mempool — relaying a transfer that
        targets another chain would mint a release tx no block producer ever
        seals, stranding the lock. A bc-2 rpc therefore relays only
        bc-2-target transfers and an island rpc only island-target ones; the
        rpc of the target chain sees the pending row because it follows the
        source chain's store.
        """
        relayed = 0
        own_chain = str(getattr(settings, "chain_id", "") or "")
        pending = [
            t for t in self.list_pending_transfers(chain_id) if t.source_chain == chain_id and t.target_chain == own_chain
        ]
        for transfer in pending:
            if not self._chain_db_ready(transfer.target_chain):
                # The release must be written to the target chain's store;
                # when this node does not host it, the transfer keeps its
                # honest pending/locked state instead of erroring each pass.
                logger.debug(
                    "Bridge relayer: target store for %s unavailable here; %s stays pending",
                    transfer.target_chain,
                    transfer.transfer_id[:16],
                )
                continue
            try:
                proof = self.build_proof(transfer.transfer_id, source_chain=chain_id)
            except ValueError as e:
                # Lock not sealed into a block yet, or the source block is not
                # available — normal intermediate state, retry next pass.
                logger.debug("Bridge relayer: %s not ready for confirm: %s", transfer.transfer_id[:16], e)
                continue
            except Exception:
                logger.exception("Bridge relayer: failed to build proof for %s", transfer.transfer_id[:16])
                continue
            try:
                self.confirm_transfer(transfer.transfer_id, proof)
                relayed += 1
            except ValueError as e:
                # Finality/threshold/validator-set failures stay pending; the
                # record keeps its honest state and we retry next interval.
                logger.debug("Bridge relayer: confirm for %s rejected: %s", transfer.transfer_id[:16], e)
            except Exception:
                logger.exception("Bridge relayer: confirm failed for %s", transfer.transfer_id[:16])
        return relayed

    async def start_finalizer(self) -> None:
        """Background loop that finalises bridge releases once they are block-sealed.

        Each pass (every ``bridge_monitor_interval`` seconds) runs three real
        phases on every known chain (GAP-47):
        1. mirror newly produced/synced block headers into the bridge header
           table so proofs have a finality anchor,
        2. relay pending transfers: build their Merkle proof and run the
           standard confirm path once the lock has finality,
        3. mark confirmed transfers ``completed`` once the release tx is
           sealed on the target chain.

        Each pass runs on a worker thread, never on the event loop -- see the
        comment on the call below.
        """
        interval = getattr(settings, "bridge_monitor_interval", 60)
        relayer_enabled = getattr(settings, "bridge_relayer_enabled", True) and getattr(
            settings, "bridge_release_enabled", False
        )
        # Chains whose worker-thread pass has not returned yet. to_thread
        # cannot be cancelled once running: a pass that blocks inside sqlite
        # (the producing process holding a write lock, or a long backfill
        # commit at ~0.75 headers/second) would otherwise stall the whole
        # loop — every later chain's phases go silent with nothing logged,
        # which is how a relay phase can never fire while the loop looks
        # healthy. Each pass gets ``bridge_finalizer_pass_timeout`` seconds;
        # on timeout the worker is abandoned (marked in-flight so passes for
        # the same chain never stack) and the loop moves on to the next chain.
        pass_timeout = float(getattr(settings, "bridge_finalizer_pass_timeout", 900))
        inflight = getattr(self, "_finalizer_inflight", None)
        if inflight is None:
            self._finalizer_inflight: set[str] = set()
            inflight = self._finalizer_inflight
        while True:
            try:
                for chain_id in self._known_chains():
                    if chain_id in inflight:
                        logger.debug(
                            "Bridge finalizer pass for chain %s still running in a worker thread; skipping",
                            chain_id,
                        )
                        continue
                    inflight.add(chain_id)

                    def _run(cid: str = chain_id) -> None:
                        # The mark is cleared inside the worker so it is
                        # released when the pass actually returns — not when
                        # wait_for gave up on it — which keeps two passes for
                        # the same chain from ever running concurrently.
                        try:
                            self._finalizer_pass(cid, relayer_enabled)
                        finally:
                            inflight.discard(cid)

                    # Every phase of a pass is synchronous SQLModel work, and the
                    # first pass after a restart is a backfill: one commit per
                    # block the bridge header table is behind, measured at 0.75
                    # headers/second. Called inline it never yielded, and this
                    # coroutine is started as a task during lifespan startup --
                    # so uvicorn never finished starting and the RPC socket
                    # stayed unbound for the whole backfill, while systemd
                    # reported the unit active (running) throughout.
                    #
                    # to_thread is sound here: _finalizer_pass and everything it
                    # calls are plain ``def``, and every session is opened inside
                    # the call from a NullPool engine with check_same_thread
                    # disabled, so no session or connection crosses a thread.
                    try:
                        await asyncio.wait_for(asyncio.to_thread(_run), timeout=pass_timeout)
                    except TimeoutError:
                        logger.error(
                            "Bridge finalizer pass for chain %s exceeded %ss; worker thread abandoned, other chains continue",
                            chain_id,
                            pass_timeout,
                        )
                    except Exception:
                        logger.exception("Bridge finalizer pass failed for chain %s", chain_id)
            except Exception:
                logger.exception("Bridge release finalizer loop failed")
            await asyncio.sleep(interval)

    def _finalizer_pass(self, chain_id: str, relayer_enabled: bool) -> None:
        """Run one finalizer pass for a single chain: header sync, relay, finalize."""
        if not self._chain_db_ready(chain_id):
            return
        try:
            stored = self._sync_local_chain_headers(chain_id)
            if stored:
                logger.debug("Stored %s bridge headers for chain %s", stored, chain_id)
        except Exception:
            logger.exception("Bridge header sync failed for chain %s", chain_id)
        if relayer_enabled:
            try:
                relayed = self._relay_pending_transfers(chain_id)
                if relayed:
                    logger.info("Relayed %s bridge transfers on chain %s", relayed, chain_id)
            except Exception:
                logger.exception("Bridge relayer failed for chain %s", chain_id)
        try:
            count = self._finalize_confirmed_transfers(chain_id)
            if count:
                logger.info("Finalized %s bridge transfers on chain %s", count, chain_id)
        except Exception:
            logger.exception("Bridge finalizer failed for chain %s", chain_id)

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
