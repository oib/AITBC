"""Periodic fee-residue pass (Task A4) — sealed-legs candidate selection +
async driver gates.

The pass sweeps a settled job's custody residue to the governed fee
recipient. Every rule below exists because a naive "lock minus sealed legs"
sweep is unsafe: a refund leg that is owed but evicted/unsent leaves the
buyer's change inside the residue, and sending it to the treasury would be a
custody bug. Candidate selection is pure/sync (``fee_sweep_candidates``);
the async driver adds the custody-equality and proposer-pending gates and
submits at most one sweep per tick.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess

CHAIN = "test-chain"
JOB = "a4_job"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
AUTHORITY = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716"
RECIPIENT = "0x716a56468DD4A11A91116920F9E8892BbDD7b1B8"

NOW = datetime(2026, 10, 5, 18, 0, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=2)
V11 = 35400

# Job-2 shape: full release, no change, residue == fee exactly.
JOB2_LOCK, JOB2_RELEASE, JOB2_RESIDUE = 36000, 35100, 900
# Job-1 shape: partial release + returned change, residue == fee only.
JOB1_RELEASE, JOB1_REFUND, JOB1_RESIDUE = 17550, 18000, 450
# Owed-change hazard: the refund leg never sealed.
OWED_CUSTODY = JOB2_LOCK - JOB1_RELEASE  # 18450 = fee 450 + owed change 18000


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def _tx(
    session,
    tx_type: str,
    tx_hash: str,
    value: int,
    *,
    job_id: str = JOB,
    height: int = V11 + 5,
    at: datetime = OLD,
    sender: str = AUTHORITY,
    recipient: str = PROVIDER,
) -> Transaction:
    action = {
        "ESCROW_LOCK": "escrow_lock",
        "ESCROW_RELEASE": "escrow_release",
        "ESCROW_REFUND": "escrow_refund",
        "ESCROW_FEE_SWEEP": "escrow_fee_sweep",
    }[tx_type]
    tx = Transaction(
        chain_id=CHAIN,
        tx_hash=tx_hash,
        sender=sender,
        recipient=recipient,
        type=tx_type,
        value=value,
        block_height=height,
        created_at=at,
        payload={"action": action, "job_id": job_id},
    )
    session.add(tx)
    session.commit()
    return tx


def _row(session, job_id: str = JOB, billed: int = JOB2_LOCK, **overrides) -> Escrow:
    fields = {
        "job_id": job_id,
        "chain_id": CHAIN,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": JOB2_LOCK,
        "status": "released",
        "protected": False,
        "energy_fee_basis_points": None,
        # A7: the route records billed gross per release leg; the chain
        # helpers mint f"0xrel-{job_id}", so pair on that hash by default.
        "billed_legs": [{"tx_hash": f"0xrel-{job_id}", "billed": billed}],
    }
    fields.update(overrides)
    row = Escrow(**fields)
    session.add(row)
    session.commit()
    return row


def _candidates(session, **kwargs):
    kwargs.setdefault("max_jobs", 50)
    kwargs.setdefault("grace_seconds", 300)
    kwargs.setdefault("min_height", V11)
    candidates, stats, _watermark = ess.fee_sweep_candidates(session, NOW, **kwargs)
    return candidates, stats


def _job2_chain(session, job_id: str = JOB):
    _tx(session, "ESCROW_LOCK", f"0xlock-{job_id}", JOB2_LOCK, job_id=job_id)
    _tx(session, "ESCROW_RELEASE", f"0xrel-{job_id}", JOB2_RELEASE, job_id=job_id)


def _job1_chain(session, job_id: str = JOB):
    _tx(session, "ESCROW_LOCK", f"0xlock-{job_id}", JOB2_LOCK, job_id=job_id)
    _tx(session, "ESCROW_RELEASE", f"0xrel-{job_id}", JOB1_RELEASE, job_id=job_id)
    _tx(session, "ESCROW_REFUND", f"0xref-{job_id}", JOB1_REFUND, job_id=job_id)


# ------------------------------------------------------------ selection


def test_residue_from_sealed_legs_never_row_columns(session):
    """Rule 1: the row's amount columns lie; the chain decides."""
    _job2_chain(session)
    # A poisoned row: claims a refund that never sealed and a wrong released
    # amount. The candidate's residue must still be 900.
    _row(session, released_amount=35100, refunded_amount=99999, refund_tx_hash="0xphantom")
    candidates, stats = _candidates(session)
    assert len(candidates) == 1
    assert candidates[0].expected_units == JOB2_RESIDUE
    assert candidates[0].fee_bound_units == JOB2_RESIDUE


