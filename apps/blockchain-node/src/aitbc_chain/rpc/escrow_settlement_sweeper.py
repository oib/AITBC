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
from typing import NamedTuple

from sqlmodel import select

from aitbc.network import SharedHttpClient

from ..config import settings
from ..contracts.escrow import settlement_legs_from_chain
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow, Transaction
from . import escrow_routes
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


# --------------------------------------------------------------------------
# Periodic fee-residue pass (Task A4)
#
# The route-emitted sweep is unreachable as built (S-12): every settlement leg
# is signed at the sealed authority nonce, so the sweep loses the mempool's
# (sender, nonce) slot to the higher-fee release, and the retry path skips
# every row with refunded_amount NULL. This pass derives the residue from
# *sealed chain legs* — never from row columns — and submits at most one
# ESCROW_FEE_SWEEP per tick, through the same _submit_fee_sweep_tx the route
# uses (dedupe, env recipient, settlement key, never raises).
#
# Safety order for each candidate job:
#   1. residue = sealed lock - Σ sealed releases - Σ sealed refunds - Σ sealed
#      sweeps; skip when <= 0 (already drained or never settled).
#   2. fee-only proof: residue must fit inside the platform fee the sealed
#      releases withheld. A release leg's on-chain value is billed*(1-r), so
#      billed reconstructs as value*10000/(10000-bps) and the withheld fee is
#      billed - value. If a refund leg is owed but evicted or unsent, custody
#      carries fee + owed change and the residue exceeds the bound — deferred,
#      never guessed. Protected rows are deferred unconditionally: the
#      energy-floor bump lets value != billed*(1-r), which makes the
#      reconstruction unreliable.
#   3. custody equality: sweep only when the derived custody balance equals
#      the residue exactly; None or a mismatch defers.
#   4. pending guard, fail closed: nothing is submitted while the proposer's
#      mempool is unprobeable or holds any tx from the settlement authority
#      or any ESCROW_* tx.
#   5. grace: the job's newest sealed leg must be older than
#      escrow_fee_sweep_pass_grace_seconds so a metered multi-leg settle is
#      never interrupted mid-flight.
#   6. height floor: a job with any settlement leg below
#      escrow_fee_sweep_pass_min_height is ignored — the pre-v11 custody
#      census is an operator decision, not this pass's business.
#
# _fee_sweep_pass_dry_run (env ESCROW_FEE_SWEEP_PASS_DRY_RUN=1) logs and
# counts every eligible job without submitting, so a first deploy can be
# read before it writes.
# --------------------------------------------------------------------------

_FEE_BPS_DEFAULT = 250  # contracts/escrow.py default_fee_rate 0.025

# Rotation cursor for the candidate ring: each pass examines the next
# max_jobs-sized window of floor-eligible jobs and wraps at the end, so no
# job waits more than one full cycle regardless of fleet size.
_fee_pass_watermark: str = ""

_ESCROW_TX_TYPES = ("ESCROW_LOCK", "ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")

_FEE_PASS_RESULT_LABELS = (
    "submitted",
    "dry_run",
    "deferred_custody",
    "deferred_unproven",
    "deferred_pending",
    "deferred_grace",
    "skipped_floor",
    "error",
)


class _FeeSweepCandidate(NamedTuple):
    job_id: str
    expected_units: int
    fee_bound_units: int


