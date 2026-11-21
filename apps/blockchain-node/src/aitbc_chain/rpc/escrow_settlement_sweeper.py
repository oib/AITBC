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
runs ``--workers N``, and the app lifespan only starts this on the worker
holding the per-host sweeper leader lock (``rpc/sweeper_leader.py``), so
exactly one instance sweeps each host's own escrow table — matching the
per-host truth of the marks.

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
import os as os
from datetime import UTC, datetime
from typing import NamedTuple as NamedTuple

from sqlmodel import select as select
from starlette.concurrency import run_in_threadpool

from aitbc.network import SharedHttpClient as SharedHttpClient
from aitbc.utils import units_to_ait

from ..config import settings
from ..contracts.escrow import (
    DEFAULT_FEE_BPS as DEFAULT_FEE_BPS,
    get_escrow_manager,
    recompute_release_proofs as recompute_release_proofs,
    row_state_for as row_state_for,
)
from ..contracts.escrow_txn import escrow_row_lock as escrow_row_lock
from ..mempool import compute_tx_hash as compute_tx_hash
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow as Escrow, Transaction as Transaction
from . import escrow_routes
from .escrow_routes import _chain_id as _chain_id, _HUB_RPC_URL as _HUB_RPC_URL
from .escrow_settlement_sweeper_scan import (
    _ChangeCandidate,
    _ESCROW_TX_TYPES as _ESCROW_TX_TYPES,
    _FeeSweepCandidate,
    _OrphanRefundCandidate,
    _MAX_AGE_SECONDS,
    _MEMPOOL_PROBE_LIMIT as _MEMPOOL_PROBE_LIMIT,
    _SETTLED_STATUSES as _SETTLED_STATUSES,
    _accumulate_escrow_leg as _accumulate_escrow_leg,
    _change_candidate_for_job as _change_candidate_for_job,
    _change_pass_dry_run,
    _change_pass_enabled,
    _claiming as _claiming,
    _count_change_pass,
    _count_fee_pass,
    _count_orphan_refund_pass,
    _escrow_legs_by_job as _escrow_legs_by_job,
    _fee_sweep_pass_dry_run,
    _fee_sweep_pass_enabled,
    _floor_eligible_job_ids,
    _mark_age_seconds as _mark_age_seconds,
    _new_leg_acc as _new_leg_acc,
    _orphan_lock_ids,
    _orphan_refund_pass_dry_run,
    _orphan_refund_pass_enabled,
    _pending_blocks_authority,
    _proposer_pending_hashes,
    _proposer_pending_txs,
    _proposer_rpc_url,
    _released_unmarked_job_ids,
    _sealed_by_hashes as _sealed_by_hashes,
    _sealed_by_jobs as _sealed_by_jobs,
    _sweep_leg as _sweep_leg,
    _sweep_reconcile_row as _sweep_reconcile_row,
    _sweep_scan as _sweep_scan,
    change_owed_candidates,
    fee_sweep_candidates,
    orphan_refund_candidates,
    sweep_once,
)

_logger = get_logger(__name__)


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

# Rotation cursor for the candidate ring: each pass examines the next
# max_jobs-sized window of floor-eligible jobs and wraps at the end, so no
# job waits more than one full cycle regardless of fleet size.
_fee_pass_watermark: str = ""

# Per-job submission backoff (D9): a deterministically rejected sweep —
# consensus refusal, recipient drift — would otherwise resubmit every tick
# forever and swamp the error metric. In-memory like the watermark: a
# restart simply retries once.
_FEE_PASS_BACKOFF_BASE_S = 60.0
_FEE_PASS_BACKOFF_MAX_S = 3600.0
_pass_submit_failures: dict[str, tuple[int, float]] = {}
# Cap on the eligible-id scan used to prune stale backoff entries (F2).
# An entry whose job is absent from the scanned set is deleted — past the
# cap a still-eligible job loses its backoff (one early retry, harmless),
# never its eligibility.
_FAILURE_PRUNE_SCAN_LIMIT = 10_000