def test_owed_change_residue_is_not_swept(session):
    """Rule 3 (first acceptance test): release sealed, owed change refund
    never landed — custody holds fee+change and the residue exceeds the fee
    bound, so the job defers instead of paying the buyer's change to the
    treasury."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB1_RELEASE)
    # proven billed 18000 → fee bound 450 < residue 18450 → not treasury money
    _row(session, billed_legs=[{"tx_hash": "0xrel", "billed": 18000}])
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_full_release_residue_is_a_candidate(session):
    """Job-2 shape: lock 36000, release 35100, residue 900 == fee bound."""
    _job2_chain(session)
    _row(session)
    candidates, stats = _candidates(session)
    assert stats["candidates"] == 1
    assert candidates[0].expected_units == 900


def test_change_returned_residue_is_a_candidate(session):
    """Job-1 shape after both legs sealed: residue 450 == withheld fee."""
    _job1_chain(session)
    _row(session, billed=18000)
    candidates, stats = _candidates(session)
    assert stats["candidates"] == 1
    assert candidates[0].expected_units == 450


def test_already_swept_job_is_done(session):
    """A sealed ESCROW_FEE_SWEEP lands in the residue formula: nothing left."""
    _job2_chain(session)
    _tx(session, "ESCROW_FEE_SWEEP", "0xsweep", JOB2_RESIDUE, recipient=RECIPIENT)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_residue"] == 1


def test_leg_below_height_floor_never_examined(session):
    """Rule 6 (F2): a job whose settlement legs are ALL below the floor is
    excluded at discovery time — it cannot consume a candidate-cap slot
    (the A4 bug this fixes was cap-slot starvation by below-floor rows)."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, height=V11 - 100)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, height=V11 - 50)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert not any(stats.values())  # invisible to the pass, not "skipped"


def test_mixed_height_job_skips_floor(session):
    """A job that straddles the floor — a settlement leg on both sides —
    surfaces via its post-floor leg but stays off-limits: any leg below
    the floor keeps the whole job excluded."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, height=V11 - 100)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, height=V11 + 5)
    _tx(session, "ESCROW_REFUND", "0xref", 1000, height=V11 - 50)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["skipped_floor"] == 1


def test_leg_at_floor_height_is_eligible(session):
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, height=V11 - 10)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, height=V11)
    _row(session, billed_legs=[{"tx_hash": "0xrel", "billed": JOB2_LOCK}])
    candidates, stats = _candidates(session)
    assert stats["candidates"] == 1


def test_fresh_leg_defers_on_grace(session):
    """Rule 5: a leg younger than the grace period means a multi-leg settle
    may still be in flight — wait."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, at=OLD)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, at=NOW - timedelta(seconds=60))
    _row(session)
    candidates, stats = _candidates(session, grace_seconds=300)
    assert candidates == []
    assert stats["deferred_grace"] == 1


def test_protected_bump_release_proves_and_sweeps(session):
    """A7 census shape (f0d0604b): the sealed release equals the signed
    provider credit — unreconstructable by inversion, exactly provable by
    recompute: expected = max(net 267300, credit 267301) = 267301. Residue
    is fee-shaped (billed == lock) and sweeps."""
    _tx(session, "ESCROW_LOCK", "0xlock", 274154)
    _tx(session, "ESCROW_RELEASE", "0xrel", 267301)
    _row(
        session,
        amount=274154,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=267301,
        energy_net_floor_units=267300,
        billed_legs=[{"tx_hash": "0xrel", "billed": 274154}],
    )
    candidates, stats = _candidates(session)
    assert stats["candidates"] == 1
    assert candidates[0].expected_units == 274154 - 267301


