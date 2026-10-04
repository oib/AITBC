"""Demote-only settlement-mark sweeper (the "lite" mark-on-seal option).

Settlement marks are written at RPC *acceptance*: ``released_at`` /
``refunded_at`` and ``status='released'|'refunded'`` go on the row as soon as
the settlement transaction enters the mempool. If the transaction is dropped
before sealing — the S-8 disease — the row keeps claiming settled forever.

This sweeper shrinks the lie window without changing the mark semantics:

* A marked leg whose stored hash is in the sealed ``transaction`` table is
  confirmed — the timestamp is normalised to the seal record's ``created_at``.
* A marked leg whose hash stays unsealed past ``_MAX_AGE_SECONDS`` (the same
  900 s threshold the ``aitbc_escrow_settlement_unlanded`` detector uses) AND
  is absent from the proposer's mempool is demoted: the timestamp is cleared
  and the row's status re-derived; when no leg remains settled the row becomes
  ``status='settlement_failed'``. "Absent from the proposer's mempool" is
  required because a local miss says nothing about the proposer — a leg that
  is merely still pending at 900 s must not be treated as dead (the mempool
  TTL is 3600 s). A failed proposer probe fails the demote closed: no leg is
  demoted on an unverified absence.
* The dead hash is *kept* on the demoted row. The C4 detector counts a stored
  hash as a claimed leg (Task 50), so the alert keeps firing until the leg is
  repaired or written off — demotion changes the row's claim, not its audit
  trail. A ``settlement_failed`` leg whose hash later seals is re-marked on a
  following tick (``*_at`` restored to the seal time, status re-derived).
* Rows that claim settled only through ``status`` (timestamps NULL, e.g.
  legacy or hand-edited rows) are swept too: a sealed leg restores the
  timestamp, an unsealed one becomes ``settlement_failed``.

Re-drive stays route-driven — the sweeper never submits. A demoted row is
re-driveable through the normal release/refund routes, which refuse v2-era
locks (sealed below ``settings.state_transition_v3_height``) with 409 so the
sweeper plus the coordinator retry paths can never replay the v2 dead-set
without an operator go.

Runs inside ``aitbc-blockchain-rpc`` next to the mempool sweeper: the service
runs ``--workers 1``, so exactly one instance sweeps each host's own escrow
table — matching the per-host truth of the marks.

Detector-consistency note: "sealed" here means a row exists in the
``transaction`` table for the hash — identical to the detector's
``SELECT 1 ... WHERE tx_hash = ?`` probe. A transaction sealed with a failed
status therefore counts as landed (the apply-side failure is a different
disease), so the sweeper and detector can never disagree about a leg.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlmodel import select

from aitbc.network import SharedHttpClient

from ..config import settings
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow, Transaction
from .escrow_routes import _CHAIN_ID, _HUB_RPC_URL

_logger = get_logger(__name__)

# The same threshold scripts/monitoring/escrow-settlements-textfile.py uses,
# so a leg the sweeper demotes is a leg the detector would also flag, and vice
# versa. Deliberately below the 3600 s mempool TTL: demotion is gated on the
# proposer-mempool probe, so a still-pending tx is never treated as dead.
_MAX_AGE_SECONDS = 900

_SETTLED_STATUSES = ("released", "refunded", "settlement_failed")


def _mark_age_seconds(mark: datetime, now: datetime) -> float:
    if mark.tzinfo is None:
        mark = mark.replace(tzinfo=UTC)
    return (now - mark).total_seconds()


async def _proposer_pending_hashes() -> set[str] | None:
    """tx_hashes currently in the proposer's mempool; ``None`` on probe failure.

    ``None`` fails the demote closed — a leg may only be presumed dead when the
    proposer's mempool was actually read and the hash was absent.
    """
    try:
        resp = await SharedHttpClient.get(f"{_HUB_RPC_URL}/mempool?chain_id={_CHAIN_ID}&limit=2000", timeout=10.0)
        if resp.status_code != 200:
            _logger.warning("settlement sweeper: proposer mempool probe returned %s", resp.status_code)
            return None
        body = resp.json() or {}
        return {str(tx.get("tx_hash")) for tx in body.get("transactions", []) if tx.get("tx_hash")}
    except Exception as e:
        _logger.warning("settlement sweeper: proposer mempool probe failed: %s", e)
        return None


def _sealed_leg_tx(session, job_id: str, tx_type: str, stored_hash: str | None) -> Transaction | None:
    """The sealed settlement tx for a leg — by stored hash, else by job.

    The job-id fallback covers rows marked without a hash (legacy marks): any
    sealed ``tx_type`` naming the job proves the leg settled.
    """
    if stored_hash:
        found: Transaction | None = session.exec(select(Transaction).where(Transaction.tx_hash == stored_hash)).first()
        if found is not None:
            return found
    for candidate in session.exec(select(Transaction).where(Transaction.type == tx_type)):
        sealed: Transaction = candidate
        if (sealed.payload or {}).get("job_id") == job_id:
            return sealed
    return None


def sweep_once(session, now: datetime, proposer_pending: set[str] | None) -> dict[str, int]:
    """Reconcile every settlement-claiming escrow row against the sealed table.

    Pure decision layer: all DB work goes through ``session`` and the caller
    supplies ``proposer_pending`` so the function is testable without HTTP.
    Returns counters for logging.
    """
    stats = {"rows": 0, "confirmed": 0, "demoted": 0, "remarked": 0}
    rows = session.exec(
        select(Escrow).where(
            (Escrow.released_at.is_not(None))  # type: ignore[union-attr]
            | (Escrow.refunded_at.is_not(None))  # type: ignore[union-attr]
            | Escrow.status.in_(_SETTLED_STATUSES)  # type: ignore[attr-defined]
        )
    ).all()
    for row in rows:
        stats["rows"] += 1
        release_tx = _sealed_leg_tx(session, row.job_id, "ESCROW_RELEASE", row.release_tx_hash)
        refund_tx = _sealed_leg_tx(session, row.job_id, "ESCROW_REFUND", row.refund_tx_hash)
        changed = False

        for leg_mark, leg_hash, leg_tx, leg_status in (
            ("released_at", "release_tx_hash", release_tx, "released"),
            ("refunded_at", "refund_tx_hash", refund_tx, "refunded"),
        ):
            mark = getattr(row, leg_mark)
            stored = getattr(row, leg_hash)
            if leg_tx is not None:
                if stored != leg_tx.tx_hash:
                    setattr(row, leg_hash, leg_tx.tx_hash)
                    changed = True
                if mark != leg_tx.created_at:
                    setattr(row, leg_mark, leg_tx.created_at)
                    changed = True
                    stats["remarked" if mark is None else "confirmed"] += 1
                continue
            # A leg is claimed by its timestamp mark or by status alone (the
            # detector claims legs the same two ways plus by stored hash). A
            # claim without a timestamp cannot prove recency, so it is stale
            # by definition — matching the detector's illegible-timestamp rule.
            claimed = mark is not None or row.status == leg_status
            stale = mark is None or _mark_age_seconds(mark, now) > _MAX_AGE_SECONDS
            if claimed and stale and proposer_pending is not None and (stored or "") not in proposer_pending:
                if mark is not None:
                    setattr(row, leg_mark, None)
                changed = True
                stats["demoted"] += 1

        if not changed:
            continue
        # Re-derive the single status from whatever legs still claim settled.
        if row.released_at is not None:
            row.status = "released"
        elif row.refunded_at is not None:
            row.status = "refunded"
        elif row.status in _SETTLED_STATUSES:
            row.status = "settlement_failed"
        session.add(row)
        session.commit()
    return stats


async def _sweep_once() -> dict[str, int]:
    proposer_pending = await _proposer_pending_hashes()
    with session_scope() as session:
        stats = sweep_once(session, datetime.now(UTC), proposer_pending)
    if stats["demoted"] or stats["remarked"] or stats["confirmed"]:
        _logger.info(
            "settlement-mark sweep: rows=%d confirmed=%d demoted=%d re-marked=%d",
            stats["rows"],
            stats["confirmed"],
            stats["demoted"],
            stats["remarked"],
        )
    return stats


async def _sweep_settlement_marks_forever() -> None:
    while True:
        await asyncio.sleep(settings.escrow_settlement_sweep_interval)
        try:
            await _sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # A sweep failure must never end the loop; the next tick retries.
            _logger.warning("Settlement-mark sweep failed: %s", e)


def start_settlement_sweeper() -> asyncio.Task[None] | None:
    """Start the demote-only sweeper, unless the interval disables it.

    Owned by the RPC app for the same reason as the mempool sweeper:
    ``aitbc-blockchain-rpc`` runs ``--workers 1``, so exactly one sweeper
    exists per host and each sweeps only its own escrow table.
    """
    if settings.escrow_settlement_sweep_interval <= 0:
        _logger.info("Settlement-mark sweeper disabled (escrow_settlement_sweep_interval <= 0)")
        return None
    from aitbc.async_tasks import create_task_with_logging

    _logger.info(
        "Settlement-mark sweeper started: max_age=%ds interval=%ds",
        _MAX_AGE_SECONDS,
        settings.escrow_settlement_sweep_interval,
    )
    return create_task_with_logging(_sweep_settlement_marks_forever(), name="settlement-mark-sweeper")
