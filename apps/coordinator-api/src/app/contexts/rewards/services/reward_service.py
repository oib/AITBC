"""
Agent Reward Engine Service
Implements performance-based reward calculations, distributions, and tier management
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlmodel import Session, and_, select

from aitbc import get_logger

from ....domain.reputation import AgentReputation
from ....domain.rewards import (
    AgentRewardProfile,
    RewardCalculation,
    RewardDistribution,
    RewardEvent,
    RewardMilestone,
    RewardStatus,
    RewardTier,
    RewardTierConfig,
    RewardType,
)

logger = get_logger(__name__)


class RewardCalculator:
    """Advanced reward calculation algorithms"""

    def __init__(self) -> None:
        self.base_rates = {
            "job_completion": 0.01,
            "high_performance": 0.005,
            "perfect_rating": 0.01,
            "on_time_delivery": 0.002,
            "repeat_client": 0.003,
        }
        self.performance_thresholds = {
            "excellent": 4.5,
            "good": 4.0,
            "response_time_fast": 2000,
            "response_time_excellent": 1000,
        }

    def calculate_tier_multiplier(self, trust_score: float, session: Session) -> float:
        """Calculate reward multiplier based on agent's tier"""
        tier_config = session.execute(
            select(RewardTierConfig)
            .where(and_(RewardTierConfig.min_trust_score <= trust_score, RewardTierConfig.is_active))
            .order_by(RewardTierConfig.min_trust_score.desc())
        ).first()  # type: ignore[attr-defined]
        if tier_config:
            return tier_config.base_multiplier  # type: ignore[no-any-return]
        elif trust_score >= 900:
            return 2.0
        elif trust_score >= 750:
            return 1.5
        elif trust_score >= 600:
            return 1.2
        elif trust_score >= 400:
            return 1.1
        else:
            return 1.0

    def calculate_performance_bonus(self, performance_metrics: dict[str, Any], session: Session) -> float:
        """Calculate performance-based bonus multiplier"""
        bonus = 0.0
        rating = performance_metrics.get("performance_rating", 3.0)
        if rating >= self.performance_thresholds["excellent"]:
            bonus += 0.5
        elif rating >= self.performance_thresholds["good"]:
            bonus += 0.2
        response_time = performance_metrics.get("average_response_time", 5000)
        if response_time <= self.performance_thresholds["response_time_excellent"]:
            bonus += 0.3
        elif response_time <= self.performance_thresholds["response_time_fast"]:
            bonus += 0.1
        success_rate = performance_metrics.get("success_rate", 80.0)
        if success_rate >= 95.0:
            bonus += 0.2
        elif success_rate >= 90.0:
            bonus += 0.1
        job_count = performance_metrics.get("jobs_completed", 0)
        if job_count >= 100:
            bonus += 0.15
        elif job_count >= 50:
            bonus += 0.1
        return bonus

    def calculate_loyalty_bonus(self, agent_id: str, session: Session) -> float:
        """Calculate loyalty bonus based on agent history"""
        reward_profile = session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()
        if not reward_profile:
            return 0.0
        bonus = 0.0
        if reward_profile.current_streak >= 30:
            bonus += 0.3
        elif reward_profile.current_streak >= 14:
            bonus += 0.2
        elif reward_profile.current_streak >= 7:
            bonus += 0.1
        if reward_profile.lifetime_earnings >= 1000:
            bonus += 0.2
        elif reward_profile.lifetime_earnings >= 500:
            bonus += 0.1
        if reward_profile.referral_count >= 10:
            bonus += 0.2
        elif reward_profile.referral_count >= 5:
            bonus += 0.1
        if reward_profile.community_contributions >= 20:
            bonus += 0.15
        elif reward_profile.community_contributions >= 10:
            bonus += 0.1
        return bonus

    def calculate_referral_bonus(self, referral_data: dict[str, Any]) -> float:
        """Calculate referral bonus"""
        referral_count = referral_data.get("referral_count", 0)
        referral_quality = referral_data.get("referral_quality", 1.0)
        base_bonus = 0.05 * referral_count
        quality_multiplier = 0.5 + referral_quality * 0.5
        return base_bonus * quality_multiplier  # type: ignore[no-any-return]

    def calculate_milestone_bonus(self, agent_id: str, session: Session) -> float:
        """Calculate milestone achievement bonus"""
        milestones = session.execute(
            select(RewardMilestone).where(
                and_(RewardMilestone.agent_id == agent_id, RewardMilestone.is_completed, not RewardMilestone.is_claimed)
            )
        ).all()
        total_bonus = 0.0
        for milestone in milestones:
            total_bonus += milestone.reward_amount
            milestone.is_claimed = True
            milestone.claimed_at = datetime.now(UTC)
        return total_bonus

    def calculate_total_reward(
        self, agent_id: str, base_amount: float, performance_metrics: dict[str, Any], session: Session
    ) -> dict[str, Any]:
        """Calculate total reward with all bonuses and multipliers"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        trust_score = reputation.trust_score if reputation else 500.0
        tier_multiplier = self.calculate_tier_multiplier(trust_score, session)
        performance_bonus = self.calculate_performance_bonus(performance_metrics, session)
        loyalty_bonus = self.calculate_loyalty_bonus(agent_id, session)
        referral_bonus = self.calculate_referral_bonus(performance_metrics.get("referral_data", {}))
        milestone_bonus = self.calculate_milestone_bonus(agent_id, session)
        effective_multiplier = tier_multiplier * (1 + performance_bonus + loyalty_bonus)
        total_reward = base_amount * effective_multiplier + referral_bonus + milestone_bonus
        return {
            "base_amount": base_amount,
            "tier_multiplier": tier_multiplier,
            "performance_bonus": performance_bonus,
            "loyalty_bonus": loyalty_bonus,
            "referral_bonus": referral_bonus,
            "milestone_bonus": milestone_bonus,
            "effective_multiplier": effective_multiplier,
            "total_reward": total_reward,
            "trust_score": trust_score,
        }


class RewardEngine:
    """Main reward management and distribution engine"""

    def __init__(self, session: Session):
        self.session = session
        self.calculator = RewardCalculator()

    async def create_reward_profile(self, agent_id: str) -> AgentRewardProfile:
        """Create a new reward profile for an agent"""
        existing = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()
        if existing:
            return existing  # type: ignore[return-value]
        profile = AgentRewardProfile(
            agent_id=agent_id,
            current_tier=RewardTier.BRONZE,
            tier_progress=0.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        logger.info("Created reward profile for agent %s", agent_id)
        return profile

    async def calculate_and_distribute_reward(
        self,
        agent_id: str,
        reward_type: RewardType,
        base_amount: float,
        performance_metrics: dict[str, Any],
        reference_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Calculate and distribute reward for an agent"""
        await self.create_reward_profile(agent_id)
        reward_calculation = self.calculator.calculate_total_reward(agent_id, base_amount, performance_metrics, self.session)
        calculation = RewardCalculation(
            agent_id=agent_id,
            reward_type=reward_type,
            base_amount=base_amount,
            tier_multiplier=reward_calculation["tier_multiplier"],
            performance_bonus=reward_calculation["performance_bonus"],
            loyalty_bonus=reward_calculation["loyalty_bonus"],
            referral_bonus=reward_calculation["referral_bonus"],
            milestone_bonus=reward_calculation["milestone_bonus"],
            total_reward=reward_calculation["total_reward"],
            effective_multiplier=reward_calculation["effective_multiplier"],
            reference_date=reference_date or datetime.now(UTC),
            trust_score_at_calculation=reward_calculation["trust_score"],
            performance_metrics=performance_metrics,
            calculated_at=datetime.now(UTC),
        )
        self.session.add(calculation)
        self.session.commit()
        self.session.refresh(calculation)
        distribution = RewardDistribution(
            calculation_id=calculation.id,
            agent_id=agent_id,
            reward_amount=reward_calculation["total_reward"],
            reward_type=reward_type,
            status=RewardStatus.PENDING,
            created_at=datetime.now(UTC),
            scheduled_at=datetime.now(UTC),
        )
        self.session.add(distribution)
        self.session.commit()
        self.session.refresh(distribution)
        await self.process_reward_distribution(distribution.id)
        await self.update_agent_reward_profile(agent_id, reward_calculation)
        await self.create_reward_event(
            agent_id,
            "reward_distributed",
            reward_type,
            reward_calculation["total_reward"],
            calculation_id=calculation.id,
            distribution_id=distribution.id,
        )
        return {
            "calculation_id": calculation.id,
            "distribution_id": distribution.id,
            "reward_amount": reward_calculation["total_reward"],
            "reward_type": reward_type,
            "tier_multiplier": reward_calculation["tier_multiplier"],
            "total_bonus": reward_calculation["performance_bonus"] + reward_calculation["loyalty_bonus"],
            "status": "distributed",
        }

    async def process_reward_distribution(self, distribution_id: str) -> RewardDistribution:
        """Process a reward distribution"""
        distribution = self.session.execute(select(RewardDistribution).where(RewardDistribution.id == distribution_id)).first()
        if not distribution:
            raise ValueError(f"Distribution {distribution_id} not found")
        if distribution.status != RewardStatus.PENDING:
            return distribution  # type: ignore[return-value]
        try:
            transaction_id = f"tx_{uuid4().hex[:8]}"
            transaction_hash = f"0x{uuid4().hex}"
            distribution.transaction_id = transaction_id
            distribution.transaction_hash = transaction_hash
            distribution.transaction_status = "confirmed"
            distribution.status = RewardStatus.DISTRIBUTED
            distribution.processed_at = datetime.now(UTC)
            distribution.confirmed_at = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(distribution)
            logger.info("Processed reward distribution %s for agent %s", distribution_id, distribution.agent_id)
        except Exception as e:
            distribution.status = RewardStatus.CANCELLED
            distribution.error_message = str(e)
            distribution.retry_count += 1
            self.session.commit()
            logger.error("Failed to process reward distribution %s: %s", distribution_id, str(e))
            raise
        return distribution  # type: ignore[return-value]

    async def update_agent_reward_profile(self, agent_id: str, reward_calculation: dict[str, Any]) -> None:
        """Update agent reward profile after reward distribution"""
        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()
        if not profile:
            return
        profile.base_earnings += reward_calculation["base_amount"]
        profile.bonus_earnings += reward_calculation["total_reward"] - reward_calculation["base_amount"]
        profile.total_earnings += reward_calculation["total_reward"]
        profile.lifetime_earnings += reward_calculation["total_reward"]
        profile.rewards_distributed += 1
        profile.last_reward_date = datetime.now(UTC)
        profile.current_streak += 1
        if profile.current_streak > profile.longest_streak:
            profile.longest_streak = profile.current_streak
        profile.performance_score = reward_calculation.get("performance_rating", 0.0)
        await self.check_and_update_tier(agent_id)
        profile.updated_at = datetime.now(UTC)
        profile.last_activity = datetime.now(UTC)
        self.session.commit()

    async def check_and_update_tier(self, agent_id: str) -> None:
        """Check and update agent's reward tier"""
        reputation = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return
        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()
        if not profile:
            return
        new_tier = self.determine_reward_tier(reputation.trust_score)
        old_tier = profile.current_tier
        if new_tier != old_tier:
            profile.current_tier = new_tier
            profile.updated_at = datetime.now(UTC)
            await self.create_reward_event(agent_id, "tier_upgrade", RewardType.SPECIAL_BONUS, 0.0, tier_impact=new_tier)
            logger.info("Agent %s upgraded from %s to %s", agent_id, old_tier, new_tier)

    def determine_reward_tier(self, trust_score: float) -> RewardTier:
        """Determine reward tier based on trust score"""
        if trust_score >= 950:
            return RewardTier.DIAMOND
        elif trust_score >= 850:
            return RewardTier.PLATINUM
        elif trust_score >= 750:
            return RewardTier.GOLD
        elif trust_score >= 600:
            return RewardTier.SILVER
        else:
            return RewardTier.BRONZE

    async def create_reward_event(
        self,
        agent_id: str,
        event_type: str,
        reward_type: RewardType,
        reward_impact: float,
        calculation_id: str | None = None,
        distribution_id: str | None = None,
        tier_impact: RewardTier | None = None,
    ) -> None:
        """Create a reward event record"""
        event = RewardEvent(
            agent_id=agent_id,
            event_type=event_type,
            trigger_source="automatic",
            reward_impact=reward_impact,
            tier_impact=tier_impact,
            related_calculation_id=calculation_id,
            related_distribution_id=distribution_id,
            occurred_at=datetime.now(UTC),
            processed_at=datetime.now(UTC),
        )
        self.session.add(event)
        self.session.commit()

    async def get_reward_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive reward summary for an agent"""
        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()
        if not profile:
            return {"error": "Reward profile not found"}
        recent_calculations = self.session.execute(
            select(RewardCalculation)
            .where(
                and_(
                    RewardCalculation.agent_id == agent_id,
                    RewardCalculation.calculated_at >= datetime.now(UTC) - timedelta(days=30),
                )
            )
            .order_by(RewardCalculation.calculated_at.desc())
            .limit(10)
        ).all()  # type: ignore[attr-defined]
        recent_distributions = self.session.execute(
            select(RewardDistribution)
            .where(
                and_(
                    RewardDistribution.agent_id == agent_id,
                    RewardDistribution.created_at >= datetime.now(UTC) - timedelta(days=30),
                )
            )
            .order_by(RewardDistribution.created_at.desc())
            .limit(10)
        ).all()  # type: ignore[attr-defined]
        return {
            "agent_id": agent_id,
            "current_tier": profile.current_tier.value,
            "tier_progress": profile.tier_progress,
            "base_earnings": profile.base_earnings,
            "bonus_earnings": profile.bonus_earnings,
            "total_earnings": profile.total_earnings,
            "lifetime_earnings": profile.lifetime_earnings,
            "rewards_distributed": profile.rewards_distributed,
            "current_streak": profile.current_streak,
            "longest_streak": profile.longest_streak,
            "performance_score": profile.performance_score,
            "loyalty_score": profile.loyalty_score,
            "referral_count": profile.referral_count,
            "community_contributions": profile.community_contributions,
            "last_reward_date": profile.last_reward_date.isoformat() if profile.last_reward_date else None,
            "recent_calculations": [
                {
                    "reward_type": calc.reward_type.value,
                    "total_reward": calc.total_reward,
                    "calculated_at": calc.calculated_at.isoformat(),
                }
                for calc in recent_calculations
            ],
            "recent_distributions": [
                {"reward_amount": dist.reward_amount, "status": dist.status.value, "created_at": dist.created_at.isoformat()}
                for dist in recent_distributions
            ],
        }

    async def batch_process_pending_rewards(self, limit: int = 100) -> dict[str, Any]:
        """Process pending reward distributions in batch"""
        pending_distributions = self.session.execute(
            select(RewardDistribution)
            .where(
                and_(RewardDistribution.status == RewardStatus.PENDING, RewardDistribution.scheduled_at <= datetime.now(UTC))
            )
            .order_by(RewardDistribution.priority.asc(), RewardDistribution.created_at.asc())
            .limit(limit)
        ).all()  # type: ignore[attr-defined, operator]
        processed = 0
        failed = 0
        for distribution in pending_distributions:
            try:
                await self.process_reward_distribution(distribution.id)
                processed += 1
            except Exception as e:
                failed += 1
                logger.error("Failed to process distribution %s: %s", distribution.id, str(e))
        return {"processed": processed, "failed": failed, "total": len(pending_distributions)}

    async def get_reward_analytics(
        self, period_type: str = "daily", start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, Any]:
        """Get reward system analytics"""
        if not start_date:
            start_date = datetime.now(UTC) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(UTC)
        distributions = self.session.execute(
            select(RewardDistribution)
            .where(
                and_(
                    RewardDistribution.created_at >= start_date,
                    RewardDistribution.created_at <= end_date,
                    RewardDistribution.status == RewardStatus.DISTRIBUTED,
                )
            )
            .all()
        )  # type: ignore[attr-defined]
        if not distributions:
            return {
                "period_type": period_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_rewards_distributed": 0.0,
                "total_agents_rewarded": 0,
                "average_reward_per_agent": 0.0,
            }
        total_rewards = sum(d.reward_amount for d in distributions)
        unique_agents = len({d.agent_id for d in distributions})
        average_reward = total_rewards / unique_agents if unique_agents > 0 else 0.0
        agent_ids = list({d.agent_id for d in distributions})
        profiles = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id.in_(agent_ids))).all()  # type: ignore[attr-defined]
        tier_distribution: dict[str, int] = {}
        for profile in profiles:
            tier = profile.current_tier.value
            tier_distribution[tier] = tier_distribution.get(tier, 0) + 1
        return {
            "period_type": period_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_rewards_distributed": total_rewards,
            "total_agents_rewarded": unique_agents,
            "average_reward_per_agent": average_reward,
            "tier_distribution": tier_distribution,
            "total_distributions": len(distributions),
        }  # type: ignore[arg-type]