_FEE_PASS_RESULT_LABELS = (
    "submitted",
    "dry_run",
    "deferred_custody",
    "deferred_unproven",
    "deferred_change_pending",
    "deferred_pending",
    "deferred_grace",
    "deferred_backoff",
    "skipped_floor",
    "no_row",
    "no_lock",
    "no_residue",
    "error",
)


async def _fee_sweep_pass_once(now: datetime | None = None) -> dict[str, int]:
    """One fee-residue pass. Never raises; counted in its own metric."""
    stats = dict.fromkeys(_FEE_PASS_RESULT_LABELS, 0)
    try:
        if not _fee_sweep_pass_enabled():
            return stats
        settlement_key = escrow_routes._get_settlement_key()
        settlement_address = escrow_routes._get_settlement_address()
        if not settlement_key or not settlement_address:
            # Still tick (A7c): the pass IS enabled — a keyless-enabled pass
            # that emits nothing would be invisible to the Stale alerts.
            _count_fee_pass(stats)
            return stats
        now = now or datetime.now(UTC)
        candidates, sel = await run_in_threadpool(_load_fee_candidates, now)
        for key in (
            "skipped_floor",
            "no_row",
            "no_lock",
            "no_residue",
            "deferred_grace",
            "deferred_unproven",
            "deferred_change_pending",
        ):
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
        if _pending_blocks_authority(pending, authority):
            stats["deferred_pending"] += 1
            _count_fee_pass(stats)
            return stats
        await _submit_fee_sweep_candidates(candidates, stats, _fee_sweep_pass_dry_run(), now.timestamp())
    except Exception as e:  # noqa: BLE001 - pass containment: one bad pass must not kill the sweeper
        _logger.warning("ESCROW_FEE_SWEEP pass failed: %s", e)
        stats["error"] += 1
    _count_fee_pass(stats)
    return stats


def _load_fee_candidates(now: datetime) -> tuple[list[_FeeSweepCandidate], dict[str, int]]:
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
        if _pass_submit_failures:
            # F2: drop backoff entries for jobs absent from the eligible
            # set — without this the map grows by one stale entry per
            # departed job forever. Eligible jobs inside the scan window
            # keep their backoff.
            eligible_ids = set(
                _floor_eligible_job_ids(
                    session,
                    settings.escrow_fee_sweep_pass_min_height,
                    "",
                    _FAILURE_PRUNE_SCAN_LIMIT,
                )
            )
            for stale in [j for j in _pass_submit_failures if j not in eligible_ids]:
                del _pass_submit_failures[stale]
    return candidates, sel


async def _submit_fee_sweep_candidates(
    candidates: list[_FeeSweepCandidate], stats: dict[str, int], dry_run: bool, now_ts: float
) -> None:
    for cand in candidates:
        failures, retry_at = _pass_submit_failures.get(cand.job_id, (0, 0.0))
        if now_ts < retry_at:
            stats["deferred_backoff"] += 1
            continue
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
            _pass_submit_failures.pop(cand.job_id, None)
            stats["submitted"] += 1
        else:
            # D9: exponential backoff per job — a permanently rejected
            # sweep backs off instead of resubmitting every tick.
            _pass_submit_failures[cand.job_id] = (
                failures + 1,
                now_ts + min(_FEE_PASS_BACKOFF_BASE_S * (2**failures), _FEE_PASS_BACKOFF_MAX_S),
            )
            stats["error"] += 1
        break  # at most one submission per pass


