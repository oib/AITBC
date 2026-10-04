"""Demote-only settlement-mark sweeper (the "lite" mark-on-seal option).

Settlement marks are written at RPC *acceptance*: ``released_at`` /
``refunded_at`` and ``status='released'|'refunded'`` go on the row as soon as
the settlement transaction enters the mempool. If the transaction is dropped
before sealing — the S-8 disease — the row keeps claiming settled forever.

This sweeper shrinks the lie window without changing the mark semantics:

* A marked leg whose stored hash is in the sealed ``transaction`` table is
  *verified* — the row is left exactly as it is. The sweeper never rewrites
  a healthy mark: timestamps keep the acceptance time the route recorded,
  and a stored hash that is itself sealed is never overwritten.
* A marked leg whose hash stays unsealed past ``_MAX_AGE_SECONDS`` (the same
  900 s threshold the ``aitbc_escrow_settlement_unlanded`` detector uses)
  AND is absent from the proposer's mempool is demoted: the timestamp is
  cleared and the row's status re-derived; when no leg remains settled the
  row becomes ``status='settlement_failed'``. "Absent from the proposer's
  mempool" is required because a local miss says nothing about the
  proposer — a leg that is merely still pending at 900 s must not be
  treated as dead (the mempool TTL is 3600 s). Any probe failure — non-200,
  an unreachable proposer, or a *truncated* answer (``count >= limit``,
  where a real pending tx could sit beyond the page) — fails the demote
  closed: no leg is demoted on an unverified absence.
* The dead hash is *kept* on the demoted row. The C4 detector counts a
  stored hash as a claimed leg (Task 50), so the alert keeps firing until
  the leg is repaired or written off — demotion changes the row's claim,
  not its audit trail. A demoted/unmarked leg whose hash later seals is
  *re-marked*: timestamp set to the seal record's ``created_at``, and the
  stored hash filled only when empty or itself unsealed.
* Rows that claim settled only through ``status`` (timestamps NULL) are
  swept the same way: a sealed leg re-marks them, an unsealed one becomes
  ``settlement_failed``.

Re-drive stays route-driven — the sweeper never submits. A demoted row is
re-driveable through the normal release/refund routes, which refuse v2-era
locks (sealed below ``settings.state_transition_v3_height``) with 409 so the
sweeper plus the coordinator retry paths can never replay the v2 dead-set
without an operator go.

Runs inside ``aitbc-blockchain-rpc`` next to the mempool sweeper: the service
runs ``--workers 1``, so exactly one instance sweeps each host's own escrow
table — matching the per-host truth of the marks.

Probe target: ``HUB_BLOCKCHAIN_RPC_URL`` — set on every host to the actual
hub — falling back to the route module's ``_HUB_RPC_URL``. The latter alone
is wrong on hosts whose ``HUB_RPC_URL``/``BLOCKCHAIN_RPC_URL`` point at
themselves: their local mempool is not the proposer's, and a local miss says
nothing about whether the proposer still holds the transaction.

Detector-consistency note: "sealed" here means a row exists in the
``transaction`` table for the hash — identical to the detector's
``SELECT 1 ... WHERE tx_hash = ?`` probe. A transaction sealed with a failed
status therefore counts as landed (the apply-side failure is a different
disease), so the sweeper and detector can never disagree about a leg.
"""

from __future__ import annotations

import asyncio
import os
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

_MEMPOOL_PROBE_LIMIT = 2000

_SETTLED_STATUSES = ("released", "refunded", "settlement_failed")


def _proposer_rpc_url() -> str:
    """The proposer's RPC URL: ``HUB_BLOCKCHAIN_RPC_URL`` where set, else the
    settlement routes' hub URL. ``HUB_BLOCKCHAIN_RPC_URL`` conventionally
    carries the ``/rpc`` suffix; accept a bare base URL too."""
    raw = (os.getenv("HUB_BLOCKCHAIN_RPC_URL") or "").rstrip("/")
    if not raw:
        return _HUB_RPC_URL
    return raw if raw.endswith("/rpc") else f"{raw}/rpc"


def _mark_age_seconds(mark: datetime, now: datetime) -> float:
    if mark.tzinfo is None:
        mark = mark.replace(tzinfo=UTC)
    return (now - mark).total_seconds()


async def _proposer_pending_hashes() -> set[str] | None:
    """tx_hashes currently in the proposer's mempool; ``None`` on probe failure.

    ``None`` fails the demote closed — a leg may only be presumed dead when
    the proposer's mempool was actually read completely and the hash was
    absent. A truncated answer (count at the limit) is a failure too: the
    unseen tail could hold exactly the hash being judged.
    """
    try:
        resp = await SharedHttpClient.get(
            f"{_proposer_rpc_url()}/mempool?chain_id={_CHAIN_ID}&limit={_MEMPOOL_PROBE_LIMIT}",
            timeout=10.0,
        )
        if resp.status_code != 200:
            _logger.warning("settlement sweeper: proposer mempool probe returned %s", resp.status_code)
            return None
        body = resp.json() or {}
        count = body.get("count")
        if not isinstance(count, int) or count >= _MEMPOOL_PROBE_LIMIT:
            _logger.warning(
                "settlement sweeper: proposer mempool answer truncated or malformed (count=%r)",
                count,
            )
            return None
        return {str(tx.get("tx_hash")) for tx in body.get("transactions", []) if tx.get("tx_hash")}
    except Exception as e:
        _logger.warning("settlement sweeper: proposer mempool probe failed: %s", e)
        return None


