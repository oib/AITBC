"""#2817: reward engine must not fabricate payouts or unbounded bonuses.

``process_reward_distribution`` used to invent ``tx_<uuid>``/``0x<uuid>``
hashes, stamp ``transaction_status='confirmed'`` and flip the row to
DISTRIBUTED — recording money movement that never happened. With no
on-chain payout rail it must refuse and leave the row PENDING.
``calculate_referral_bonus`` took caller-influenced ``referral_count`` /
``referral_quality`` unbounded — negative or huge inputs produced
negative or unbounded flat bonus money.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.rewards.domain.rewards import (
    AgentRewardProfile,
    RewardCalculation,
    RewardDistribution,
    RewardStatus,
    RewardTier,
    RewardType,
)
from coordinator_api.contexts.rewards.services.reward_service import (
    RewardCalculator,
    RewardEngine,
)


def _profile(session: Session, agent_id: str) -> AgentRewardProfile:
    profile = AgentRewardProfile(agent_id=agent_id, current_tier=RewardTier.BRONZE)
    session.add(profile)
    session.commit()
    return profile


def _pending_distribution(session: Session, agent_id: str) -> RewardDistribution:
    calc = RewardCalculation(
        agent_id=agent_id,
        reward_type=RewardType.PERFORMANCE_BONUS,
        base_amount=Decimal("1"),
        total_reward=Decimal("1"),
        trust_score_at_calculation=Decimal("500"),
    )
    session.add(calc)
    session.commit()
    dist = RewardDistribution(
        calculation_id=calc.id,
        agent_id=agent_id,
        reward_amount=Decimal("1"),
        reward_type=RewardType.PERFORMANCE_BONUS,
        status=RewardStatus.PENDING,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(dist)
    session.commit()
    return dist


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_reward_distribution_refuses_to_fabricate(db_engine) -> None:
    """A PENDING row must stay PENDING with no invented tx fields."""
    with Session(db_engine) as session:
        agent_id = "agent-fake-payout"
        _profile(session, agent_id)
        dist = _pending_distribution(session, agent_id)
        dist_id = dist.id

        engine = RewardEngine(session)
        with pytest.raises(RuntimeError, match="not implemented"):
            await engine.process_reward_distribution(dist_id)

        session.expire_all()
        row = session.get(RewardDistribution, dist_id)
        assert row is not None
        assert row.status == RewardStatus.PENDING
        assert row.transaction_id is None
        assert row.transaction_hash is None
        assert row.transaction_status == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_and_distribute_does_not_mark_distributed(db_engine) -> None:
    """The full path must surface the missing rail, not report 'distributed'."""
    with Session(db_engine) as session:
        agent_id = "agent-calc-dist"
        engine = RewardEngine(session)
        with pytest.raises(RuntimeError, match="not implemented"):
            await engine.calculate_and_distribute_reward(
                agent_id,
                RewardType.PERFORMANCE_BONUS,
                Decimal("1"),
                {},
            )

        dists = session.execute(select(RewardDistribution).where(RewardDistribution.agent_id == agent_id)).scalars().all()
        assert len(dists) == 1
        assert dists[0].status == RewardStatus.PENDING
        assert dists[0].transaction_hash is None
        profile = session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).scalars().first()
        assert profile is not None
        assert profile.lifetime_earnings == Decimal("0")


@pytest.mark.unit
def test_referral_bonus_rejects_negative_and_huge_inputs() -> None:
    calc = RewardCalculator()
    # Negative quality used to drive the multiplier below zero; it now
    # clamps to 0 -> multiplier floor 0.5.
    assert calc.calculate_referral_bonus({"referral_count": 10, "referral_quality": -5}) == Decimal("0.25")
    # Huge quality used to multiply the bonus without bound.
    bounded = calc.calculate_referral_bonus({"referral_count": 1, "referral_quality": 10**9})
    assert bounded == Decimal("0.05") * (Decimal("0.5") + Decimal("1") * Decimal("0.5"))
    # Non-finite / garbage quality falls back to the neutral default.
    for bad in ("nan", "inf", "-inf", "not-a-number", None, object()):
        got = calc.calculate_referral_bonus({"referral_count": 2, "referral_quality": bad})
        assert got == Decimal("0.1") * (Decimal("0.5") + Decimal("1.0") * Decimal("0.5")), bad


@pytest.mark.unit
def test_referral_bonus_bounds_count() -> None:
    calc = RewardCalculator()
    # Negative count used to subtract bonus money.
    assert calc.calculate_referral_bonus({"referral_count": -50}) == Decimal("0")
    # Absurd counts are capped — the bonus is a flat addend.
    capped = calc.calculate_referral_bonus({"referral_count": 10**9})
    assert capped == Decimal("0.05") * 100 * Decimal("1.0")
    # Garbage count degrades to zero rather than raising.
    assert calc.calculate_referral_bonus({"referral_count": "junk"}) == Decimal("0")