# --------------------------------------------------------------------------
# Owed-change pass (A6/F1b): the release route never signs the buyer-change
# leg in-request — it would collide on the release's own (sender, nonce)
# mempool slot, and an in-request seal-wait would out-live the caller's
# timeout (nginx 30 s / CLI 10 s vs 60 s+ block intervals) and invite a
# re-entered second submission. This pass pays the owed change instead:
#
#   - discovery is row-driven: released escrows whose refund is unmarked;
#   - owed change is derived ONLY from sealed chain legs plus the billed
#     gross the route recorded per release (A7):
#       owed = lock_units − Σbilled − Σrefund
#     (recompute_release_proofs replays the route's own fee rule per leg —
#     the sealed value must equal the recomputed release or nothing is
#     proven; legacy rows without recorded billed stay deferred_unproven);
#   - the refund is submitted only when the proposer mempool holds NO
#     authority or escrow transaction — the change leg can never share a
#     mempool window with the release or a fee sweep;
#   - the row is marked (refunded_amount/refund_tx_hash) only from a sealed
#     refund leg — heal runs first every tick, so a restart between submit
#     and seal re-drives from chain truth, not row state;
#   - it runs BEFORE the fee pass in the tick: a submitted refund lands in
#     the proposer mempool, which makes the fee pass's own pending guard
#     defer — refund and sweep are never in the mempool together.
#
# Flags: ESCROW_CHANGE_PASS_ENABLED arms it; ESCROW_CHANGE_PASS_DRY_RUN logs
# and counts without submitting. Both unset → the pass is inert.
# --------------------------------------------------------------------------

_change_pass_watermark: str = ""
_change_pass_failures: dict[str, tuple[int, float]] = {}

_CHANGE_PASS_RESULT_LABELS = (
    "submitted",
    "dry_run",
    "marked",
    "no_owed",
    "no_legs",
    "skipped_floor",
    "deferred_unproven",
    "deferred_custody",
    "deferred_pending",
    "deferred_backoff",
    "error",
)


async def _change_pass_once(now: datetime | None = None) -> dict[str, int]:
    """One owed-change pass. Never raises; counted in its own metric."""
    stats = dict.fromkeys(_CHANGE_PASS_RESULT_LABELS, 0)
    try:
        if not _change_pass_enabled():
            return stats
        settlement_key = escrow_routes._get_settlement_key()
        settlement_address = escrow_routes._get_settlement_address()
        if not settlement_key or not settlement_address:
            # Still tick (A7c): the pass IS enabled — a keyless-enabled pass
            # that emits nothing would be invisible to the Stale alerts.
            _count_change_pass(stats)
            return stats
        now = now or datetime.now(UTC)
        candidates, sel = await run_in_threadpool(_load_change_candidates, now)
        for key, n in sel.items():
            stats[key] += n
        if not candidates:
            _count_change_pass(stats)
            return stats
        pending = await _proposer_pending_txs()
        if pending is None:
            stats["deferred_pending"] += 1
            _count_change_pass(stats)
            return stats
        authority = settlement_address.lower()
        if _pending_blocks_authority(pending, authority):
            stats["deferred_pending"] += 1
            _count_change_pass(stats)
            return stats
        await _submit_change_candidates(candidates, stats, authority, _change_pass_dry_run(), now.timestamp())
    except Exception as e:  # noqa: BLE001 - pass containment: one bad pass must not kill the sweeper
        _logger.warning("ESCROW change pass failed: %s", e)
        stats["error"] += 1
    _count_change_pass(stats)
    return stats


def _load_change_candidates(now: datetime) -> tuple[list[_ChangeCandidate], dict[str, int]]:
    global _change_pass_watermark
    with session_scope() as session:
        candidates, sel, _change_pass_watermark = change_owed_candidates(
            session,
            now,
            max_jobs=settings.escrow_fee_sweep_pass_max_jobs,
            min_height=settings.escrow_fee_sweep_pass_min_height,
            after_job_id=_change_pass_watermark,
        )
        if _change_pass_failures:
            # Same prune rule as the fee pass: drop backoff entries for
            # jobs absent from the eligible (released, unmarked) set.
            eligible_ids = set(_released_unmarked_job_ids(session, "", _FAILURE_PRUNE_SCAN_LIMIT))
            for stale in [j for j in _change_pass_failures if j not in eligible_ids]:
                del _change_pass_failures[stale]
    return candidates, sel


