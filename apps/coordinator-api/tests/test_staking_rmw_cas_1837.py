"""#1837: staking consumer writes are CAS/SQL-side, not ORM read-modify-write.

#1799 made ``total_staked`` atomic but every consumer still did ORM RMW:
``add_to_stake`` lost concurrent amount bumps, ``complete_unbonding`` could
double-decrement on a stale status read, ``claim_rewards`` let two callers
both zero-and-count the same rewards, ``unbond_stake``/``_calculate_rewards``
and ``distribute_earnings`` interleaved lost updates.

Pins use uncommitted interfering writes: an UPDATE with
``synchronize_session=False`` lands in the same transaction (visible to
subsequent reads) while the session's identity-mapped ORM objects keep
their pre-write values — exactly the stale-read a concurrent commit produces
for a caller that fetched earlier.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import Session, col, select, update

from coordinator_api.contexts.staking.domain.staking import AgentMetrics, AgentStake, PerformanceTier, StakeStatus
from coordinator_api.contexts.staking.services.staking_service import StakingService

AGENT = "0x" + "cc" * 20
STAKER = "0x" + "dd" * 20


def _agent(session: Session) -> None:
    session.add(AgentMetrics(agent_wallet=AGENT, total_staked=Decimal("0"), current_tier=PerformanceTier.BRONZE))
    session.commit()


def _stake(session: Session, amount: str = "200") -> AgentStake:
    return StakingService(session).create_stake(STAKER, AGENT, Decimal(amount), lock_period=30, auto_compound=False)


def _raw_stake(session: Session, stake_id: str) -> AgentStake:
    return session.execute(select(AgentStake).where(AgentStake.stake_id == stake_id)).scalar_one()


def _set_stake(session: Session, stake_id: str, **values) -> None:
    """Setup write: committed and expired so later reads see it."""
    session.execute(update(AgentStake).where(col(AgentStake.stake_id) == stake_id).values(**values))
    session.commit()
    session.expire_all()


def _interfere(session: Session, stmt) -> None:
    """Simulate a concurrent committed write: visible in-transaction, but the
    identity-mapped ORM objects keep their stale attribute values."""
    session.execute(stmt.execution_options(synchronize_session=False))


def _fresh_stake(session: Session, stake_id: str) -> AgentStake:
    session.expire_all()
    return _raw_stake(session, stake_id)


@pytest.mark.unit
def test_add_to_stake_amount_survives_concurrent_bump(db_session):
    """ORM ``stake.amount += X`` wrote back a stale total; the SQL-side bump
    must land on the concurrently-updated amount."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    svc = StakingService(db_session)
    # Warm the identity map, then a concurrent +50 lands uncommitted-but-visible.
    assert _raw_stake(db_session, stake.stake_id).amount == Decimal("200")
    _interfere(
        db_session,
        update(AgentStake).where(col(AgentStake.stake_id) == stake.stake_id).values(amount=AgentStake.amount + Decimal("50")),
    )
    svc.add_to_stake(stake.stake_id, Decimal("25"))
    assert _fresh_stake(db_session, stake.stake_id).amount == Decimal("275")


@pytest.mark.unit
def test_complete_unbonding_cas_rejects_second_completion(db_session):
    """Two completions on a stale UNBONDING read each decremented
    total_staked/pool/staker_count — the status CAS must refuse the loser."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(db_session, stake.stake_id, status=StakeStatus.UNBONDING, unbonding_time=datetime.now(UTC) - timedelta(days=31))
    svc = StakingService(db_session)
    # Warm UNBONDING, then a concurrent completion flips it to COMPLETED.
    assert _raw_stake(db_session, stake.stake_id).status == StakeStatus.UNBONDING
    _interfere(
        db_session,
        update(AgentStake).where(col(AgentStake.stake_id) == stake.stake_id).values(status=StakeStatus.COMPLETED),
    )
    metrics_before = db_session.execute(
        select(AgentMetrics.total_staked).where(AgentMetrics.agent_wallet == AGENT)
    ).scalar_one()
    with pytest.raises(ValueError, match="not unbonding"):
        svc.complete_unbonding(stake.stake_id)
    db_session.rollback()
    db_session.expire_all()
    assert (
        db_session.execute(select(AgentMetrics.total_staked).where(AgentMetrics.agent_wallet == AGENT)).scalar_one()
        == metrics_before
    )


@pytest.mark.unit
def test_claim_rewards_cas_counts_each_reward_once(db_session):
    """Two claims reading the same accumulated_rewards must not both count —
    the value-predicate CAS lets only the first zeroing win."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(db_session, stake.stake_id, accumulated_rewards=Decimal("42"))
    svc = StakingService(db_session)
    # Warm rewards=42, then a concurrent claim zeroes the row.
    assert _raw_stake(db_session, stake.stake_id).accumulated_rewards == Decimal("42")
    _interfere(
        db_session,
        update(AgentStake).where(col(AgentStake.stake_id) == stake.stake_id).values(accumulated_rewards=Decimal("0")),
    )
    result = svc.claim_rewards([stake.stake_id])
    assert result["total_rewards"] == Decimal("0")
    assert _fresh_stake(db_session, stake.stake_id).accumulated_rewards == Decimal("0")


