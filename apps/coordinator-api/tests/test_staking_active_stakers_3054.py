"""#3054: ``StakingPool.active_stakers`` membership is actually persisted.

``_update_staking_pool`` mutated the plain ``Column(JSON)`` list in place
(``.append()``/``.remove()``), which SQLAlchemy never marks dirty — and the
``session.refresh(pool)`` that reloads the #1799 atomic ``total_staked``
expires the object and discards even a rebound-but-unflushed value. The
column stayed at its insert-time ``[]`` forever, so pool staker membership
was never recorded.

Pins re-read through a FRESH Session (not ``expire_all`` on the writer
session): the defect is a missing UPDATE, so only a new session proves the
row on disk changed. Both the append (stake) and remove (unbond-complete)
paths are covered, and ``total_staked`` is asserted alongside to pin the
#1799 refresh mechanism the fix had to order around.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.staking.domain.staking import AgentMetrics, PerformanceTier, StakingPool
from coordinator_api.contexts.staking.services.staking_service import StakingService

AGENT = "0x" + "ee" * 20
STAKER = "0x" + "ff" * 20
STAKER2 = "0x" + "11" * 20


def _agent(session: Session) -> None:
    session.add(AgentMetrics(agent_wallet=AGENT, total_staked=Decimal("0"), current_tier=PerformanceTier.BRONZE))
    session.commit()


def _fresh_pool(session: Session) -> StakingPool | None:
    """Read the pool through a brand-new Session — proves the committed row."""
    fresh = Session(session.get_bind())
    try:
        return fresh.execute(select(StakingPool).where(StakingPool.agent_wallet == AGENT)).scalar_one_or_none()
    finally:
        fresh.close()


@pytest.mark.unit
def test_create_stake_persists_active_stakers(db_session):
    """Append path: a new staker must land in the committed JSON list."""
    _agent(db_session)
    svc = StakingService(db_session)
    svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=30, auto_compound=False)
    pool = _fresh_pool(db_session)
    assert pool is not None
    assert pool.active_stakers == [STAKER]
    # #1799 mechanism preserved: the refresh still reloads the landed total.
    assert pool.total_staked == Decimal("150")


@pytest.mark.unit
def test_second_staker_appends_without_duplicating(db_session):
    """A second distinct staker joins; the first staker's second stake must
    not duplicate its address in the list."""
    _agent(db_session)
    svc = StakingService(db_session)
    svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=30, auto_compound=False)
    svc.create_stake(STAKER2, AGENT, Decimal("200"), lock_period=30, auto_compound=False)
    svc.create_stake(STAKER, AGENT, Decimal("100"), lock_period=90, auto_compound=False)
    pool = _fresh_pool(db_session)
    assert pool is not None
    assert sorted(pool.active_stakers) == sorted([STAKER, STAKER2])
    assert pool.total_staked == Decimal("450")


@pytest.mark.unit
def test_complete_unbonding_removes_staker(db_session):
    """Remove path: completing the last unbond removes the address and the
    pool total returns to zero — both in the committed row."""
    _agent(db_session)
    svc = StakingService(db_session)
    stake = svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=30, auto_compound=False)
    stake.end_time = datetime.now(UTC) - timedelta(days=1)
    db_session.add(stake)
    db_session.commit()
    svc.unbond_stake(stake.stake_id)
    svc.complete_unbonding(stake.stake_id)
    pool = _fresh_pool(db_session)
    assert pool is not None
    assert pool.active_stakers == []
    assert pool.total_staked == Decimal("0")