async def _submit_change_candidates(
    candidates: list[_ChangeCandidate], stats: dict[str, int], authority: str, dry_run: bool, now_ts: float
) -> None:
    for cand in candidates:
        failures, retry_at = _change_pass_failures.get(cand.job_id, (0, 0.0))
        if now_ts < retry_at:
            stats["deferred_backoff"] += 1
            continue
        custody = await escrow_routes._escrow_custody_balance(cand.job_id)
        if custody is None or custody != cand.custody_units:
            stats["deferred_custody"] += 1
            continue
        if dry_run:
            _logger.info(
                "ESCROW change pass [dry-run] would refund job_id=%s owed=%s to %s",
                cand.job_id,
                cand.owed_units,
                cand.buyer_address,
            )
            stats["dry_run"] += 1
            continue
        # A6c: re-probe immediately before signing — the earlier check is
        # a stale snapshot by the time this candidate is reached. The
        # residual race is a route release landing between this probe and
        # the POST below; it cannot be closed by a lock around sign+POST
        # either, because _get_account_nonce reads sealed state only —
        # a second leg signed while the first is still pending would read
        # the same sealed nonce and collide anyway. Pending or probe
        # failure means no authority leg can be signed this tick — done.
        pending = await _proposer_pending_txs()
        if pending is None or _pending_blocks_authority(pending, authority):
            stats["deferred_pending"] += 1
            return
        contract_id = await escrow_routes._find_contract_id(get_escrow_manager(), cand.job_id)
        tx_hash = await escrow_routes._submit_refund_tx(
            cand.buyer_address,
            cand.provider_address,
            units_to_ait(cand.owed_units),
            cand.job_id,
            contract_id or "",
        )
        if tx_hash:
            _logger.info(
                "ESCROW change pass submitted job_id=%s owed=%s tx=%s",
                cand.job_id,
                cand.owed_units,
                tx_hash,
            )
            _change_pass_failures.pop(cand.job_id, None)
            stats["submitted"] += 1
        else:
            _change_pass_failures[cand.job_id] = (
                failures + 1,
                now_ts + min(_FEE_PASS_BACKOFF_BASE_S * (2**failures), _FEE_PASS_BACKOFF_MAX_S),
            )
            stats["error"] += 1
        break  # at most one submission per pass


# --------------------------------------------------------------------------
# Orphan tx-only lock refund pass (#2380)
#
# ``sw_job_*`` ESCROW_LOCKs have no escrow row and no job row, so the mark
# sweep, the change pass, and the fee pass all skip them — the
# ``EscrowOpenTxOnlyLock`` alert is the only witness. Past the min age with
# no settlement leg, this pass refunds the FULL lock to the buyer recorded
# as the lock's sender. Guards, all required:
#
#   - prefix-bound to ``sw_job`` job_ids — manual ``market escrow create``
#     ids are never auto-refunded (the owner may still intend to settle);
#   - exactly one sealed lock, no sealed release/refund leg, no escrow row,
#     lock height at/above max(state_transition_v3_height,
#     escrow_fee_sweep_pass_min_height) — below the v3 floor a "refund"
#     debits the settlement authority's own float, not custody;
#   - lock older than escrow_orphan_refund_pass_min_age_seconds — a live
#     shop-window job must never have its escrow pulled mid-call;
#   - custody balance must equal the lock value at submit time — anything
#     else means legs exist that the scan cannot see;
#   - the same pending-authority serialization as the change pass, and
#     _submit_refund_tx's own sealed+mempool dedup (#2376) makes a retry or
#     a concurrent route refund return the in-flight hash instead of
#     double-paying;
#   - the refund recipient is the lock sender resolved through
#     _resolve_chain_account — the node-wallet custody refusal in
#     _submit_refund_tx applies unchanged.
#
# There is no row to mark: the pass writes nothing off-chain. A sealed
# refund leg removes the job from the candidate set on the next scan, so
# restart-between-submit-and-seal re-derives from chain truth.
#
# Flags: ESCROW_ORPHAN_REFUND_PASS_ENABLED arms it;
# ESCROW_ORPHAN_REFUND_PASS_DRY_RUN logs and counts without submitting.
# --------------------------------------------------------------------------