def _fee_sweep_pass_dry_run() -> bool:
    return os.getenv("ESCROW_FEE_SWEEP_PASS_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


async def _proposer_pending_txs() -> list[dict] | None:
    """Full mempool bodies from the proposer; ``None`` on probe failure.

    Sibling of _proposer_pending_hashes for callers that need sender/type,
    not just membership. Same fail-closed contract: non-200, an unreachable
    proposer, or a truncated answer all return None.
    """
    try:
        resp = await SharedHttpClient.get(
            f"{_proposer_rpc_url()}/mempool?chain_id={_CHAIN_ID}&limit={_MEMPOOL_PROBE_LIMIT}",
            timeout=10.0,
        )
        if resp.status_code != 200:
            _logger.warning("fee-sweep pass: proposer mempool probe returned %s", resp.status_code)
            return None
        body = resp.json() or {}
        count = body.get("count")
        if not isinstance(count, int) or count >= _MEMPOOL_PROBE_LIMIT:
            _logger.warning(
                "fee-sweep pass: proposer mempool answer truncated or malformed (count=%r)",
                count,
            )
            return None
        txs = body.get("transactions", [])
        return txs if isinstance(txs, list) else []
    except Exception as e:
        _logger.warning("fee-sweep pass: proposer mempool probe failed: %s", e)
        return None


def _job_escrow_legs(session, job_id: str) -> dict:
    """The job's sealed escrow txs, one bounded probe.

    Returns lock value, per-leg settlement values, swept total, the newest
    settlement-leg timestamp, and the lowest settlement-leg height. Lock and
    sweep legs are excluded from the settlement sums but counted here because
    the residue formula needs the full custody flow.
    """
    legs: dict = {
        "lock_units": 0,
        "release_values": [],
        "refund_values": [],
        "swept_units": 0,
        "latest_settlement_at": None,
        "min_settlement_height": None,
    }
    stmt = select(Transaction).where(
        Transaction.type.in_(_ESCROW_TX_TYPES),  # type: ignore[attr-defined]
        Transaction.payload["job_id"].as_string() == job_id,
    )
    for tx in session.exec(stmt):
        at = tx.created_at
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        if tx.type == "ESCROW_LOCK":
            legs["lock_units"] += tx.value or 0
            continue
        if tx.type == "ESCROW_RELEASE":
            legs["release_values"].append(tx.value or 0)
        elif tx.type == "ESCROW_REFUND":
            legs["refund_values"].append(tx.value or 0)
        elif tx.type == "ESCROW_FEE_SWEEP":
            legs["swept_units"] += tx.value or 0
        if at is not None and (legs["latest_settlement_at"] is None or at > legs["latest_settlement_at"]):
            legs["latest_settlement_at"] = at
        h = tx.block_height
        if h is not None and (legs["min_settlement_height"] is None or h < legs["min_settlement_height"]):
            legs["min_settlement_height"] = h
    return legs


def _floor_eligible_job_ids(session, min_height: int, after_job_id: str, limit: int) -> list[str]:
    """Distinct job_ids with a sealed settlement leg at or above the floor,
    job_id-ordered past ``after_job_id``, capped at ``limit``.

    Discovery runs on the tx table — the same source the residue is derived
    from — so rows that can never be candidates (every leg below the floor)
    cannot consume the per-pass cap.
    """
    jid = Transaction.payload["job_id"].as_string()
    stmt = (
        select(jid)
        .where(Transaction.type.in_(("ESCROW_RELEASE", "ESCROW_REFUND")))  # type: ignore[attr-defined]
        .where(Transaction.block_height.is_not(None))  # type: ignore[union-attr]
        .where(Transaction.block_height >= min_height)  # type: ignore[operator]
    )
    if after_job_id:
        stmt = stmt.where(jid > after_job_id)
    stmt = stmt.distinct().order_by(jid).limit(limit)
    return [str(j) for j in session.exec(stmt) if j]


def fee_sweep_candidates(
    session,
    now: datetime,
    *,
    max_jobs: int,
    grace_seconds: int,
    min_height: int,
    after_job_id: str = "",
) -> tuple[list[_FeeSweepCandidate], dict[str, int], str]:
    """Pick sweep-eligible jobs purely from sealed chain legs.

    Bounded to ``max_jobs`` floor-eligible jobs per pass, examined in
    job_id order starting after ``after_job_id`` and wrapping around — the
    watermark ring guarantees every eligible job is inspected once per
    cycle regardless of how many exist. Returns (candidates, stats,
    next_watermark). Residue and the fee-only bound are computed here;
    the custody/pending gates are async and live in _fee_sweep_pass_once.
    """
    stats = {
        "candidates": 0,
        "no_residue": 0,
        "skipped_floor": 0,
        "deferred_grace": 0,
        "deferred_unproven": 0,
    }
    ids = _floor_eligible_job_ids(session, min_height, after_job_id, max_jobs)
    if len(ids) < max_jobs and after_job_id:
        # Reached the end of the ring: wrap to the start and fill the pass.
        ids += _floor_eligible_job_ids(session, min_height, "", max_jobs - len(ids))
    next_watermark = ids[-1] if ids else ""
    rows_by_id = {
        r.job_id: r
        for r in session.exec(select(Escrow).where(Escrow.job_id.in_(ids))).all()  # type: ignore[attr-defined]
    }
    candidates: list[_FeeSweepCandidate] = []
    for job_id in ids:
        row = rows_by_id.get(job_id)
        if row is None:
            continue  # chain legs without an escrow row — nothing to bound by
        legs = _job_escrow_legs(session, job_id)
        # Mixed-height jobs can surface here via a post-floor leg — a job
        # with ANY settlement leg below the floor stays off-limits.
        if legs["min_settlement_height"] is None or legs["min_settlement_height"] < min_height:
            stats["skipped_floor"] += 1
            continue
        latest = legs["latest_settlement_at"]
        if latest is not None and (now - latest).total_seconds() < grace_seconds:
            stats["deferred_grace"] += 1
            continue
        # Sealed-legs oracle for the settlement sums (never row columns).
        chain_legs = settlement_legs_from_chain(session, job_id) or {}
        expected = (
            legs["lock_units"]
            - int(chain_legs.get("released_amount") or 0)
            - int(chain_legs.get("refunded_amount") or 0)
            - legs["swept_units"]
        )
        if expected <= 0:
            stats["no_residue"] += 1
            continue
        # Fee-only proof: reconstruct each release's billed gross and bound
        # the withheld platform fee. Anything the bound cannot explain is
        # owed change or a non-standard fee path — defer, never guess.
        bps = row.energy_fee_basis_points if row.energy_fee_basis_points is not None else _FEE_BPS_DEFAULT
        provable = not row.protected and 0 < bps < 10000
        fee_bound = 0
        billed_total = 0
        if provable:
            denom = 10000 - bps
            for value in legs["release_values"]:
                # value = billed*(1-r) must invert integrally: a non-integral
                # reconstruction means the leg did not follow the route's
                # fee split (floor bump, foreign submission) — unprovable.
                if value <= 0 or (value * 10000) % denom != 0:
                    provable = False
                    break
                billed = (value * 10000) // denom
                billed_total += billed
                fee_bound += billed - value
            if billed_total > legs["lock_units"]:
                provable = False
        if not provable or expected > fee_bound:
            stats["deferred_unproven"] += 1
            continue
        candidates.append(_FeeSweepCandidate(job_id, expected, fee_bound))
        stats["candidates"] += 1
    return candidates, stats, next_watermark


async def _fee_sweep_pass_once(now: datetime | None = None) -> dict[str, int]:
    """One fee-residue pass. Never raises; counted in its own metric."""
    stats = dict.fromkeys(_FEE_PASS_RESULT_LABELS, 0)
    try:
        if not escrow_routes._fee_sweep_enabled():
            return stats
        settlement_key = escrow_routes._get_settlement_key()
        settlement_address = escrow_routes._get_settlement_address()
        if not settlement_key or not settlement_address:
            return stats
        now = now or datetime.now(UTC)
        global _fee_pass_watermark
        with session_scope() as session:
            candidates, sel, _fee_pass_watermark = fee_sweep_candidates(
                session,
                now,
                max_jobs=settings.escrow_fee_sweep_pass_max_jobs,
                grace_seconds=settings.escrow_fee_sweep_pass_grace_seconds,
                min_height=settings.escrow_fee_sweep_pass_min_height,
                after_job_id=_fee_pass_watermark,
            )
        for key in ("skipped_floor", "deferred_grace", "deferred_unproven"):
            stats[key] += sel[key]
        if not candidates:
            _count_fee_pass(stats)
            return stats
        pending = await _proposer_pending_txs()
        if pending is None:
            stats["deferred_pending"] += 1
            _count_fee_pass(stats)
            return stats
        authority = settlement_address.lower()
        # Mempool entries are the submitted tx dicts verbatim — the sender key
        # is "from" (mempool._tx_sender accepts "from" or "sender"); reading
        # "sender" alone matches nothing real.
        if any(
            str(tx.get("from") or tx.get("sender") or "").lower() == authority
            or str(tx.get("type") or "").startswith("ESCROW_")
            for tx in pending
        ):
            stats["deferred_pending"] += 1
            _count_fee_pass(stats)
            return stats
        dry_run = _fee_sweep_pass_dry_run()
        for cand in candidates:
            custody = await escrow_routes._escrow_custody_balance(cand.job_id)
            if custody is None or custody != cand.expected_units:
                stats["deferred_custody"] += 1
                continue
            if dry_run:
                _logger.info(
                    "ESCROW_FEE_SWEEP pass [dry-run] would sweep job_id=%s residue=%s (fee bound %s)",
                    cand.job_id,
                    cand.expected_units,
                    cand.fee_bound_units,
                )
                stats["dry_run"] += 1
                continue
            tx_hash = await escrow_routes._submit_fee_sweep_tx(cand.job_id, cand.job_id, cand.expected_units)
            if tx_hash:
                _logger.info(
                    "ESCROW_FEE_SWEEP pass submitted job_id=%s residue=%s tx=%s",
                    cand.job_id,
                    cand.expected_units,
                    tx_hash,
                )
                stats["submitted"] += 1
            else:
                stats["error"] += 1
            break  # at most one submission per pass
    except Exception as e:
        _logger.warning("ESCROW_FEE_SWEEP pass failed: %s", e)
        stats["error"] += 1
    _count_fee_pass(stats)
    return stats


def _count_fee_pass(stats: dict[str, int]) -> None:
    try:
        from ..metrics import escrow_fee_sweep_pass_total

        for result, n in stats.items():
            if n:
                escrow_fee_sweep_pass_total.labels(result=result).inc(n)
    except Exception:  # metrics must never break the pass
        pass


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
    # The fee-residue pass shares this tick: bounded, gated, and never in the
    # way of the demote path above — its own try/except keeps a pass failure
    # from touching the mark reconciliation's result.
    await _fee_sweep_pass_once()
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