@pytest.mark.unit
def test_unbond_stake_cas_rejects_second_transition(db_session):
    """A second unbond on a stale ACTIVE read must not re-transition —
    the ACTIVE->UNBONDING CAS refuses it."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(db_session, stake.stake_id, end_time=datetime.now(UTC) - timedelta(days=1))
    svc = StakingService(db_session)
    assert _raw_stake(db_session, stake.stake_id).status == StakeStatus.ACTIVE
    _interfere(
        db_session,
        update(AgentStake)
        .where(col(AgentStake.stake_id) == stake.stake_id)
        .values(status=StakeStatus.UNBONDING, unbonding_time=datetime.now(UTC)),
    )
    with pytest.raises(ValueError, match="not active"):
        svc.unbond_stake(stake.stake_id)
    db_session.rollback()


@pytest.mark.unit
def test_calculate_rewards_sql_credit_survives_concurrent_write(db_session):
    """The reward credit is SQL-side ``accumulated + current`` — a concurrent
    write to accumulated_rewards must not be overwritten by a stale ORM +=."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(
        db_session,
        stake.stake_id,
        accumulated_rewards=Decimal("10"),
        last_reward_time=datetime.now(UTC) - timedelta(days=30),
        current_apy=Decimal("10"),
    )
    svc = StakingService(db_session)
    # Warm accumulated=10, then a concurrent +50 lands uncommitted-but-visible.
    assert _raw_stake(db_session, stake.stake_id).accumulated_rewards == Decimal("10")
    _interfere(
        db_session,
        update(AgentStake)
        .where(col(AgentStake.stake_id) == stake.stake_id)
        .values(accumulated_rewards=AgentStake.accumulated_rewards + Decimal("50")),
    )
    svc._calculate_rewards(stake.stake_id)
    db_session.commit()
    final = _fresh_stake(db_session, stake.stake_id).accumulated_rewards
    # 10 + 50 concurrent + ~30d of 10% APY on 200 — must exceed 60, proving
    # the concurrent +50 was not lost.
    assert final > Decimal("60")


@pytest.mark.unit
def test_distribute_earnings_sql_increment_survives_concurrent_write(db_session):
    """Per-stake reward credits are SQL-side increments — a concurrent write
    to accumulated_rewards must survive the distribution."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(db_session, stake.stake_id, accumulated_rewards=Decimal("7"))
    svc = StakingService(db_session)
    # Warm the stake object, then a concurrent +50 lands uncommitted-but-visible.
    stakes = (
        db_session.execute(select(AgentStake).where(AgentStake.agent_wallet == AGENT, AgentStake.status == StakeStatus.ACTIVE))
        .scalars()
        .all()
    )
    assert stakes and stakes[0].accumulated_rewards == Decimal("7")
    _interfere(
        db_session,
        update(AgentStake)
        .where(col(AgentStake.stake_id) == stake.stake_id)
        .values(accumulated_rewards=AgentStake.accumulated_rewards + Decimal("50")),
    )
    svc.distribute_earnings(AGENT, Decimal("100"), {})
    final = _fresh_stake(db_session, stake.stake_id).accumulated_rewards
    # share = 99 (1% fee) * 200/200 = 99 → final must be 7 + 50 + 99.
    assert final == Decimal("156")


# --- #1837 validator rework: claim router gating + payout-failure compensation ---


class _ClaimStake:
    def __init__(self, address: str, rewards: Decimal) -> None:
        self.staker_address = address
        self.accumulated_rewards = rewards


class _FakeStakingService:
    def __init__(self, stakes: dict[str, _ClaimStake], claim_result: dict[str, Any]) -> None:
        self._stakes = stakes
        self._claim_result = claim_result
        self.restored: dict[str, Decimal] | None = None

    def get_stake(self, stake_id: str):
        return self._stakes.get(stake_id)

    def claim_rewards(self, stake_ids: list[str]) -> dict[str, Any]:
        return self._claim_result

    def restore_claimed_rewards(self, claimed_amounts: dict[str, Decimal]) -> None:
        self.restored = claimed_amounts


class _FakeChainService:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self._error = error

    async def claim_rewards(self, stake_ids: list[str]) -> dict[str, Any]:
        self.calls.append(list(stake_ids))
        if self._error is not None:
            raise self._error
        return {"transaction_hash": "0xdead"}


def _override_claim_deps(client, staking_service, chain_service):
    """Swap the router's service deps for fakes; returns a cleanup callable."""
    from coordinator_api.contexts.staking.routers import staking as staking_router
    from coordinator_api.main import app

    async def _user():
        return {"address": STAKER, "is_oracle": False, "is_admin": False}

    app.dependency_overrides[staking_router.get_staking_service] = lambda: staking_service
    app.dependency_overrides[staking_router.get_blockchain_service] = lambda: chain_service
    app.dependency_overrides[staking_router.get_current_user_required] = _user

    def _cleanup():
        for dep in (
            staking_router.get_staking_service,
            staking_router.get_blockchain_service,
            staking_router.get_current_user_required,
        ):
            app.dependency_overrides.pop(dep, None)

    return _cleanup