_orphan_refund_pass_watermark: str = ""
_orphan_refund_failures: dict[str, tuple[int, float]] = {}

_ORPHAN_REFUND_RESULT_LABELS = (
    "submitted",
    "dry_run",
    "no_owed",
    "deferred_custody",
    "deferred_pending",
    "deferred_backoff",
    "error",
    # scan-side keys merged into the same stats dict
    "no_lock",
    "multi_lock",
    "settled",
    "has_row",
    "skipped_floor",
    "deferred_age",
)


async def _orphan_refund_pass_once(now: datetime | None = None) -> dict[str, int]:
    """One orphan tx-only lock refund pass. Never raises; counted in its own metric."""
    stats = dict.fromkeys(_ORPHAN_REFUND_RESULT_LABELS, 0)
    try:
        if not _orphan_refund_pass_enabled():
            return stats
        settlement_key = escrow_routes._get_settlement_key()
        settlement_address = escrow_routes._get_settlement_address()
        if not settlement_key or not settlement_address:
            _count_orphan_refund_pass(stats)
            return stats
        now = now or datetime.now(UTC)
        candidates, sel = await run_in_threadpool(_load_orphan_candidates, now)
        for key, n in sel.items():
            stats[key] += n
        if not candidates:
            _count_orphan_refund_pass(stats)
            return stats
        pending = await _proposer_pending_txs()
        if pending is None or _pending_blocks_authority(pending, settlement_address.lower()):
            stats["deferred_pending"] += 1
            _count_orphan_refund_pass(stats)
            return stats
        await _submit_orphan_candidates(
            candidates, stats, settlement_address.lower(), _orphan_refund_pass_dry_run(), now.timestamp()
        )
    except Exception as e:  # noqa: BLE001 - pass containment: one bad pass must not kill the sweeper
        _logger.warning("ESCROW orphan-refund pass failed: %s", e)
        stats["error"] += 1
    _count_orphan_refund_pass(stats)
    return stats


def _load_orphan_candidates(now: datetime) -> tuple[list[_OrphanRefundCandidate], dict[str, int]]:
    global _orphan_refund_pass_watermark
    # The floor is the higher of the v3-custody activation and the shared
    # fee-sweep floor: below v3 a refund debits the authority's float, and
    # the fee floor is the operator's own "do not touch old custody" bound.
    min_height = max(settings.state_transition_v3_height, settings.escrow_fee_sweep_pass_min_height)
    with session_scope() as session:
        candidates, sel, _orphan_refund_pass_watermark = orphan_refund_candidates(
            session,
            now,
            max_jobs=settings.escrow_orphan_refund_pass_max_jobs,
            min_age_seconds=settings.escrow_orphan_refund_pass_min_age_seconds,
            min_height=min_height,
            after_job_id=_orphan_refund_pass_watermark,
        )
        if _orphan_refund_failures:
            eligible_ids = set(_orphan_lock_ids(session, "", _FAILURE_PRUNE_SCAN_LIMIT))
            for stale in [j for j in _orphan_refund_failures if j not in eligible_ids]:
                del _orphan_refund_failures[stale]
    return candidates, sel