def test_zero_fee_rate_leaves_no_residue(session):
    """A7c: a legal bps=0 quote withholds nothing — lock − sealed release is
    zero, so the job reports no_residue instead of refusing the proof."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_LOCK)  # bps=0 → release == billed
    _row(session, energy_fee_basis_points=0)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_residue"] == 1


def test_protected_billed_below_credit_refuses(session):
    """A7b: a protected billed below the signed credit is impossible via the
    route (billable < target → refused, no leg submitted) — the bump would
    otherwise mask it: sealed equals credit and withheld goes negative."""
    _tx(session, "ESCROW_LOCK", "0xlock", 274154)
    _tx(session, "ESCROW_RELEASE", "0xrel", 267301)
    _row(
        session,
        amount=274154,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=267301,
        energy_net_floor_units=267300,
        billed_legs=[{"tx_hash": "0xrel", "billed": 200000}],
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_protected_recompute_mismatch_defers(session):
    """A protected row whose sealed value matches neither the net nor the
    credit bump fails the recompute — defer."""
    _job2_chain(session)
    _row(
        session,
        protected=True,
        energy_fee_basis_points=250,
        energy_provider_credit_units=40000,  # bump expected → 40000 ≠ 35100
    )
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_legacy_row_without_billed_stays_unproven(session):
    """A7: rows released before billed recording was added have
    billed_legs=NULL — unproven forever, no inversion fallback."""
    _job2_chain(session)
    _row(session, billed_legs=None)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_non_integral_reconstruction_defers(session):
    """A sealed value the recorded billed cannot recompute to came from a
    non-standard path — unprovable."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 10000)
    # paired billed recomputes 35100 ≠ sealed 10000 → refuse
    _row(session, billed_legs=[{"tx_hash": "0xrel", "billed": JOB2_LOCK}])
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_billed_above_lock_defers(session):
    """A recorded billed gross exceeding the lock is impossible — the route
    clamps billable to the milestones total — unprovable."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 35880)
    _row(session, billed_legs=[{"tx_hash": "0xrel", "billed": 36800}])
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_release_leg_without_billed_entry_defers(session):
    """A sealed release leg with no billed entry on its hash proves nothing —
    the pass cannot know what was billed for it."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xunknown", JOB2_RELEASE)
    _row(session)  # billed entry keys 0xrel-<job>, leg hashes 0xunknown
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_candidate_cap_bounds_work(session):
    """Rule 7: at most max_jobs rows are inspected per pass."""
    for i in range(3):
        _job2_chain(session, job_id=f"job{i}")
        _row(session, job_id=f"job{i}")
    candidates, stats = _candidates(session, max_jobs=1)
    assert stats["candidates"] == 1


def test_below_floor_rows_cannot_consume_cap(session):
    """F2: sixty settled jobs below the floor plus one eligible job —
    the cap counts floor-eligible jobs only, so the new job is inspected
    even though it sorts last."""
    for i in range(60):
        job_id = f"old{i:02d}"
        _tx(session, "ESCROW_LOCK", f"0xlock-{job_id}", JOB2_LOCK, job_id=job_id, height=V11 - 100)
        _tx(session, "ESCROW_RELEASE", f"0xrel-{job_id}", JOB2_RELEASE, job_id=job_id, height=V11 - 50)
        _row(session, job_id=job_id)
    _job2_chain(session, job_id="zznew")
    _row(session, job_id="zznew")
    candidates, stats, _ = ess.fee_sweep_candidates(session, NOW, max_jobs=1, grace_seconds=300, min_height=V11)
    assert stats["candidates"] == 1
    assert [c.job_id for c in candidates] == ["zznew"]


def test_eligible_jobs_rotate_through_the_ring(session):
    """F2: more eligible jobs than the cap — each pass takes the next
    max_jobs window in job_id order (watermark ring), so deferred jobs are
    re-examined every cycle instead of starving behind the first N rows."""
    for i in range(3):
        _job2_chain(session, job_id=f"job{i}")
        _row(session, job_id=f"job{i}")
    seen = []
    watermark = ""
    for _ in range(4):
        candidates, _stats, watermark = ess.fee_sweep_candidates(
            session, NOW, max_jobs=1, grace_seconds=300, min_height=V11, after_job_id=watermark
        )
        seen.extend(c.job_id for c in candidates)
    assert seen == ["job0", "job1", "job2", "job0"]  # wraps around, none starved


# ------------------------------------------------------------ async driver


def _patch_route(monkeypatch, custody: dict | None, submit_returns="0xsweephash"):
    """Wire the route surface the pass calls: pass flag, key/address, custody,
    submit. custody maps job_id -> balance-or-None."""
    monkeypatch.setenv("ESCROW_FEE_SWEEP_PASS_ENABLED", "1")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: "k")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_address", lambda: AUTHORITY)
    custody_mock = AsyncMock(side_effect=lambda job_id: (custody or {}).get(job_id))
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._escrow_custody_balance", custody_mock)
    submit = AsyncMock(return_value=submit_returns)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._submit_fee_sweep_tx", submit)
    return submit


