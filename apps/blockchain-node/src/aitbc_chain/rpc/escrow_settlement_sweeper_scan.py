"""Scan/decision layer for the escrow settlement sweeper (#1860 pure-move split).

``aitbc_chain.rpc.escrow_settlement_sweeper`` re-exports every name defined
here and keeps the submit/orchestration half of each pass plus the sweeper
lifecycle. The split is monkeypatch-safe: every function that reads a
module global tests patch on ``escrow_settlement_sweeper``
(``session_scope``, ``_proposer_pending_txs``, the failure dicts,
``get_escrow_manager``) stayed in that module, so ``ess.X`` patches keep
reaching the code that reads them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import NamedTuple

from sqlmodel import select

from aitbc.network import SharedHttpClient

from ..contracts.escrow import DEFAULT_FEE_BPS, recompute_release_proofs, row_state_for
from ..contracts.escrow_txn import escrow_row_lock
from ..logger import get_logger
from ..mempool import compute_tx_hash
from ..models import Escrow, Transaction
from .escrow_routes import _chain_id, _HUB_RPC_URL

# Keep the original logger name so log records are unchanged by the split.
_logger = get_logger("aitbc_chain.rpc.escrow_settlement_sweeper")


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
            f"{_proposer_rpc_url()}/mempool?chain_id={_chain_id()}&limit={_MEMPOOL_PROBE_LIMIT}",
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
        txs = body.get("transactions", [])
        if not isinstance(txs, list):
            _logger.warning("settlement sweeper: proposer mempool transactions malformed (%r)", type(txs))
            return None
        # /mempool returns each pending entry's submitted body verbatim: the
        # tx_hash is the mempool table's primary key, never a key inside the
        # body. Recompute it the way admission does (compute_tx_hash over the
        # canonical body) — the same value the submit response returned and
        # the row stored. An unhashable body must not silently empty the
        # answer to "is my leg still pending": fail closed like any other
        # unreadable probe.
        return {compute_tx_hash(tx) for tx in txs}
    except Exception as e:  # noqa: BLE001 - any RPC/parse failure alike: probe reports unreadable
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
    stats = {"rows": 0, "verified": 0, "demoted": 0, "remarked": 0, "skipped_locked": 0}
    rows, sealed_map, by_job = _sweep_scan(session)
    for row in rows:
        stats["rows"] += 1
        _sweep_reconcile_row(session, row, sealed_map, by_job, now, proposer_pending, stats)
    return stats


def _sweep_scan(session):
    """Phase 1+2 of sweep_once: the claim rows, then every stored claim hash
    resolved against the sealed table plus one bounded job-id probe for legs
    still unresolved."""
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
    return rows, sealed_map, by_job


def _sweep_reconcile_row(
    session, row: Escrow, sealed_map: dict, by_job: dict, now: datetime, proposer_pending, stats: dict
) -> None:
    # Serialise with the routes (#831): the same stripe flock the release/
    # refund path polls, then a refresh so a settlement that landed between
    # the SELECT and the lock is seen on fresh attributes. A contended row
    # is skipped this tick — the next pass catches it.
    with escrow_row_lock(session, row.job_id) as locked:
        if not locked:
            stats["skipped_locked"] += 1
            return
        session.refresh(row)
        changed = False
        for leg in (
            ("released_at", "release_tx_hash", "released_amount", "ESCROW_RELEASE", "released"),
            ("refunded_at", "refund_tx_hash", "refunded_amount", "ESCROW_REFUND", "refunded"),
        ):
            if _sweep_leg(row, leg, sealed_map, by_job, now, proposer_pending, stats):
                changed = True
        if not changed:
            return
        # Re-derive the single status from whatever legs still claim settled.
        if row.released_at is not None:
            row.status = "released"
        elif row.refunded_at is not None:
            row.status = "refunded"
        elif row.status in _SETTLED_STATUSES:
            row.status = "settlement_failed"
        # The lifecycle column follows the legs, not the status: a demoted row still
        # holds its funds (FUNDED) and a re-marked one is settled again.
        row.state = row_state_for(row.released_at, row.refunded_at)
        session.add(row)
        session.commit()


def _sweep_leg(row: Escrow, leg, sealed_map: dict, by_job: dict, now: datetime, proposer_pending, stats: dict) -> bool:
    """Reconcile one settlement leg of ``row`` against the sealed table.
    Returns True when the row was mutated (remark, amount heal, or demote)."""
    leg_mark, leg_hash, leg_amount, tx_type, leg_status = leg
    mark = getattr(row, leg_mark)
    stored = getattr(row, leg_hash)
    stored_sealed = sealed_map.get(stored) if stored else None
    leg_tx = stored_sealed or by_job.get((row.job_id, tx_type))
    if leg_tx is not None:
        mutated = False
        if mark is None:
            # Re-mark only: the leg was unmarked (demoted, status-only,
            # or hash-only claim) and its settlement is proven. Fill
            # the hash when absent or itself unsealed — a stored hash
            # that IS sealed is never overwritten.
            setattr(row, leg_mark, leg_tx.created_at)
            if stored_sealed is None and stored != leg_tx.tx_hash:
                setattr(row, leg_hash, leg_tx.tx_hash)
            stats["remarked"] += 1
            mutated = True
        else:
            # Verified healthy: the mark stands and the settlement is
            # sealed — nothing on the row is touched.
            stats["verified"] += 1
        if getattr(row, leg_amount) is None:
            # A sealed leg proves the amount too — marking only
            # time+hash leaves released rows in the change pass's
            # refunded_amount-IS-NULL scan forever, and a demote that
            # cleared the amount must heal when the leg seals.
            setattr(row, leg_amount, leg_tx.value or 0)
            mutated = True
        return mutated
    # Unsealed leg. Claimed by its timestamp mark or by status alone
    # (the detector's claim channels). A claim without a timestamp
    # cannot prove recency, so it is stale by definition — the
    # illegible-timestamp rule, mirrored.
    claimed = _claiming(row, leg_status, mark)
    stale = mark is None or _mark_age_seconds(mark, now) > _MAX_AGE_SECONDS
    if claimed and stale and proposer_pending is not None and (stored or "") not in proposer_pending:
        if mark is not None:
            setattr(row, leg_mark, None)
        if getattr(row, leg_amount) is not None:
            # The amount makes the same settlement claim as the mark:
            # a demoted leg proves it never sealed, so the amount must
            # not keep reporting money as moved (C21 I1).
            setattr(row, leg_amount, None)
        stats["demoted"] += 1
        return True
    return False


_ESCROW_TX_TYPES = ("ESCROW_LOCK", "ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")


class _FeeSweepCandidate(NamedTuple):
    job_id: str
    expected_units: int
    fee_bound_units: int


def _fee_sweep_pass_dry_run() -> bool:
    return os.getenv("ESCROW_FEE_SWEEP_PASS_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def _fee_sweep_pass_enabled() -> bool:
    """The pass's own flag, split from ``ESCROW_FEE_SWEEP_ENABLED`` (the C16
    deploy note): that flag also gates the release-route retry, so enabling it
    to observe the pass would re-arm route emission with it. The pass arms on
    ``ESCROW_FEE_SWEEP_PASS_ENABLED`` alone."""
    return os.getenv("ESCROW_FEE_SWEEP_PASS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


async def _proposer_pending_txs() -> list[dict] | None:
    """Full mempool bodies from the proposer; ``None`` on probe failure.

    Sibling of _proposer_pending_hashes for callers that need sender/type,
    not just membership. Same fail-closed contract: non-200, an unreachable
    proposer, or a truncated answer all return None.
    """
    try:
        resp = await SharedHttpClient.get(
            f"{_proposer_rpc_url()}/mempool?chain_id={_chain_id()}&limit={_MEMPOOL_PROBE_LIMIT}",
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
        txs = body.get("transactions")
        # Missing or mistyped "transactions" on a well-formed count is not an
        # empty mempool — it is an answer we cannot read; defer (C19).
        return txs if isinstance(txs, list) else None
    except Exception as e:  # noqa: BLE001 - any RPC/parse failure alike: probe reports unreadable
        _logger.warning("fee-sweep pass: proposer mempool probe failed: %s", e)
        return None


def _new_leg_acc() -> dict:
    return {
        "lock_units": 0,
        "release_values": [],
        "release_legs": [],
        "refund_values": [],
        "refund_tx_hash": None,
        "swept_units": 0,
        "latest_settlement_at": None,
        "min_settlement_height": None,
    }


def _escrow_legs_by_job(session, job_ids: list[str]) -> dict[str, dict]:
    """All candidate jobs' sealed escrow txs in one scan, grouped by job_id.

    The per-job probes this replaces were O(cap × escrow_rows): payload.job_id
    carries no index, so each job's query index-scanned the whole ESCROW type
    range — a multi-second synchronous block on the single-worker RPC loop at
    100× chain size (D4). One type-indexed scan with the job_ids matched in
    memory is O(escrow_rows) once.

    Leg membership matches settlement_legs_from_chain exactly (D6): release
    and refund *values* count only on the oracle's action names, so a leg the
    oracle would ignore can never inflate the bound side of the fee proof.
    Settlement timing and height still see every non-lock leg — a
    mismatched-action leg is settlement activity for floor/grace purposes
    either way.
    """
    wanted = set(job_ids)
    jid = Transaction.payload["job_id"].as_string()
    stmt = select(Transaction).where(
        Transaction.type.in_(_ESCROW_TX_TYPES),  # type: ignore[attr-defined]
        jid.in_(wanted),
    )
    by_job: dict[str, dict] = {}
    for tx in session.exec(stmt):
        job_id = (tx.payload or {}).get("job_id")
        if not isinstance(job_id, str) or job_id not in wanted:
            continue
        legs = by_job.setdefault(job_id, _new_leg_acc())
        _accumulate_escrow_leg(legs, tx)
    return by_job


def _accumulate_escrow_leg(legs: dict, tx: Transaction) -> None:
    at = tx.created_at
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if tx.type == "ESCROW_LOCK":
        legs["lock_units"] += tx.value or 0
        return
    action = (tx.payload or {}).get("action")
    if tx.type == "ESCROW_RELEASE" and action == "escrow_release":
        legs["release_values"].append(tx.value or 0)
        legs["release_legs"].append({"tx_hash": tx.tx_hash, "value": tx.value or 0})
    elif tx.type == "ESCROW_REFUND" and action == "escrow_refund":
        legs["refund_values"].append(tx.value or 0)
        if tx.tx_hash:
            legs["refund_tx_hash"] = tx.tx_hash
    elif tx.type == "ESCROW_FEE_SWEEP":
        legs["swept_units"] += tx.value or 0
    if at is not None and (legs["latest_settlement_at"] is None or at > legs["latest_settlement_at"]):
        legs["latest_settlement_at"] = at
    h = tx.block_height
    if h is not None and (legs["min_settlement_height"] is None or h < legs["min_settlement_height"]):
        legs["min_settlement_height"] = h


def _floor_eligible_job_ids(
    session,
    min_height: int,
    after_job_id: str,
    limit: int,
    through_job_id: str | None = None,
) -> list[str]:
    """Distinct job_ids with a sealed settlement leg at or above the floor,
    job_id-ordered past ``after_job_id``, capped at ``limit``.

    ``through_job_id`` bounds the window from above (inclusive) — the ring's
    wrap-around refill uses it so a job sitting past the watermark is never
    returned twice by the two halves of one pass (D1).

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
    if through_job_id is not None:
        stmt = stmt.where(jid <= through_job_id)
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
        "no_row": 0,
        "no_lock": 0,
        "deferred_grace": 0,
        "deferred_unproven": 0,
        "deferred_change_pending": 0,
    }
    ids = _floor_eligible_job_ids(session, min_height, after_job_id, max_jobs)
    if len(ids) < max_jobs and after_job_id:
        # Reached the end of the ring: wrap to the start and fill the pass,
        # bounded above by the watermark so nothing is examined twice (D1).
        ids += _floor_eligible_job_ids(session, min_height, "", max_jobs - len(ids), through_job_id=after_job_id)
    next_watermark = ids[-1] if ids else ""
    rows_by_id = {
        r.job_id: r
        for r in session.exec(select(Escrow).where(Escrow.job_id.in_(ids))).all()  # type: ignore[attr-defined]
    }
    legs_by_id = _escrow_legs_by_job(session, ids)
    candidates: list[_FeeSweepCandidate] = []
    for job_id in ids:
        row = rows_by_id.get(job_id)
        if row is None:
            # Chain legs without an escrow row are invisible without a stat —
            # a rebuilt node's whole history reads that way (D3).
            stats["no_row"] += 1
            continue
        legs = legs_by_id.get(job_id) or _new_leg_acc()
        # Mixed-height jobs can surface here via a post-floor leg — a job
        # with ANY settlement leg below the floor stays off-limits.
        if legs["min_settlement_height"] is None or legs["min_settlement_height"] < min_height:
            stats["skipped_floor"] += 1
            continue
        if legs["lock_units"] <= 0:
            # Settlement legs but no ESCROW_LOCK-type leg (foreign-typed lock,
            # import anomaly) — previously read as a silent no_residue (D5).
            stats["no_lock"] += 1
            continue
        latest = legs["latest_settlement_at"]
        if latest is not None and (now - latest).total_seconds() < grace_seconds:
            stats["deferred_grace"] += 1
            continue
        # The release/refund value lists are action-matched (D6), so their
        # sums are exactly what the settlement oracle reports — never row
        # columns.
        expected = legs["lock_units"] - sum(legs["release_values"]) - sum(legs["refund_values"]) - legs["swept_units"]
        if expected <= 0:
            stats["no_residue"] += 1
            continue
        # Fee-only proof (A7): recompute the route's own fee rule from the
        # billed gross it recorded per release leg — the inversion this
        # replaces could never prove protected bumps or floor-rounded
        # billings. Anything the recompute cannot match defers, never guesses.
        bps = row.energy_fee_basis_points if row.energy_fee_basis_points is not None else DEFAULT_FEE_BPS
        proof = recompute_release_proofs(
            legs["release_legs"],
            row.billed_legs,
            fee_bps=bps,
            protected=bool(row.protected),
            credit_units=row.energy_provider_credit_units,
            net_floor_units=row.energy_net_floor_units,
            lock_units=legs["lock_units"],
        )
        fee_bound = proof[1] if proof else None
        if fee_bound is None:
            stats["deferred_unproven"] += 1
            continue
        if expected > fee_bound:
            # The proof holds but custody carries more than the withheld
            # fee: the excess is owed change the change pass has not paid
            # (or a legacy row it cannot prove). Provable, just not
            # sweepable — "unproven" would alert on a healthy transient row.
            stats["deferred_change_pending"] += 1
            continue
        candidates.append(_FeeSweepCandidate(job_id, expected, fee_bound))
        stats["candidates"] += 1
    return candidates, stats, next_watermark


