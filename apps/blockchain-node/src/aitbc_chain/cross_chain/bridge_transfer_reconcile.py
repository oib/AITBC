"""Cross-chain bridge transfer — node-local reconciler for stale ``pending`` rows (#2257).

``cross_chain_transfer`` rows are node-local: only the node that ran the
relay/finalize/refund path moves its own row, so followers keep ``pending``
forever. This phase moves a stale ``pending`` source-chain row to a terminal
state from CHAIN evidence only (sealed transactions are identical on every
node, so every host reaches the same answer). It never writes a transaction,
never touches an apply path and never rewrites a terminal row.

Rules, first match wins (default: leave ``pending``):
1. sealed ``BRIDGE_RELEASE`` for the transfer on the target chain -> ``completed``
2. sealed ``BRIDGE_REFUND`` for the transfer on the source chain -> ``refunded``
3. lock tx sealed on the source chain -> leave (honest intermediate state)
4. lock tx locally marked ``rejected``, or never sealed past the horizon -> ``failed``
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from ..config import settings
from ..logger import get_logger
from ..models import CrossChainTransfer, Transaction
from .bridge_base import BridgeBase, _OPS_ERRORS

logger = get_logger(__name__)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class BridgeTransferReconcileMixin(BridgeBase):
    def _sealed_transfer_index(self, chain_id: str, tx_type: str, wanted: set[str]) -> dict[str, str]:
        """Map ``transfer_id`` -> tx_hash for sealed ``tx_type`` txs on ``chain_id``."""
        found: dict[str, str] = {}
        with self._session_for(chain_id) as session:
            rows = session.exec(
                select(Transaction).where(
                    Transaction.chain_id == chain_id,
                    Transaction.type == tx_type,
                    Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                )
            ).all()
            for row in rows:
                payload = row.payload if isinstance(row.payload, dict) else {}
                tid = payload.get("transfer_id")
                if isinstance(tid, str) and tid in wanted:
                    found[tid] = row.tx_hash
        return found

    @staticmethod
    def _lock_state(session: Any, chain_id: str, record: CrossChainTransfer) -> str:
        """'sealed' | 'rejected' | 'unknown' for the record's lock tx on its source chain."""
        lock = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.tx_hash == (record.source_tx_hash or record.transfer_id),
            )
        ).first()
        if lock is None:
            return "unknown"
        if lock.block_height is not None:
            return "sealed"
        return "rejected" if lock.status == "rejected" else "unknown"

    def _reconcile_decision(
        self,
        record: CrossChainTransfer,
        lock_state: str,
        released: dict[str, str],
        refunded: dict[str, str],
        now: datetime,
    ) -> tuple[str, str | None] | None:
        """Return (new_status, target_tx_hash) or None to leave the row pending."""
        tid = record.transfer_id
        if tid in released:
            return "completed", released[tid]
        if tid in refunded:
            return "refunded", None
        if lock_state == "sealed":
            return None
        if lock_state == "rejected":
            return "failed", None
        locked_at = _aware(record.lock_time)
        horizon = int(getattr(settings, "bridge_reconcile_unsealed_horizon_seconds", 7200))
        if locked_at is not None and (now - locked_at).total_seconds() > horizon:
            return "failed", None
        return None

    def _reconcile_phase(self, chain_id: str, deadline: float | None) -> None:
        """Finalizer-pass entry: run the reconcile, log, never raise."""
        try:
            reconciled = self._reconcile_stale_pending(chain_id, deadline)
            if reconciled:
                logger.info("Reconciled %s stale bridge transfers on chain %s", reconciled, chain_id)
        except _OPS_ERRORS:
            logger.exception("Bridge reconcile failed for chain %s", chain_id)

    def _stale_pending_rows(self, session: Any, chain_id: str, now: datetime) -> list[CrossChainTransfer]:
        grace = int(getattr(settings, "bridge_reconcile_grace_seconds", 600))
        rows = session.exec(
            select(CrossChainTransfer).where(
                CrossChainTransfer.source_chain == chain_id,
                CrossChainTransfer.status == "pending",
            )
        ).all()
        stale = []
        for r in rows:
            locked_at = _aware(r.lock_time)
            if locked_at is None or (now - locked_at).total_seconds() > grace:
                stale.append(r)
        return stale

    def _evidence_for(self, chain_id: str, stale: list[CrossChainTransfer]) -> tuple[dict[str, str], dict[str, str]]:
        """(released, refunded) transfer_id -> tx_hash maps from sealed chain txs."""
        refunded = self._sealed_transfer_index(chain_id, "BRIDGE_REFUND", {r.transfer_id for r in stale})
        released: dict[str, str] = {}
        for target in {r.target_chain for r in stale}:
            if self._chain_db_ready(target):
                ids = {r.transfer_id for r in stale if r.target_chain == target}
                released.update(self._sealed_transfer_index(target, "BRIDGE_RELEASE", ids))
        return released, refunded

    def _reconcile_stale_pending(self, chain_id: str, deadline: float | None = None) -> int:
        """One reconcile pass over local ``pending`` rows whose source chain is ``chain_id``."""
        if not bool(getattr(settings, "bridge_reconcile_enabled", False)):
            return 0
        dry_run = bool(getattr(settings, "bridge_reconcile_dry_run", True))
        now = datetime.now(UTC)
        changed = 0
        with self._session_for(chain_id) as session:
            stale = self._stale_pending_rows(session, chain_id, now)
            if not stale:
                return 0
            released, refunded = self._evidence_for(chain_id, stale)
            for record in stale:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                lock_state = self._lock_state(session, chain_id, record)
                decision = self._reconcile_decision(record, lock_state, released, refunded, now)
                if decision is None:
                    continue
                status, target_tx = decision
                logger.info(
                    "Bridge reconcile%s: %s pending -> %s on %s",
                    " (dry-run)" if dry_run else "",
                    record.transfer_id[:16],
                    status,
                    chain_id,
                )
                if dry_run:
                    continue
                record.status = status
                if target_tx and not record.target_tx_hash:
                    record.target_tx_hash = target_tx
                session.add(record)
                changed += 1
            if changed:
                session.commit()
        return changed