def _sealed_by_hashes(session, hashes: set[str]) -> dict[str, Transaction]:
    """One indexed probe: every stored claim hash that is actually sealed."""
    if not hashes:
        return {}
    found = session.exec(select(Transaction).where(Transaction.tx_hash.in_(hashes)))  # type: ignore[attr-defined]
    return {tx.tx_hash: tx for tx in found}


def _sealed_by_jobs(session, legs: list[tuple[str, str]]) -> dict[tuple[str, str], Transaction]:
    """One bounded probe for legs whose stored hash did not resolve: every
    sealed ``tx_type`` row for the types still in question, matched to
    ``(job_id, tx_type)`` in memory. Settlement rows are few and type-indexed,
    so one query covers all unmatched legs per tick."""
    types = {tx_type for _, tx_type in legs}
    if not types:
        return {}
    resolved: dict[tuple[str, str], Transaction] = {}
    for tx in session.exec(select(Transaction).where(Transaction.type.in_(types))):  # type: ignore[attr-defined]
        job_id = (tx.payload or {}).get("job_id")
        if isinstance(job_id, str) and (job_id, tx.type) in legs and (job_id, tx.type) not in resolved:
            resolved[(job_id, tx.type)] = tx
    return resolved


def _claiming(row: Escrow, leg_status: str, mark) -> bool:
    return mark is not None or row.status == leg_status


def sweep_once(session, now: datetime, proposer_pending: set[str] | None) -> dict[str, int]:
    """Reconcile every settlement-claiming escrow row against the sealed table.

    Pure decision layer: all DB work goes through ``session`` and the caller
    supplies ``proposer_pending`` so the function is testable without HTTP.
    Returns counters for logging.
    """
    stats = {"rows": 0, "verified": 0, "demoted": 0, "remarked": 0}
    rows = session.exec(
        select(Escrow).where(
            (Escrow.released_at.is_not(None))  # type: ignore[union-attr]
            | (Escrow.refunded_at.is_not(None))  # type: ignore[union-attr]
            | Escrow.status.in_(_SETTLED_STATUSES)  # type: ignore[attr-defined]
        )
    ).all()

    # Phase 1: batch-resolve every stored claim hash against the sealed table.
    stored_hashes = {h for r in rows for h in (r.release_tx_hash, r.refund_tx_hash) if h}
    sealed_map = _sealed_by_hashes(session, stored_hashes)

    # Phase 2: one bounded job-id probe for legs still unresolved.
    unmatched: list[tuple[str, str]] = []
    for r in rows:
        for tx_type, stored in (
            ("ESCROW_RELEASE", r.release_tx_hash),
            ("ESCROW_REFUND", r.refund_tx_hash),
        ):
            if (stored or "") not in sealed_map:
                unmatched.append((r.job_id, tx_type))
    by_job = _sealed_by_jobs(session, unmatched)

    for row in rows:
        stats["rows"] += 1
        changed = False
        for leg_mark, leg_hash, tx_type, leg_status in (
            ("released_at", "release_tx_hash", "ESCROW_RELEASE", "released"),
            ("refunded_at", "refund_tx_hash", "ESCROW_REFUND", "refunded"),
        ):
            mark = getattr(row, leg_mark)
            stored = getattr(row, leg_hash)
            stored_sealed = sealed_map.get(stored) if stored else None
            leg_tx = stored_sealed or by_job.get((row.job_id, tx_type))
            if leg_tx is not None:
                if mark is None:
                    # Re-mark only: the leg was unmarked (demoted, status-only,
                    # or hash-only claim) and its settlement is proven. Fill
                    # the hash when absent or itself unsealed — a stored hash
                    # that IS sealed is never overwritten.
                    setattr(row, leg_mark, leg_tx.created_at)
                    if stored_sealed is None and stored != leg_tx.tx_hash:
                        setattr(row, leg_hash, leg_tx.tx_hash)
                    changed = True
                    stats["remarked"] += 1
                else:
                    # Verified healthy: the mark stands and the settlement is
                    # sealed — nothing on the row is touched.
                    stats["verified"] += 1
                continue
            # Unsealed leg. Claimed by its timestamp mark or by status alone
            # (the detector's claim channels). A claim without a timestamp
            # cannot prove recency, so it is stale by definition — the
            # illegible-timestamp rule, mirrored.
            claimed = _claiming(row, leg_status, mark)
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
    if stats["demoted"] or stats["remarked"]:
        _logger.info(
            "settlement-mark sweep: rows=%d verified=%d demoted=%d re-marked=%d",
            stats["rows"],
            stats["verified"],
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
        "Settlement-mark sweeper started: max_age=%ds interval=%ds proposer=%s",
        _MAX_AGE_SECONDS,
        settings.escrow_settlement_sweep_interval,
        _proposer_rpc_url(),
    )
    return create_task_with_logging(_sweep_settlement_marks_forever(), name="settlement-mark-sweeper")