def _patch_pass_session(monkeypatch, session):
    """Run the pass's DB reads against the in-memory test session."""
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)


def _route_tx(sender: str, tx_type: str, nonce: int = 7) -> dict:
    """A transaction shaped the way the routes actually submit one —
    sender under "from", no "tx_hash" key in the body."""
    return {
        "from": sender,
        "to": PROVIDER,
        "amount": 10,
        "fee": 5,
        "nonce": nonce,
        "type": tx_type,
        "signature": "0xsig",
        "chain_id": CHAIN,
    }


def _mempool_pending(*txs: dict) -> list[dict]:
    """Feed real txs through the actual Mempool and read back exactly what
    the /mempool endpoint would return — the shape cannot drift from what
    _proposer_pending_txs sees in production."""
    from aitbc_chain.mempool import InMemoryMempool

    mp = InMemoryMempool(chain_id=CHAIN)
    for tx in txs:
        mp.add(dict(tx), CHAIN)
    return mp.get_pending_transactions(CHAIN)


@pytest.mark.asyncio
async def test_full_release_sweep_submits(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1
    submit.assert_awaited_once_with(JOB, JOB, JOB2_RESIDUE)


@pytest.mark.asyncio
async def test_change_job_sweep_submits_exact_residue(session, monkeypatch):
    _job1_chain(session)
    _row(session, billed=18000)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB1_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1
    submit.assert_awaited_once_with(JOB, JOB, JOB1_RESIDUE)


@pytest.mark.asyncio
async def test_owed_change_never_submits(session, monkeypatch):
    """End-to-end rule 3: custody holds fee+owed change — the pass defers on
    the fee bound before it ever asks the balance."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB1_RELEASE)
    _row(session, billed_legs=[{"tx_hash": "0xrel", "billed": 18000}])
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: OWED_CUSTODY})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 0
    assert stats["deferred_unproven"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_custody_mismatch_defers(session, monkeypatch):
    """Rule 2: anything but exact custody equality defers."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE + 1})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_custody"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_custody_probe_none_defers(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: None})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_custody"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_authority_tx_blocks(session, monkeypatch):
    """Rule 4: any pending tx from the settlement authority fails closed —
    real mempool shape ("from" key, not "sender")."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    pending = _mempool_pending(_route_tx(AUTHORITY, "ESCROW_RELEASE"))
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_authority_transfer_blocks(session, monkeypatch):
    """F1: an authority-signed NON-escrow tx (nonce-occupying TRANSFER)
    must also block — a sweep built now would collide on the nonce slot."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    pending = _mempool_pending(_route_tx(AUTHORITY, "TRANSFER"))
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_escrow_tx_from_anyone_blocks(session, monkeypatch):
    """Any ESCROW_* tx in the proposer mempool means a settlement is in
    flight — not just authority-signed ones."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    pending = _mempool_pending(_route_tx(BUYER, "ESCROW_LOCK"))
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_probe_failure_blocks(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=None))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_pending_tx_does_not_block(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    pending = _mempool_pending(_route_tx(BUYER, "TRANSFER"))
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1


def test_mempool_content_has_no_tx_hash_key():
    """F1 proof: get_pending_transactions returns the submitted tx body
    verbatim — "from" is the sender key and "tx_hash" exists only as the
    mempool table's primary key, never inside the returned content."""
    pending = _mempool_pending(_route_tx(AUTHORITY, "TRANSFER"))
    assert len(pending) == 1
    assert pending[0]["from"] == AUTHORITY
    assert "sender" not in pending[0]
    assert "tx_hash" not in pending[0]


@pytest.mark.asyncio
async def test_proposer_pending_hashes_recognises_pending_tx(monkeypatch):
    """The demote probe recomputes admission's hash over each returned body
    (mempool content carries no tx_hash key — proven by
    test_mempool_content_has_no_tx_hash_key), so a real pending leg's stored
    hash comes back in the set and is protected from demotion."""
    from types import SimpleNamespace

    from aitbc_chain.mempool import compute_tx_hash

    tx = _route_tx(AUTHORITY, "ESCROW_RELEASE")
    txs = _mempool_pending(tx)
    body = {"success": True, "transactions": txs, "count": len(txs)}
    resp = SimpleNamespace(status_code=200, json=lambda: body)
    monkeypatch.setattr(ess.SharedHttpClient, "get", AsyncMock(return_value=resp))
    pending_hashes = await ess._proposer_pending_hashes()
    assert pending_hashes == {compute_tx_hash(tx)}