@pytest.mark.unit
def test_claim_router_skips_chain_call_when_all_cas_lost(client, db_session):
    """Every claim CAS lost -> the DB counted nothing, so NO chain memo may
    be written (the double-emit the Validator flagged)."""
    stakes = {"s1": _ClaimStake(STAKER, Decimal("10")), "s2": _ClaimStake(STAKER, Decimal("5"))}
    svc = _FakeStakingService(
        stakes,
        {"total_rewards": Decimal("0"), "claimed_stakes": 0, "claimed_stake_ids": [], "claimed_amounts": {}},
    )
    chain = _FakeChainService()
    cleanup = _override_claim_deps(client, svc, chain)
    try:
        resp = client.post("/v1/staking/claim-rewards", json=["s1", "s2"])
    finally:
        cleanup()
    assert resp.status_code == 200
    assert resp.json()["claimed_stakes"] == 0
    assert chain.calls == []


@pytest.mark.unit
def test_claim_router_chain_called_only_for_cas_winners(client, db_session):
    """Partial CAS win -> the chain payout covers only the stakes whose
    rewards this claim actually zeroed."""
    stakes = {"s1": _ClaimStake(STAKER, Decimal("10")), "s2": _ClaimStake(STAKER, Decimal("5"))}
    svc = _FakeStakingService(
        stakes,
        {
            "total_rewards": Decimal("10"),
            "claimed_stakes": 1,
            "claimed_stake_ids": ["s1"],
            "claimed_amounts": {"s1": Decimal("10")},
        },
    )
    chain = _FakeChainService()
    cleanup = _override_claim_deps(client, svc, chain)
    try:
        resp = client.post("/v1/staking/claim-rewards", json=["s1", "s2"])
    finally:
        cleanup()
    assert resp.status_code == 200
    assert resp.json()["claimed_stakes"] == 1
    assert chain.calls == [["s1"]]


@pytest.mark.unit
def test_claim_router_restores_rewards_on_chain_failure(client, db_session):
    """Chain payout raises after the DB zero committed -> the exact claimed
    amounts go back so a retry can pay them (no unrecoverable loss)."""
    stakes = {"s1": _ClaimStake(STAKER, Decimal("10"))}
    svc = _FakeStakingService(
        stakes,
        {
            "total_rewards": Decimal("10"),
            "claimed_stakes": 1,
            "claimed_stake_ids": ["s1"],
            "claimed_amounts": {"s1": Decimal("10")},
        },
    )
    chain = _FakeChainService(error=RuntimeError("chain rpc unreachable"))
    cleanup = _override_claim_deps(client, svc, chain)
    try:
        resp = client.post("/v1/staking/claim-rewards", json=["s1"])
    finally:
        cleanup()
    assert resp.status_code == 400
    assert svc.restored == {"s1": Decimal("10")}


@pytest.mark.unit
def test_restore_claimed_rewards_sql_side_recredit(db_session):
    """Service-level: restore adds the amount back SQL-side, preserving any
    rewards accrued after the zero."""
    _agent(db_session)
    stake = _stake(db_session, "200")
    _set_stake(db_session, stake.stake_id, accumulated_rewards=Decimal("0"))
    svc = StakingService(db_session)
    svc.restore_claimed_rewards({stake.stake_id: Decimal("42")})
    assert _fresh_stake(db_session, stake.stake_id).accumulated_rewards == Decimal("42")
