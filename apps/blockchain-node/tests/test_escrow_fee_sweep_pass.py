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


def _row(session, job_id: str = JOB, **overrides) -> Escrow:
    fields = {
        "job_id": job_id,
        "chain_id": CHAIN,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": JOB2_LOCK,
        "status": "released",
        "protected": False,
        "energy_fee_basis_points": None,
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
    return ess.fee_sweep_candidates(session, NOW, **kwargs)


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
    _row(session)
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
    _row(session)
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


def test_leg_below_height_floor_is_skipped(session):
    """Rule 6: a settlement leg below the floor leaves the job alone."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, height=V11 - 100)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, height=V11 - 50)
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["skipped_floor"] == 1


def test_leg_at_floor_height_is_eligible(session):
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK, height=V11 - 10)
    _tx(session, "ESCROW_RELEASE", "0xrel", JOB2_RELEASE, height=V11)
    _row(session)
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


def test_protected_row_defers_unproven(session):
    """Energy-protected rows can carry the floor-bumped release value where
    billed reconstruction is unreliable — defer unconditionally."""
    _job2_chain(session)
    _row(session, protected=True, energy_fee_basis_points=250)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_non_integral_reconstruction_defers(session):
    """A release value that does not invert billed*(1-r) integrally came from
    a non-standard fee path — unprovable."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 10000)  # 10000 % 39 != 0
    _row(session)
    candidates, stats = _candidates(session)
    assert candidates == []
    assert stats["deferred_unproven"] == 1


def test_billed_above_lock_defers(session):
    """Reconstructed billed gross exceeding the lock means the release leg
    did not follow value=billed*(1-r) (e.g. a floor bump) — unprovable."""
    _tx(session, "ESCROW_LOCK", "0xlock", JOB2_LOCK)
    _tx(session, "ESCROW_RELEASE", "0xrel", 35880)  # billed 36800 > lock 36000
    _row(session)
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


# ------------------------------------------------------------ async driver


def _patch_route(monkeypatch, custody: dict | None, submit_returns="0xsweephash"):
    """Wire the route surface the pass calls: enabled, key/address, custody,
    submit. custody maps job_id -> balance-or-None."""
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._fee_sweep_enabled", lambda: True)
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
    _row(session)
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
    _row(session)
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
    """Rule 4: any pending tx from the settlement authority fails closed."""
    _job2_chain(session)
    _row(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    pending = [{"tx_hash": "0xp", "sender": AUTHORITY, "type": "ESCROW_RELEASE"}]
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
    pending = [{"tx_hash": "0xp", "sender": BUYER, "type": "ESCROW_LOCK"}]
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
    pending = [{"tx_hash": "0xp", "sender": BUYER, "type": "TRANSFER"}]
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._fee_sweep_pass_once(NOW)
    assert stats["submitted"] == 1


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
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._fee_sweep_enabled", lambda: False)
    submit = _patch_route(monkeypatch, {JOB: JOB2_RESIDUE})
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._fee_sweep_enabled", lambda: False)
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
