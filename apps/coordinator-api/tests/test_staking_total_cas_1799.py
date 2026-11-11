"""#1799: staking ``total_staked`` updates are atomic SQL-side increments.

Before the fix, ``AgentMetrics.total_staked`` and ``StakingPool.total_staked``
were updated via ORM read-modify-write (``metrics.total_staked += amount``) —
two concurrent stake/unstake calls could both read the same total and one
increment was silently lost. The writes are now ``UPDATE ... SET
 total_staked = total_staked + delta`` executed in SQL.

Pins use the stale-identity-map trick: an interfering write goes through
``synchronize_session=False`` so the cached ORM object keeps its old value,
exactly like a reader that fetched before a concurrent commit — only the
SQL-side arithmetic produces the correct total.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, col, select, update

from coordinator_api.contexts.staking.domain.staking import (
    AgentMetrics,
    PerformanceTier,
    StakingPool,
)
from coordinator_api.contexts.staking.services.staking_service import StakingService

AGENT = "0x" + "aa" * 20
STAKER = "0x" + "bb" * 20


def _metrics(session: Session, total: str = "0") -> AgentMetrics:
    m = AgentMetrics(agent_wallet=AGENT, total_staked=Decimal(total), current_tier=PerformanceTier.BRONZE)
    session.add(m)
    session.commit()
    return m


def _total(session: Session) -> Decimal:
    session.expire_all()
    return session.execute(select(AgentMetrics.total_staked).where(AgentMetrics.agent_wallet == AGENT)).scalar_one()


def _pool_total(session: Session) -> Decimal:
    session.expire_all()
    row = session.execute(select(StakingPool.total_staked).where(StakingPool.agent_wallet == AGENT)).scalar_one_or_none()
    return Decimal(str(row)) if row is not None else Decimal("0")


@pytest.mark.unit
def test_bump_total_staked_accumulates_in_sql(db_session):
    _metrics(db_session, "100")
    svc = StakingService(db_session)
    svc._bump_total_staked(AGENT, Decimal("50"))
    svc._bump_total_staked(AGENT, Decimal("25"))
    db_session.commit()
    assert _total(db_session) == Decimal("175")


@pytest.mark.unit
def test_create_stake_total_survives_stale_metrics_read(db_session):
    """A concurrent bump lands between the metrics read and the stake write;
    the ORM += would have written back the stale total — the SQL increment
    must add onto the landed value instead."""
    _metrics(db_session, "100")
    svc = StakingService(db_session)
    # Warm the identity map, then a concurrent writer bumps +50 behind its back.
    assert db_session.execute(
        select(AgentMetrics).where(AgentMetrics.agent_wallet == AGENT)
    ).scalar_one().total_staked == Decimal("100")
    db_session.execute(
        update(AgentMetrics)
        .where(col(AgentMetrics.agent_wallet) == AGENT)
        .values(total_staked=AgentMetrics.total_staked + Decimal("50"))
        .execution_options(synchronize_session=False)
    )
    db_session.commit()
    svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=30, auto_compound=False)
    # DB truth: 100 + 50 (concurrent) + 150 (this stake) — not 100 + 150.
    assert _total(db_session) == Decimal("300")
    assert _pool_total(db_session) == Decimal("150")


@pytest.mark.unit
def test_unbond_decrements_atomically(db_session):
    _metrics(db_session, "300")
    svc = StakingService(db_session)
    stake = svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=1, auto_compound=False)
    # Force the lock period into the past so unbond is allowed.
    stake.end_time = datetime.now(UTC) - timedelta(days=1)
    db_session.add(stake)
    db_session.commit()
    svc.unbond_stake(stake.stake_id)
    # A concurrent +50 lands while the stake sits in UNBONDING.
    db_session.execute(
        update(AgentMetrics)
        .where(col(AgentMetrics.agent_wallet) == AGENT)
        .values(total_staked=AgentMetrics.total_staked + Decimal("50"))
        .execution_options(synchronize_session=False)
    )
    db_session.commit()
    svc.complete_unbonding(stake.stake_id)
    # 300 + 150 (stake) + 50 (concurrent) - 150 (unbonded) = 350.
    assert _total(db_session) == Decimal("350")
    assert _pool_total(db_session) == Decimal("0")


@pytest.mark.unit
def test_add_to_stake_increments_atomically(db_session):
    _metrics(db_session, "0")
    svc = StakingService(db_session)
    stake = svc.create_stake(STAKER, AGENT, Decimal("150"), lock_period=30, auto_compound=False)
    before = _total(db_session)
    svc.add_to_stake(stake.stake_id, Decimal("60"))
    assert _total(db_session) == before + Decimal("60")
