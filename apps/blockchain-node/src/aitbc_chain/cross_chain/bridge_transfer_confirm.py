"""Cross-chain bridge transfer — Confirm/refund/release flows, batch confirm, and transfer queries."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select


from ..config import settings
from ..logger import get_logger
from ..models import Account, CrossChainTransfer, Transaction
from .bridge_base import BridgeBase, _OPS_ERRORS
from .bridge_types import BridgeStatus, BridgeTransfer

logger = get_logger(__name__)


class BridgeTransferConfirmMixin(BridgeBase):
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

    def _resolve_confirm_record(
        self, session: Any, transfer_id: str, proof: dict[str, Any], target_chain: str
    ) -> tuple[CrossChainTransfer, bool]:
        """Load the target-chain transfer record for a confirm, or build it.

        Returns ``(record, proof_built_record)``. F1: the fields a release
        pays out on (amount, recipient, target chain) must come from a record
        this node wrote when it served the lock, or be bound by the proof's
        Merkle leaf. A record built from the proof alone used to be checked
        against itself. When no local record exists the lock is on another
        node; the record is materialised from the proof (v0.7.3
        mint-and-release pattern for cross-island bridges), but only
        persisted once the proof verifies.
        """
        record = session.get(CrossChainTransfer, transfer_id)
        if not record:
            record = self._lock_record_from_source(transfer_id, proof, target_chain)
        if record:
            return record, False
        proof_built_record = CrossChainTransfer(
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
        return proof_built_record, True

    def _release_nonce_for_mode(
        self, session: Any, record: CrossChainTransfer, release_amount: int, block_scoped: bool
    ) -> int:
        """Credit the recipient (and bridge release account) on the legacy path.

        Returns the nonce to anchor the release row/credit on; 0 when
        block-scoped preregistered transactions are in effect.
        """
        if block_scoped:
            return 0
        recipient_account: Account | None = session.get(Account, (record.target_chain, record.recipient))
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
        bridge_release_account: Account | None = session.get(Account, (record.target_chain, bridge_release_addr))
        if not bridge_release_account:
            bridge_release_account = Account(
                chain_id=record.target_chain, address=bridge_release_addr, balance=release_amount, nonce=0
            )
            session.add(bridge_release_account)
        release_nonce = bridge_release_account.nonce
        return release_nonce

    def _apply_legacy_release_row(
        self,
        session: Any,
        record: CrossChainTransfer,
        transfer_id: str,
        proof_hash: str,
        release_amount: int,
        release_nonce: int,
        target_tx_hash: str,
        block_scoped: bool,
    ) -> None:
        """Pre-register the signed BRIDGE_RELEASE row on the legacy path."""
        if block_scoped:
            return
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
            target_chain=record.target_chain,
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

    def _submit_release_mempool_credit(
        self,
        record: CrossChainTransfer,
        transfer_id: str,
        proof_hash: str,
        release_amount: int,
        release_nonce: int,
        target_tx_hash: str,
        block_scoped: bool,
    ) -> None:
        """Submit the signed BRIDGE_RELEASE credit to the mempool (block-scoped path)."""
        if not block_scoped:
            return
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
        self._sign_bridge_credit(credit_dict, target_tx_hash, payload=credit_payload, target_chain=record.target_chain)
        mempool.add(
            credit_dict,
            chain_id=record.target_chain,
            tx_hash=target_tx_hash,
        )

    def _mark_source_record_confirmed(
        self, record: CrossChainTransfer, transfer_id: str, target_tx_hash: str, proof_hash: str
    ) -> None:
        """Mirror the confirmed state onto the source-chain transfer record."""
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
        except (SQLAlchemyError, OSError):
            logger.exception("Failed to update source-chain bridge record for %s", transfer_id)

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
            record, proof_built_record = self._resolve_confirm_record(session, transfer_id, proof, target_chain)
            if record.status != "pending":
                raise ValueError(f"Transfer already processed: {record.status}")
            if not self._validate_proof(proof, record, require_leaf_binding=proof_built_record):
                raise ValueError("Invalid transfer proof")
            session.add(record)
            # GAP-47: cross-chain swaps may release a converted amount that
            # differs from the locked amount; plain bridges release `amount`.
            release_amount = record.release_amount if record.release_amount is not None else record.amount
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            release_nonce = self._release_nonce_for_mode(session, record, release_amount, block_scoped)
            target_tx_hash = hashlib.sha256(f"{transfer_id}:{record.target_chain}:{int(time.time())}".encode()).hexdigest()
            self._apply_legacy_release_row(
                session, record, transfer_id, proof_hash, release_amount, release_nonce, target_tx_hash, block_scoped
            )
            self._submit_release_mempool_credit(
                record, transfer_id, proof_hash, release_amount, release_nonce, target_tx_hash, block_scoped
            )
            record.status = "confirmed"
            record.target_tx_hash = target_tx_hash
            record.proof_hash = proof_hash
            record.confirm_time = datetime.now(UTC)
            session.add(record)
            session.commit()
            self._mark_source_record_confirmed(record, transfer_id, target_tx_hash, proof_hash)
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

    def _check_refund_lock_sealed(self, session: Any, record: CrossChainTransfer, transfer_id: str) -> None:
        """#703 emission-before-seal guard: the apply-side v6 gate binds the
        refund to a SEALED BRIDGE_LOCK row — a refund emitted while its
        lock is still unsealed can never apply and strands the amount.
        """
        source_hash = (record.source_tx_hash or "").strip()
        if not source_hash:
            raise ValueError(
                f"Transfer {transfer_id} has no recorded source tx — refund refused until the lock is recorded (pre-#669 row)"
            )
        lock_tx = session.exec(
            select(Transaction).where(
                Transaction.chain_id == record.source_chain,
                Transaction.tx_hash == source_hash,
            )
        ).first()
        if lock_tx is None or lock_tx.block_height is None:
            height = lock_tx.block_height if lock_tx else "unsealed"
            raise ValueError(
                f"Lock {source_hash} not yet sealed (height {height}) — refund refused; retry after the lock seals"
            )

    def _check_refund_delay(self, record: CrossChainTransfer) -> None:
        """Enforce ``bridge_refund_delay_seconds`` since the lock was recorded."""
        refund_delay = getattr(settings, "bridge_refund_delay_seconds", 0)
        if refund_delay:
            lock_time = record.lock_time or record.confirm_time or datetime.now(UTC)
            elapsed = (datetime.now(UTC) - lock_time).total_seconds()
            if elapsed < refund_delay:
                raise ValueError(f"Refund not allowed yet: {elapsed:.0f}s since lock, minimum delay is {refund_delay}s")

    def _refund_credit_legacy_nonce(self, session: Any, record: CrossChainTransfer, block_scoped: bool) -> int:
        """Return the locked amount to the sender on the legacy path.

        The fee was already deducted at lock time. Returns the nonce to
        anchor the refund row/credit on; 0 when block-scoped preregistered
        transactions are in effect.
        """
        if block_scoped:
            return 0
        sender_account: Account | None = session.get(Account, (record.source_chain, record.sender))
        if not sender_account:
            sender_account = Account(chain_id=record.source_chain, address=record.sender, balance=0, nonce=0)
            session.add(sender_account)
        sender_account.balance += record.amount
        refund_nonce = sender_account.nonce
        sender_account.nonce += 1
        session.add(sender_account)
        return refund_nonce

    def _apply_legacy_refund_row(
        self,
        session: Any,
        record: CrossChainTransfer,
        transfer_id: str,
        refund_tx_hash: str,
        refund_nonce: int,
        block_scoped: bool,
    ) -> None:
        """Pre-register the signed BRIDGE_REFUND row on the legacy path."""
        if block_scoped:
            return
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
            target_chain=record.source_chain,
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

    def _submit_refund_mempool_credit(
        self,
        record: CrossChainTransfer,
        transfer_id: str,
        refund_tx_hash: str,
        refund_nonce: int,
        block_scoped: bool,
    ) -> None:
        """Submit the signed BRIDGE_REFUND credit to the mempool (block-scoped path)."""
        if not block_scoped:
            return
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
        self._sign_bridge_credit(credit_dict, refund_tx_hash, payload=credit_payload, target_chain=record.source_chain)
        mempool.add(
            credit_dict,
            chain_id=record.source_chain,
            tx_hash=refund_tx_hash,
        )

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

            self._check_refund_lock_sealed(session, record, transfer_id)
            self._check_refund_delay(record)

            # Return the locked amount to the sender (fee was already deducted at lock time)
            block_scoped = getattr(settings, "block_scoped_preregistered_transactions", True)
            refund_nonce = self._refund_credit_legacy_nonce(session, record, block_scoped)

            # Create a BRIDGE_REFUND transaction record
            refund_tx_hash = hashlib.sha256(
                f"{transfer_id}:refund:{record.source_chain}:{int(time.time())}".encode()
            ).hexdigest()
            self._apply_legacy_refund_row(session, record, transfer_id, refund_tx_hash, refund_nonce, block_scoped)
            self._submit_refund_mempool_credit(record, transfer_id, refund_tx_hash, refund_nonce, block_scoped)
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
            except _OPS_ERRORS as e:
                logger.warning("Batch confirm failed for transfer %s: %s", transfer_id, e)
                results.append({"transfer_id": transfer_id, "error": str(e)})
        return results