def _pending_blocks_authority(pending: list[dict], authority: str) -> bool:
    # Mempool entries are the submitted tx dicts verbatim — the sender key
    # is "from" (mempool._tx_sender accepts "from" or "sender"); reading
    # "sender" alone matches nothing real.
    return any(
        str(tx.get("from") or tx.get("sender") or "").lower() == authority or str(tx.get("type") or "").startswith("ESCROW_")
        for tx in pending
    )


def _count_fee_pass(stats: dict[str, int]) -> None:
    try:
        from ..metrics import escrow_fee_sweep_pass_total

        # Heartbeat: one "tick" per executed pass run — an idle pass still
        # proves it is alive; its absence means dead or flag-disabled.
        escrow_fee_sweep_pass_total.labels(result="tick").inc()
        for result, n in stats.items():
            if n:
                escrow_fee_sweep_pass_total.labels(result=result).inc(n)
    except Exception as e:  # noqa: BLE001 - metrics must never break the pass
        _logger.debug("fee-sweep metrics emit failed: %s", e)


class _ChangeCandidate(NamedTuple):
    job_id: str
    buyer_address: str
    provider_address: str
    owed_units: int
    custody_units: int


def _change_pass_enabled() -> bool:
    return os.getenv("ESCROW_CHANGE_PASS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _change_pass_dry_run() -> bool:
    return os.getenv("ESCROW_CHANGE_PASS_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def _released_unmarked_job_ids(session, after_job_id: str, limit: int, through_job_id: str | None = None) -> list[str]:
    """job_ids of released escrows whose refund is still unmarked, ordered.

    Same ring mechanics as the fee pass's floor-eligible scan: the watermark
    bounds the window so every row is inspected once per cycle.
    """
    stmt = (
        select(Escrow.job_id)
        .where(Escrow.released_at.is_not(None))  # type: ignore[union-attr]
        .where(Escrow.refunded_amount.is_(None))  # type: ignore[union-attr]
    )
    if after_job_id:
        stmt = stmt.where(Escrow.job_id > after_job_id)
    if through_job_id is not None:
        stmt = stmt.where(Escrow.job_id <= through_job_id)
    stmt = stmt.order_by(Escrow.job_id).limit(limit)
    return [jid for jid in session.exec(stmt) if isinstance(jid, str)]


def change_owed_candidates(
    session,
    now: datetime,
    *,
    max_jobs: int,
    min_height: int,
    after_job_id: str = "",
) -> tuple[list[_ChangeCandidate], dict[str, int], str]:
    """Pick released rows with provable owed change, from sealed legs only.

    Owed = lock − Σbilled − Σrefund, with billed proven per release leg by
    ``recompute_release_proofs`` (A7 — the recorded-billed recompute, not the
    old inversion). Rows without recorded billed, unpaired legs, or a
    recompute mismatch defer unproven. A sealed refund leg heals the row
    mark here — marking off chain truth, so a crash between submission and
    seal re-derives correctly on restart.
    Returns (candidates, stats, next_watermark).
    """
    stats = {
        "marked": 0,
        "no_owed": 0,
        "no_legs": 0,
        "skipped_floor": 0,
        "deferred_unproven": 0,
    }
    ids = _released_unmarked_job_ids(session, after_job_id, max_jobs)
    if len(ids) < max_jobs and after_job_id:
        ids += _released_unmarked_job_ids(session, "", max_jobs - len(ids), through_job_id=after_job_id)
    next_watermark = ids[-1] if ids else ""
    rows_by_id = {
        r.job_id: r
        for r in session.exec(select(Escrow).where(Escrow.job_id.in_(ids))).all()  # type: ignore[attr-defined]
    }
    legs_by_id = _escrow_legs_by_job(session, ids)
    candidates: list[_ChangeCandidate] = []
    for job_id in ids:
        row = rows_by_id.get(job_id)
        if row is None:
            continue
        legs = legs_by_id.get(job_id) or _new_leg_acc()
        candidate = _change_candidate_for_job(session, job_id, row, legs, min_height, stats)
        if candidate is not None:
            candidates.append(candidate)
    return candidates, stats, next_watermark


def _change_candidate_for_job(session, job_id: str, row: Escrow, legs: dict, min_height: int, stats: dict[str, int]):
    # Same floor rule as the fee pass: ANY settlement leg below the
    # floor (a reused id's old era) poisons the derivation — skip.
    if legs["min_settlement_height"] is None:
        stats["no_legs"] += 1
        return None
    if legs["min_settlement_height"] < min_height:
        stats["skipped_floor"] += 1
        return None
    # Heal first: a sealed refund leg marks the row regardless of where
    # the submission came from. refunded_at stays unset — on a released
    # escrow it means "refunded instead of released" (route semantics).
    # The commit is explicit: session_scope is a plain autocommit=False
    # session, so without it the mark rolls back at scope exit and the
    # row is re-found (and re-counted) every tick (A6b).
    refund_total = sum(legs["refund_values"])
    if legs["refund_tx_hash"] and (row.refund_tx_hash != legs["refund_tx_hash"] or row.refunded_amount != refund_total):
        # The mark-sweeper's own heal only writes refunded_at and the
        # hash — a row it stamped keeps refunded_amount NULL and would
        # re-enter this scan every cycle forever. Amount must equal the
        # sealed sum before the row counts as marked.
        row.refunded_amount = refund_total
        row.refund_tx_hash = legs["refund_tx_hash"]
        session.add(row)
        session.commit()
        stats["marked"] += 1
        return None
    if legs["lock_units"] <= 0 or not legs["release_values"]:
        # No lock, or no sealed provider release: the row's released_at
        # claim has no chain truth behind it (a dead release mark, or a
        # foreign/mistyped settlement leg feeding min_settlement_height).
        # Owed change only exists once the provider was actually paid —
        # refunding ≈lock here would race the release re-drive (C19).
        stats["no_legs"] += 1
        return None
    # A7: owed = lock − billed − refunded, with billed proven by the
    # recompute (never by inversion and never by row columns alone).
    bps = row.energy_fee_basis_points if row.energy_fee_basis_points is not None else DEFAULT_FEE_BPS
    proof = recompute_release_proofs(
        legs["release_legs"],
        row.billed_legs,
        fee_bps=bps,
        protected=bool(row.protected),
        credit_units=row.energy_provider_credit_units,
        net_floor_units=row.energy_net_floor_units,
        lock_units=legs["lock_units"],
    )
    if proof is None:
        stats["deferred_unproven"] += 1
        return None
    billed_total = proof[0]
    owed = legs["lock_units"] - billed_total - sum(legs["refund_values"])
    if owed <= 0:
        stats["no_owed"] += 1
        return None
    custody = legs["lock_units"] - sum(legs["release_values"]) - sum(legs["refund_values"]) - legs["swept_units"]
    if owed > custody:
        # Owed exceeds what custody holds — the chain would refuse the
        # refund anyway, so never sign it; this shape means a leg is
        # missing or the row/legs disagree and needs eyes, not backoff.
        stats["deferred_unproven"] += 1
        return None
    return _ChangeCandidate(job_id, row.buyer, row.provider, owed, custody)


def _count_change_pass(stats: dict[str, int]) -> None:
    try:
        from ..metrics import escrow_change_pass_total

        # Heartbeat: one "tick" per executed pass run (see _count_fee_pass).
        escrow_change_pass_total.labels(result="tick").inc()
        for result, n in stats.items():
            if n:
                escrow_change_pass_total.labels(result=result).inc(n)
    except Exception as e:  # noqa: BLE001 - metrics must never break the pass
        _logger.debug("change-pass metrics emit failed: %s", e)


# --------------------------------------------------------------------------
# Orphan tx-only lock refund pass (#2380)
#
# ``sw_job_*`` ESCROW_LOCKs are minted by the shop-window CLI flows before the
# provider call and deliberately carry no market/coordinator job row and no
# escrow row — the same set ``aitbc_escrow_open_tx_only_lock`` alerts on. A
# provider-call failure (or a killed session) strands the lock: nothing
# selects it, nothing settles it, and the 30-day contract expiry nothing
# invokes is the only other exit. The inline ``_refund_orphaned_escrow``
# (#1767) dies with the session that hit the failure.
#
# This pass refunds the full lock to the recorded buyer once the lock is
# older than the min age and still has no settlement leg and no escrow row.
# Scope is deliberately prefix-bound to ``sw_job``: arbitrary manual
# ``market escrow create`` ids are NOT auto-refunded — a user may intend to
# settle them later. The prefix is the class whose rows provably never exist.
#
# Pure decision layer like the other passes: all DB work goes through
# ``session``; custody/pending probes and submission live in the sweeper
# module. Flags: ESCROW_ORPHAN_REFUND_PASS_ENABLED arms it,
# ESCROW_ORPHAN_REFUND_PASS_DRY_RUN logs and counts without submitting.
# --------------------------------------------------------------------------

_ORPHAN_JOB_PREFIX = "sw_job"


def _orphan_refund_pass_enabled() -> bool:
    return os.getenv("ESCROW_ORPHAN_REFUND_PASS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _orphan_refund_pass_dry_run() -> bool:
    return os.getenv("ESCROW_ORPHAN_REFUND_PASS_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


class _OrphanRefundCandidate(NamedTuple):
    job_id: str
    buyer_address: str
    provider_address: str
    owed_units: int
    custody_units: int


def _orphan_lock_ids(session, after_job_id: str, limit: int, through_job_id: str | None = None) -> list[str]:
    """Distinct ``sw_job*`` job_ids with a sealed ESCROW_LOCK, job_id-ordered.

    Same ring mechanics as the other passes: ``after_job_id`` bounds the
    window, ``through_job_id`` caps the wrap-around refill so nothing is
    examined twice in one pass.
    """
    jid = Transaction.payload["job_id"].as_string()
    stmt = (
        select(jid)
        .where(Transaction.type == "ESCROW_LOCK")
        .where(jid.like(f"{_ORPHAN_JOB_PREFIX}%"))
        .where(Transaction.block_height.is_not(None))  # type: ignore[union-attr]
    )
    if after_job_id:
        stmt = stmt.where(jid > after_job_id)
    if through_job_id is not None:
        stmt = stmt.where(jid <= through_job_id)
    stmt = stmt.distinct().order_by(jid).limit(limit)
    return [str(j) for j in session.exec(stmt) if j]


def orphan_refund_candidates(
    session,
    now: datetime,
    *,
    max_jobs: int,
    min_age_seconds: int,
    min_height: int,
    after_job_id: str = "",
) -> tuple[list[_OrphanRefundCandidate], dict[str, int], str]:
    """Pick orphan tx-only locks eligible for a full buyer refund.

    A job qualifies only when its single sealed ESCROW_LOCK is at or above
    ``min_height`` (the v3-custody floor — below it a refund debits the
    settlement authority's own float, not custody), older than
    ``min_age_seconds``, and has no sealed ESCROW_RELEASE/ESCROW_REFUND leg
    and no escrow row. Multiple locks on one job_id are ambiguous — skip.
    Returns (candidates, stats, next_watermark).
    """
    stats = {
        "no_lock": 0,
        "multi_lock": 0,
        "settled": 0,
        "has_row": 0,
        "skipped_floor": 0,
        "deferred_age": 0,
    }
    wanted = _orphan_lock_ids(session, after_job_id, max_jobs)
    if len(wanted) < max_jobs and after_job_id:
        wanted += _orphan_lock_ids(session, "", max_jobs - len(wanted), through_job_id=after_job_id)
    next_watermark = wanted[-1] if wanted else ""
    if not wanted:
        return [], stats, next_watermark
    wanted_set = set(wanted)

    # One type-indexed scan for every escrow tx naming a candidate job —
    # same shape as _escrow_legs_by_job, matched in memory.
    jid = Transaction.payload["job_id"].as_string()
    locks: dict[str, list[Transaction]] = {}
    settled: set[str] = set()
    for tx in session.exec(
        select(Transaction).where(
            Transaction.type.in_(("ESCROW_LOCK", "ESCROW_RELEASE", "ESCROW_REFUND")),  # type: ignore[attr-defined]
            jid.in_(wanted_set),
        )
    ):
        job_id = (tx.payload or {}).get("job_id")
        if job_id not in wanted_set:
            continue
        if tx.type == "ESCROW_LOCK":
            locks.setdefault(job_id, []).append(tx)
        else:
            settled.add(job_id)

    row_ids = {
        r
        for r in session.exec(select(Escrow.job_id).where(Escrow.job_id.in_(wanted_set)))  # type: ignore[attr-defined]
        if isinstance(r, str)
    }

    candidates: list[_OrphanRefundCandidate] = []
    for job_id in wanted:
        candidate = _orphan_candidate_for_job(
            job_id, locks.get(job_id) or [], settled, row_ids, now, min_age_seconds, min_height, stats
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates, stats, next_watermark


def _orphan_candidate_for_job(
    job_id: str,
    job_locks: list[Transaction],
    settled: set[str],
    row_ids: set[str],
    now: datetime,
    min_age_seconds: int,
    min_height: int,
    stats: dict[str, int],
) -> _OrphanRefundCandidate | None:
    if job_id in settled:
        stats["settled"] += 1
        return None
    if job_id in row_ids:
        stats["has_row"] += 1
        return None
    if not job_locks:
        stats["no_lock"] += 1
        return None
    if len(job_locks) > 1:
        # A reused id with two locks has ambiguous custody — never
        # auto-refund; the tx-only alert keeps it visible for a human.
        stats["multi_lock"] += 1
        return None
    lock = job_locks[0]
    height = lock.block_height
    if height is None or height < min_height:
        stats["skipped_floor"] += 1
        return None
    at = lock.created_at
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if at is None or (now - at).total_seconds() < min_age_seconds:
        stats["deferred_age"] += 1
        return None
    provider = (lock.payload or {}).get("provider")
    owed = int(lock.value or 0)
    return _OrphanRefundCandidate(
        job_id=job_id,
        buyer_address=lock.sender,
        provider_address=provider if isinstance(provider, str) else "",
        owed_units=owed,
        custody_units=owed,
    )


def _count_orphan_refund_pass(stats: dict[str, int]) -> None:
    try:
        from ..metrics import escrow_orphan_refund_pass_total

        # Heartbeat: one "tick" per executed pass run (see _count_fee_pass).
        escrow_orphan_refund_pass_total.labels(result="tick").inc()
        for result, n in stats.items():
            if n:
                escrow_orphan_refund_pass_total.labels(result=result).inc(n)
    except Exception as e:  # noqa: BLE001 - metrics must never break the pass
        _logger.debug("orphan-refund-pass metrics emit failed: %s", e)