@pytest.mark.asyncio
async def test_dry_run_counts_and_submits_nothing(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    monkeypatch.setenv("ESCROW_FEE_SWEEP_PASS_DRY_RUN", "1")
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["dry_run"] == 1
    assert stats["submitted"] == 0
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pass_disabled_is_noop(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.delenv("ESCROW_FEE_SWEEP_PASS_ENABLED", raising=False)
    stats = await ess._fee_sweep_pass_once(NOW)
    assert not any(stats.values())
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_flag_alone_does_not_arm_the_pass(session, monkeypatch):
    """Flag split (A4c): ESCROW_FEE_SWEEP_ENABLED gates the release-route
    retry only — the pass arms on ESCROW_FEE_SWEEP_PASS_ENABLED, so the pass
    can be observed without re-arming route emission (C16 deploy note)."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.delenv("ESCROW_FEE_SWEEP_PASS_ENABLED", raising=False)
    monkeypatch.setenv("ESCROW_FEE_SWEEP_ENABLED", "1")
    stats = await ess._fee_sweep_pass_once(NOW)
    assert not any(stats.values())
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_settlement_key_is_noop(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: "")
    stats = await ess._fee_sweep_pass_once(NOW)
    assert not any(stats.values())


@pytest.mark.asyncio
async def test_one_submission_per_pass(session, monkeypatch):
    """Two eligible jobs, one tick: the second waits for the next pass."""
    for i in (0, 1):
        _job2_chain(session, job_id=f"job{i}")
        _row(session, job_id=f"job{i}")
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {"job0": JOB2_RESIDUE, "job1": JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1
    assert submit.await_count == 1


@pytest.mark.asyncio
async def test_sweep_once_runs_demote_then_fee_pass(session, monkeypatch):
    """Wiring: _sweep_once runs the demote path (byte-identical) and then one
    fee pass — a pass failure must not touch the demote result."""
    _tx(session, "ESCROW_RELEASE", "0xsealed", 100)
    _row(session, released_at=NOW - timedelta(hours=3), release_tx_hash="0xsealed")
    _patch_pass_session(monkeypatch, session)
    fee_pass = AsyncMock(return_value={})
    monkeypatch.setattr(ess, "_fee_sweep_pass_once", fee_pass)
    monkeypatch.setattr(ess, "_proposer_pending_hashes", AsyncMock(return_value=set()))
    stats = await ess._sweep_once()
    assert stats["verified"] == 1
    fee_pass.assert_awaited_once()


# ------------------------------------------------------------ A4c defects


def test_ring_wrap_examines_each_job_once(session):
    """D1: with the watermark inside the eligible set, the wrap-around refill
    is bounded above by the watermark — every job is examined exactly once.
    Pre-fix the unbounded refill re-returned the tail (['e','a','b','c','e'])."""
    for job_id in ("a", "b", "c", "e"):
        _job2_chain(session, job_id=job_id)
        _row(session, job_id=job_id)
    candidates, stats, watermark = ess.fee_sweep_candidates(
        session, NOW, max_jobs=50, grace_seconds=300, min_height=V11, after_job_id="c"
    )
    assert [c.job_id for c in candidates] == ["e", "a", "b", "c"]
    assert stats["candidates"] == 4
    assert watermark == "c"


def test_ring_wrap_refill_respects_remaining_cap(session):
    """D1 companion: the refill takes at most the cap remainder, still bounded
    above by the watermark — a mid-ring pass examines [tail..., head...] with
    no overlap."""
    for job_id in ("a", "b", "c", "d", "e"):
        _job2_chain(session, job_id=job_id)
        _row(session, job_id=job_id)
    candidates, _stats, watermark = ess.fee_sweep_candidates(
        session, NOW, max_jobs=3, grace_seconds=300, min_height=V11, after_job_id="c"
    )
    # tail past 'c' = [d, e] (2 < cap) → refill 1 slot from the head → [a]
    assert [c.job_id for c in candidates] == ["d", "e", "a"]
    assert watermark == "a"


def test_chain_legs_without_row_are_counted(session):
    """D3: sealed settlement legs whose job has no Escrow row surface in the
    stats — a rebuilt node's whole history reads that way, and silence made
    'nothing to sweep' indistinguishable from 'everything invisible'."""
    _job2_chain(session)  # legs exist, no _row
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_row"] == 1


def test_lockless_job_is_counted(session):
    """D5: settlement legs but no ESCROW_LOCK-type leg (foreign-typed lock,
    import anomaly) — counted, not silently read as a settled no_residue."""
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["no_lock"] == 1


def test_legs_reader_matches_oracle_membership(session):
    """D6: the pass's leg membership is the oracle's — release/refund values
    count only on the oracle's action names, so a mismatched-action leg can
    never land on the bound side while missing from the expected side."""
    from aitbc_chain.contracts.escrow import settlement_legs_from_chain

    _job1_chain(session)
    # A foreign release-typed leg: type matches, payload action does not.
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash="0xforeign",
            sender=AUTHORITY,
            recipient=PROVIDER,
            type="ESCROW_RELEASE",
            value=111,
            block_height=V11 + 6,
            created_at=OLD,
            payload={"action": "not_escrow_release", "job_id": JOB},
        )
    )
    session.commit()
    oracle = settlement_legs_from_chain(session, JOB)
    legs = ess._escrow_legs_by_job(session, [JOB])[JOB]
    assert legs["release_values"] == oracle["release_values"] == [JOB1_RELEASE]
    assert sum(legs["refund_values"]) == oracle["refunded_amount"] == JOB1_REFUND
    assert legs["lock_units"] == oracle["locked_amount"] == JOB2_LOCK
    # ...but the mismatched leg still counts as settlement activity for the
    # floor and grace clocks.
    assert legs["min_settlement_height"] == V11 + 5


@pytest.mark.asyncio
async def test_rejected_sweep_backs_off_per_job(session, monkeypatch):
    """D9: a rejected submission records a per-job backoff — the same job is
    skipped on later ticks instead of resubmitting every pass, and the backoff
    expires so a transient cause still self-heals."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    monkeypatch.setattr(ess, "_pass_submit_failures", {})
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE}, submit_returns=None)
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))

    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["error"] == 1
    assert submit.await_count == 1

    # Inside the backoff window: examined but not attempted.
    stats = await ess._fee_sweep_pass_once(NOW + timedelta(seconds=30))
    assert stats["deferred_backoff"] == 1
    assert submit.await_count == 1

    # Past the window: retried.
    stats = await ess._fee_sweep_pass_once(NOW + timedelta(seconds=61))
    assert stats["error"] == 1
    assert submit.await_count == 2


