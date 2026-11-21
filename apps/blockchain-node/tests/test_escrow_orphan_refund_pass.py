"""Orphan tx-only lock refund pass (#2380).

``sw_job_*`` ESCROW_LOCKs are minted by the shop-window CLI flows before the
provider call and carry no market/coordinator job row and no escrow row — the
``EscrowOpenTxOnlyLock`` alert's exact set. A provider-call failure or killed
session strands the lock: nothing selects it, nothing settles it. This pass
refunds the full lock to the buyer recorded as the lock's sender once the
lock is older than the min age and still has no settlement leg.

Scope is deliberately prefix-bound: manual ``market escrow create`` ids are
never auto-refunded. The floor is max(state_transition_v3_height,
escrow_fee_sweep_pass_min_height) — below v3 a refund debits the settlement
authority's own float, not the custody account.
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, create_engine
from sqlalchemy.pool import StaticPool

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import escrow_settlement_sweeper as ess
from aitbc_chain.rpc import escrow_settlement_sweeper_scan as scan

CHAIN = "test-chain"
JOB = "sw_job_20261120121052_2a4a4675"
BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
AUTHORITY = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716"
CUSTODY = "0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0"

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=8)
FRESH = NOW - timedelta(hours=1)
V3 = 1
FLOOR = 35400
LOCK_VALUE = 36000


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


@pytest.fixture(autouse=True)
def _reset_pass_state(monkeypatch):
    monkeypatch.setattr(ess, "_orphan_refund_pass_watermark", "")
    ess._orphan_refund_failures.clear()
    monkeypatch.setattr(ess.settings, "escrow_orphan_refund_pass_max_jobs", 25)
    monkeypatch.setattr(ess.settings, "escrow_orphan_refund_pass_min_age_seconds", 21600)
    monkeypatch.setattr(ess.settings, "state_transition_v3_height", V3)
    monkeypatch.setattr(ess.settings, "escrow_fee_sweep_pass_min_height", FLOOR)


def _lock(
    session,
    job_id: str = JOB,
    *,
    value: int = LOCK_VALUE,
    height: int = FLOOR + 10,
    at: datetime = OLD,
    sender: str = BUYER,
    provider: str | None = PROVIDER,
) -> Transaction:
    payload = {"action": "escrow_lock", "job_id": job_id}
    if provider is not None:
        payload["provider"] = provider
    tx = Transaction(
        chain_id=CHAIN,
        tx_hash=f"0xlock-{job_id}-{value}-{height}",
        sender=sender,
        recipient=CUSTODY,
        type="ESCROW_LOCK",
        value=value,
        block_height=height,
        created_at=at,
        payload=payload,
    )
    session.add(tx)
    session.commit()
    return tx


def _leg(session, tx_type: str, job_id: str = JOB, *, value: int = LOCK_VALUE) -> Transaction:
    tx = Transaction(
        chain_id=CHAIN,
        tx_hash=f"0x{tx_type}-{job_id}",
        sender=AUTHORITY,
        recipient=PROVIDER,
        type=tx_type,
        value=value,
        block_height=FLOOR + 20,
        created_at=OLD,
        payload={"action": tx_type.lower(), "job_id": job_id},
    )
    session.add(tx)
    session.commit()
    return tx


def _row(session, job_id: str = JOB) -> Escrow:
    row = Escrow(
        job_id=job_id,
        chain_id=CHAIN,
        buyer=BUYER,
        provider=PROVIDER,
        amount=LOCK_VALUE,
        status="locked",
    )
    session.add(row)
    session.commit()
    return row


def _candidates(session, **kw):
    args = {"max_jobs": 25, "min_age_seconds": 21600, "min_height": FLOOR}
    args.update(kw)
    return scan.orphan_refund_candidates(session, NOW, **args)


# ------------------------------------------------------------------ scan


def test_orphan_lock_is_candidate(session):
    _lock(session)
    candidates, stats, _ = _candidates(session)
    assert [c.job_id for c in candidates] == [JOB]
    cand = candidates[0]
    assert cand.buyer_address == BUYER
    assert cand.provider_address == PROVIDER
    assert cand.owed_units == LOCK_VALUE
    assert cand.custody_units == LOCK_VALUE


def test_non_sw_job_prefix_never_candidate(session):
    _lock(session, job_id="job_manual_1")
    _lock(session, job_id="ai_job_abc123")
    candidates, stats, _ = _candidates(session)
    assert candidates == []


def test_settled_lock_excluded(session):
    _lock(session)
    _leg(session, "ESCROW_RELEASE")
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["settled"] == 1


def test_refund_leg_also_excludes(session):
    _lock(session)
    _leg(session, "ESCROW_REFUND")
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["settled"] == 1


def test_escrow_row_excludes(session):
    _lock(session)
    _row(session)
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["has_row"] == 1


def test_below_min_height_skipped(session):
    _lock(session, height=FLOOR - 1)
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["skipped_floor"] == 1


def test_younger_than_min_age_deferred(session):
    _lock(session, at=FRESH)
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["deferred_age"] == 1


def test_multi_lock_same_job_skipped(session):
    _lock(session)
    _lock(session, value=LOCK_VALUE + 1)
    candidates, stats, _ = _candidates(session)
    assert candidates == []
    assert stats["multi_lock"] == 1


def test_ring_rotates_through_orphans(session):
    for i in range(3):
        _lock(session, job_id=f"sw_job_{i:04d}")
    seen = []
    after = ""
    for _ in range(2):
        candidates, _, watermark = _candidates(session, max_jobs=2, after_job_id=after)
        seen.extend(c.job_id for c in candidates)
        after = watermark
    assert seen == ["sw_job_0000", "sw_job_0001", "sw_job_0002", "sw_job_0000"]


# ------------------------------------------------------------ async driver


def _patch_pass_session(monkeypatch, session):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(ess, "session_scope", _scope)


def _patch_route(monkeypatch, custody: dict | None, submit_returns="0xrefund"):
    monkeypatch.setenv("ESCROW_ORPHAN_REFUND_PASS_ENABLED", "1")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: "k")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_address", lambda: AUTHORITY)
    custody_mock = AsyncMock(side_effect=lambda job_id: (custody or {}).get(job_id))
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._escrow_custody_balance", custody_mock)
    submit = AsyncMock(return_value=submit_returns)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._submit_refund_tx", submit)
    return submit


@pytest.mark.asyncio
async def test_flag_off_is_inert(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert not any(stats.values())


@pytest.mark.asyncio
async def test_enabled_but_keyless_still_ticks(session, monkeypatch):
    from aitbc_chain.metrics import escrow_orphan_refund_pass_total

    monkeypatch.setenv("ESCROW_ORPHAN_REFUND_PASS_ENABLED", "1")
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_key", lambda: None)
    monkeypatch.setattr("aitbc_chain.rpc.escrow_routes._get_settlement_address", lambda: None)
    _patch_pass_session(monkeypatch, session)
    before = escrow_orphan_refund_pass_total.labels(result="tick")._value.get()
    stats = await ess._orphan_refund_pass_once(NOW)
    assert not any(stats.values())
    assert escrow_orphan_refund_pass_total.labels(result="tick")._value.get() == before + 1


@pytest.mark.asyncio
async def test_orphan_refund_submits_full_lock(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["submitted"] == 1
    submit.assert_awaited_once_with(BUYER, PROVIDER, Decimal("0.001"), JOB, "")


@pytest.mark.asyncio
async def test_custody_mismatch_defers(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE - 1})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["deferred_custody"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_authority_tx_blocks_refund(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE})
    pending = [
        {
            "from": AUTHORITY,
            "to": PROVIDER,
            "amount": 10,
            "fee": 5,
            "nonce": 7,
            "type": "ESCROW_RELEASE",
            "signature": "0xsig",
            "chain_id": CHAIN,
        }
    ]
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=pending))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_failure_defers(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE})
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=None))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["deferred_pending"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_dry_run_counts_without_submitting(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE})
    monkeypatch.setenv("ESCROW_ORPHAN_REFUND_PASS_DRY_RUN", "1")
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["dry_run"] == 1
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_failure_backs_off(session, monkeypatch):
    _lock(session)
    _patch_pass_session(monkeypatch, session)
    submit = _patch_route(monkeypatch, {JOB: LOCK_VALUE}, submit_returns=None)
    monkeypatch.setattr(ess, "_proposer_pending_txs", AsyncMock(return_value=[]))
    stats = await ess._orphan_refund_pass_once(NOW)
    assert stats["error"] == 1
    # Inside the backoff window the same candidate defers without retrying.
    stats = await ess._orphan_refund_pass_once(NOW + timedelta(seconds=30))
    assert stats["deferred_backoff"] == 1
    assert submit.await_count == 1
