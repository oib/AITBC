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

import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select

from ..config import settings
from ..logger import get_logger
from ..models import CrossChainTransfer, Transaction
from .bridge_base import BridgeBase, _OPS_ERRORS
from .bridge_types import BridgeStatus

logger = get_logger(__name__)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_iso8601(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _remote_api_headers() -> dict[str, str]:
    """X-API-Key for peer rpc calls — same credential pair as the ledger client."""
    key = os.environ.get("BRIDGE_LEDGER_API_KEY") or os.environ.get("BLOCKCHAIN_RPC_API_KEY")
    return {"X-API-Key": key} if key else {}


class ChainStoreUnavailableError(RuntimeError):
    """#2510: the peer cannot read the requested chain's store right now.

    Distinct from "no evidence": callers must treat this as *unknown*, never
    as a definitive negative — the RPC route maps it to 503 so remote
    consumers keep their fail-closed ``unreachable`` verdict.
    """


class BridgeTransferReconcileMixin(BridgeBase):
    def _sealed_transfer_index(self, chain_id: str, tx_type: str, wanted: set[str]) -> dict[str, tuple[str, datetime | None]]:
        """Map ``transfer_id`` -> (tx_hash, created_at) for sealed ``tx_type`` txs on ``chain_id``.

        The ``wanted`` filter is applied in SQL (#2775): this used to load
        every sealed tx of the type — payload included — into Python and
        match ``transfer_id`` row by row, so each reconcile/backfill pass
        materialized the chain's entire bridge-tx history.
        """
        if not wanted:
            return {}
        found: dict[str, tuple[str, datetime | None]] = {}
        tid_col = Transaction.payload["transfer_id"].as_string()
        ids = sorted(wanted)
        with self._session_for(chain_id) as session:
            # Chunk the IN list — same 500 bound as _VOTE_TARGET_CHUNK, far
            # inside SQLite's variable limit on old builds.
            for i in range(0, len(ids), 500):
                rows = session.exec(
                    select(Transaction.tx_hash, Transaction.created_at, tid_col.label("transfer_id")).where(
                        Transaction.chain_id == chain_id,
                        Transaction.type == tx_type,
                        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                        tid_col.in_(ids[i : i + 500]),
                    )
                ).all()
                for tx_hash, created_at, tid in rows:
                    found[tid] = (tx_hash, created_at)
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
        released: dict[str, tuple[str | None, datetime | None]],
        refunded: dict[str, tuple[str, datetime | None]],
        now: datetime,
    ) -> tuple[str, str | None, datetime | None] | None:
        """Return (new_status, target_tx_hash, confirm_time) or None to leave the row pending."""
        tid = record.transfer_id
        if tid in released:
            tx_hash, sealed_at = released[tid]
            # #2458: confirm_time is the sealed release's timestamp — without
            # it a reconcile-completed row shows completed with a null
            # confirm_time and the pending->confirmed->completed timeline
            # cannot be reconstructed.
            return "completed", tx_hash, _aware(sealed_at)
        if tid in refunded:
            return "refunded", None, None
        if lock_state == "sealed":
            return None
        if lock_state == "rejected":
            return "failed", None, None
        locked_at = _aware(record.lock_time)
        horizon = int(getattr(settings, "bridge_reconcile_unsealed_horizon_seconds", 7200))
        if locked_at is not None and (now - locked_at).total_seconds() > horizon:
            return "failed", None, None
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

    def _evidence_for(
        self, chain_id: str, stale: list[CrossChainTransfer], deadline: float | None = None
    ) -> tuple[dict[str, tuple[str | None, datetime | None]], dict[str, tuple[str, datetime | None]]]:
        """(released, refunded) transfer_id -> (tx_hash, created_at) from sealed chain txs.

        #2486: targets without a local store fall back to the same remote
        evidence the #2469 backfill uses, so a store-less host's stale rows
        still reconcile to completed after the target chain released.
        """
        refunded = self._sealed_transfer_index(chain_id, "BRIDGE_REFUND", {r.transfer_id for r in stale})
        released: dict[str, tuple[str | None, datetime | None]] = {}
        remote: list[tuple[str, set[str]]] = []
        for target in {r.target_chain for r in stale}:
            ids = {r.transfer_id for r in stale if r.target_chain == target}
            if self._chain_db_ready(target):
                released.update(self._sealed_transfer_index(target, "BRIDGE_RELEASE", ids))
            else:
                remote.append((target, ids))
        for target, ids in remote:
            released.update(self._remote_release_evidence(target, ids, deadline))
        return released, refunded

    def _reconcile_stale_pending(self, chain_id: str, deadline: float | None = None) -> int:
        """One reconcile pass over local ``pending`` rows whose source chain is ``chain_id``."""
        if not bool(getattr(settings, "bridge_reconcile_enabled", False)):
            return 0
        dry_run = bool(getattr(settings, "bridge_reconcile_dry_run", True))
        now = datetime.now(UTC)
        changed = self._backfill_completed_confirm_times(chain_id, deadline, dry_run)
        with self._session_for(chain_id) as session:
            stale = self._stale_pending_rows(session, chain_id, now)
            if not stale:
                return changed
            released, refunded = self._evidence_for(chain_id, stale, deadline)
            for record in stale:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                lock_state = self._lock_state(session, chain_id, record)
                decision = self._reconcile_decision(record, lock_state, released, refunded, now)
                if decision is None:
                    continue
                status, target_tx, confirm_time = decision
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
                if confirm_time is not None and record.confirm_time is None:
                    record.confirm_time = confirm_time
                session.add(record)
                changed += 1
            if changed:
                session.commit()
                self._mirror_reconciled(stale)
        return changed

    def _backfill_release_evidence(
        self, rows: Sequence[CrossChainTransfer], deadline: float | None
    ) -> dict[str, tuple[str | None, datetime | None]]:
        """transfer_id -> (tx_hash, confirm_time) of sealed BRIDGE_RELEASE evidence."""
        by_target: dict[str, set[str]] = {}
        for r in rows:
            by_target.setdefault(r.target_chain, set()).add(r.transfer_id)
        evidence: dict[str, tuple[str | None, datetime | None]] = {}
        for target, ids in by_target.items():
            if deadline is not None and time.monotonic() >= deadline:
                break
            if self._chain_db_ready(target):
                for tid, hit in self._sealed_transfer_index(target, "BRIDGE_RELEASE", ids).items():
                    evidence[tid] = hit
            else:
                # #2469: no local store for the target chain — the producing
                # chain's rpc serves the same outcome remotely.
                evidence.update(self._remote_release_evidence(target, ids, deadline))
        return evidence

    def _remote_transfer_base(self, target: str) -> str | None:
        """Base URL of ``target``'s bridge API from ``CHAIN_SYNC_SOURCES``.

        The default peer fallback is not consulted — it serves this node's
        own chain, not ``target``. No mapping yields None.
        """
        from aitbc.sync import SyncSourceResolver

        sources = SyncSourceResolver(getattr(settings, "chain_sync_sources", "") or "")
        return sources.get_all_sources().get(target)

    def _remote_release_verdict(self, target: str, transfer_id: str) -> tuple[str, dict[str, Any] | None]:
        """Target chain's view of one transfer via its bridge API (#2486).

        Returns ``("released", row)`` when the peer's release-evidence route
        reports ``released:true``, ``("clear", row)`` for a definitive
        ``released:false``,
        ``("unreachable", None)`` when a mapping exists but the fetch failed,
        and ``("unconfigured", None)`` when no sync source is configured or
        remote evidence is disabled. The refund guard fails closed on
        ``unreachable`` for post-finality rows; ``unconfigured`` keeps the
        documented store-less time gates.
        """
        if not bool(getattr(settings, "bridge_reconcile_remote_evidence_enabled", True)):
            return "unconfigured", None
        base = self._remote_transfer_base(target)
        if not base:
            return "unconfigured", None
        row = self._fetch_remote_release(base, target, transfer_id)
        if row is None:
            return "unreachable", None
        if row.get("released") is True:
            return "released", row
        return "clear", row

    def _remote_release_evidence(
        self, target: str, wanted: set[str], deadline: float | None
    ) -> dict[str, tuple[str | None, datetime | None]]:
        """#2469: confirm evidence from the target chain's own bridge API.

        A node that holds no local store for ``target`` cannot read the
        sealed BRIDGE_RELEASE — but the producing chain's rpc answers
        ``GET /rpc/bridge/release/{id}`` with the same outcome (released,
        target_tx_hash, confirm_time). No mapping, an unreachable peer, or a
        ``released:false`` answer all yield no evidence; the local row keeps
        its honest NULL.
        """
        if not bool(getattr(settings, "bridge_reconcile_remote_evidence_enabled", True)):
            return {}
        base = self._remote_transfer_base(target)
        if not base:
            return {}
        evidence: dict[str, tuple[str | None, datetime | None]] = {}
        for tid in sorted(wanted):
            if deadline is not None and time.monotonic() >= deadline:
                break
            row = self._fetch_remote_release(base, target, tid)
            if row is None or row.get("released") is not True:
                continue
            confirm_time = _parse_iso8601(row.get("confirm_time"))
            tx_hash = row.get("target_tx_hash")
            if confirm_time is not None:
                evidence[tid] = (tx_hash if isinstance(tx_hash, str) else None, confirm_time)
        return evidence

    def release_evidence(self, transfer_id: str, chain_id: str | None = None) -> dict[str, Any]:
        """Authoritative release evidence for ``transfer_id`` (#2503).

        A target chain can seal the ``BRIDGE_RELEASE`` credit without ever
        holding a ``cross_chain_transfer`` row for a hub-originated transfer,
        so the row lookup alone is not authoritative — the sealed index is
        consulted as well. ``released`` is True only for a confirmed/completed
        row or a sealed release; every other outcome is a definitive negative.
        Read-only; never creates a store for ``chain_id``. Raises
        :class:`ChainStoreUnavailableError` when the store is not readable —
        "no store here" is *unknown*, not "no release" (#2510).
        """
        chain = chain_id or str(getattr(settings, "chain_id", "") or "")
        evidence: dict[str, Any] = {
            "transfer_id": transfer_id,
            "released": False,
            "status": None,
            "target_tx_hash": None,
            "confirm_time": None,
        }
        if not self._chain_db_ready(chain):
            raise ChainStoreUnavailableError(f"chain store not ready for {chain!r}")
        with self._session_for(chain) as session:
            record = session.get(CrossChainTransfer, transfer_id)
        if record is not None:
            evidence["status"] = record.status
            if record.status in ("confirmed", "completed"):
                evidence["released"] = True
                evidence["target_tx_hash"] = record.target_tx_hash
                confirm_time = _aware(record.confirm_time)
                evidence["confirm_time"] = confirm_time.isoformat() if confirm_time else None
                return evidence
            # #2509: a pending/locked copy row can lag its sealed release —
            # the status writeback may not have landed yet or was lost. The
            # sealed index stays authoritative; fall through and consult it.
        hit = self._sealed_transfer_index(chain, "BRIDGE_RELEASE", {transfer_id}).get(transfer_id)
        if hit is not None:
            tx_hash, sealed_at = hit
            aware_sealed = _aware(sealed_at)
            evidence.update(
                released=True,
                target_tx_hash=tx_hash,
                confirm_time=aware_sealed.isoformat() if aware_sealed else None,
            )
            if evidence["status"] is None:
                evidence["status"] = "completed"
        return evidence

    @staticmethod
    def _fetch_remote_release(base_url: str, target: str, transfer_id: str) -> dict[str, Any] | None:
        """GET ``{base}/rpc/bridge/release/{id}?chain_id={target}``; None on any failure.

        #2503: the release-evidence route answers 200 with a definitive
        ``released`` flag either way. A non-200 — including the route-level
        404 an unpatched peer returns for every id — stays ``unreachable``
        so an old build can never be read as "no release".
        """
        import httpx

        try:
            with httpx.Client(timeout=5.0, headers=_remote_api_headers()) as client:
                resp = client.get(
                    f"{base_url}/rpc/bridge/release/{transfer_id}",
                    params={"chain_id": target},
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:  # noqa: BLE001 - remote evidence is strictly best-effort
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _backfill_one(
        self,
        session: Any,
        record: CrossChainTransfer,
        evidence: dict[str, tuple[str | None, datetime | None]],
        dry_run: bool,
        chain_id: str,
    ) -> bool:
        """Apply the backfill to one row; returns True when the row changed."""
        hit = evidence.get(record.transfer_id)
        if hit is None:
            return False
        tx_hash, sealed_at = hit
        logger.info(
            "Bridge reconcile%s: %s completed confirm_time backfill on %s",
            " (dry-run)" if dry_run else "",
            record.transfer_id[:16],
            chain_id,
        )
        if dry_run:
            return False
        if sealed_at is not None:
            record.confirm_time = _aware(sealed_at)
        if tx_hash and not record.target_tx_hash:
            record.target_tx_hash = tx_hash
        session.add(record)
        return True

    def _backfill_completed_confirm_times(self, chain_id: str, deadline: float | None, dry_run: bool) -> int:
        """#2458: rows completed before confirm_time existed on the reconcile
        path keep ``confirm_time`` NULL forever — the pending scan never
        revisits terminal rows. Fill it (and a missing target_tx_hash) from
        the sealed BRIDGE_RELEASE evidence. Read-model fields only; the row
        status is never rewritten here.

        #2492: the local store holds rows for transfers where this chain is
        the TARGET too (the confirm/finalize path writes them locally), so
        the scan keys on involvement — ``source_chain`` OR ``target_chain``
        — not on ``source_chain`` alone. A store-less source chain (hub
        holding only bc-2) then still backfills its island->bc-2 rows,
        whose release evidence is the local sealed index. The pending
        reconcile stays source-scoped: its lock/refund evidence rules are
        only locally readable for source-side rows."""
        changed = 0
        with self._session_for(chain_id) as session:
            rows = session.exec(
                select(CrossChainTransfer).where(
                    (CrossChainTransfer.source_chain == chain_id) | (CrossChainTransfer.target_chain == chain_id),
                    CrossChainTransfer.status == "completed",
                    CrossChainTransfer.confirm_time.is_(None),  # type: ignore[union-attr]
                )
            ).all()
            if not rows:
                return 0
            evidence = self._backfill_release_evidence(rows, deadline)
            for record in rows:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                changed += self._backfill_one(session, record, evidence, dry_run, chain_id)
            if changed:
                session.commit()
                pending = getattr(self, "_pending_transfers", None) or {}
                for record in rows:
                    transfer = pending.get(record.transfer_id)
                    if transfer is not None:
                        transfer.confirm_time = _aware(record.confirm_time)
                        if record.target_tx_hash:
                            transfer.target_tx_hash = record.target_tx_hash
        return changed

    def _mirror_reconciled(self, stale: list[CrossChainTransfer]) -> None:
        """#2458: keep the in-memory cache consistent with reconciled rows —
        without this a cached ``locked`` entry keeps answering status reads
        after the DB row has gone terminal."""
        pending = getattr(self, "_pending_transfers", None) or {}
        for record in stale:
            if record.status == "pending":
                continue
            transfer = pending.get(record.transfer_id)
            if transfer is None:
                continue
            try:
                transfer.status = BridgeStatus(record.status)
            except ValueError:
                continue
            if record.target_tx_hash:
                transfer.target_tx_hash = record.target_tx_hash
            transfer.confirm_time = _aware(record.confirm_time)