async def _submit_orphan_candidates(
    candidates: list[_OrphanRefundCandidate], stats: dict[str, int], authority: str, dry_run: bool, now_ts: float
) -> None:
    for cand in candidates:
        failures, retry_at = _orphan_refund_failures.get(cand.job_id, (0, 0.0))
        if now_ts < retry_at:
            stats["deferred_backoff"] += 1
            continue
        if cand.owed_units <= 0:
            stats["no_owed"] += 1
            continue
        custody = await escrow_routes._escrow_custody_balance(cand.job_id)
        if custody is None or custody != cand.custody_units:
            stats["deferred_custody"] += 1
            continue
        if dry_run:
            _logger.info(
                "ESCROW orphan-refund pass [dry-run] would refund job_id=%s owed=%s to %s",
                cand.job_id,
                cand.owed_units,
                cand.buyer_address,
            )
            stats["dry_run"] += 1
            continue
        # Same re-probe as the change pass (A6c): the pending snapshot is
        # stale by signing time; a fresh authority/escrow leg in the
        # proposer mempool means no second settlement leg this tick.
        pending = await _proposer_pending_txs()
        if pending is None or _pending_blocks_authority(pending, authority):
            stats["deferred_pending"] += 1
            return
        tx_hash = await escrow_routes._submit_refund_tx(
            cand.buyer_address,
            cand.provider_address,
            units_to_ait(cand.owed_units),
            cand.job_id,
            "",
        )
        if tx_hash:
            _logger.info(
                "ESCROW orphan-refund pass submitted job_id=%s owed=%s tx=%s",
                cand.job_id,
                cand.owed_units,
                tx_hash,
            )
            _orphan_refund_failures.pop(cand.job_id, None)
            stats["submitted"] += 1
        else:
            _orphan_refund_failures[cand.job_id] = (
                failures + 1,
                now_ts + min(_FEE_PASS_BACKOFF_BASE_S * (2**failures), _FEE_PASS_BACKOFF_MAX_S),
            )
            stats["error"] += 1
        break  # at most one submission per pass


async def _sweep_once() -> dict[str, int]:
    proposer_pending = await _proposer_pending_hashes()
    stats: dict[str, int] = {}

    def _run_mark_sweep() -> None:
        nonlocal stats
        with session_scope() as session:
            stats = sweep_once(session, datetime.now(UTC), proposer_pending)

    await run_in_threadpool(_run_mark_sweep)
    if stats["demoted"] or stats["remarked"]:
        _logger.info(
            "settlement-mark sweep: rows=%d verified=%d demoted=%d re-marked=%d",
            stats["rows"],
            stats["verified"],
            stats["demoted"],
            stats["remarked"],
        )
    # The orphan tx-only lock pass runs FIRST: it returns whole locked
    # amounts to buyers of dead sw_job_* jobs — the class no other pass can
    # see. Then the owed-change pass, then the fee-residue pass: a submitted
    # refund lands in the proposer mempool, which trips the next pass's own
    # pending guard — settlement legs can never share a mempool window (A6).
    # All passes are bounded, gated, and never in the way of the demote path
    # above — their own try/except keeps a pass failure from touching the
    # mark reconciliation's result.
    await _orphan_refund_pass_once()
    await _change_pass_once()
    await _fee_sweep_pass_once()
    return stats


async def _sweep_settlement_marks_forever() -> None:
    while True:
        await asyncio.sleep(settings.escrow_settlement_sweep_interval)
        try:
            await _sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a sweep failure must never end the loop
            _logger.warning("Settlement-mark sweep failed: %s", e)


def start_settlement_sweeper() -> asyncio.Task[None] | None:
    """Start the demote-only sweeper, unless the interval disables it.

    Owned by the RPC app for the same reason as the mempool sweeper:
    ``aitbc-blockchain-rpc`` runs ``--workers N``, and the lifespan only
    calls this on the worker holding the sweeper leader lock
    (``rpc/sweeper_leader.py``), so exactly one sweeper exists per host
    and each sweeps only its own escrow table.
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