@pytest.mark.asyncio
async def test_backoff_does_not_block_other_jobs(session, monkeypatch):
    """D9: a backed-off job yields its slot — the pass moves on to the next
    candidate in the same tick."""
    for job_id in ("job0", "job1"):
        _job2_chain(session, job_id=job_id)
        _row(session, job_id=job_id)
    _patch_pass_session(monkeypatch, session)
    monkeypatch.setattr(ess, "_pass_submit_failures", {"job0": (1, NOW.timestamp() + 600)})
    submit = _patch_route(monkeypatch, {"job0": JOB2_RESIDUE, "job1": JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["deferred_backoff"] == 1
    assert stats["submitted"] == 1
    submit.assert_awaited_once_with("job1", "job1", JOB2_RESIDUE)


@pytest.mark.asyncio
async def test_success_clears_backoff(session, monkeypatch):
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    failures = {JOB: (3, NOW.timestamp() - 1)}  # expired backoff
    monkeypatch.setattr(ess, "_pass_submit_failures", failures)
    _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1
    assert JOB not in failures


@pytest.mark.asyncio
async def test_backoff_map_prunes_departed_jobs(session, monkeypatch):
    """F2: backoff entries for jobs that are no longer floor-eligible are
    dropped during the pass — the map does not accumulate stale rows for
    departed jobs forever. A still-eligible job keeps its backoff."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    failures = {
        JOB: (1, NOW.timestamp() + 600),  # eligible, stays backed off
        "ghost": (5, NOW.timestamp() + 600),  # no legs anywhere — pruned
    }
    monkeypatch.setattr(ess, "_pass_submit_failures", failures)
    _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))

    stats = await ess._fee_sweep_pass_once(NOW)

    assert "ghost" not in failures
    assert JOB in failures
    assert stats["deferred_backoff"] == 1
