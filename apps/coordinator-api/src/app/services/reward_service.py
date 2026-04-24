"""
Agent Reward Engine Service
Implements performance-based reward calculations, distributions, and tier management
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)

from sqlmodel import Session, and_, select

from ..domain.reputation import AgentReputation
from ..domain.rewards import (
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


class RewardCalculator:
    """Advanced reward calculation algorithms"""

    def __init__(self):
        # Base reward rates (in AITBC)
        self.base_rates = {
            "job_completion": 0.01,  # Base reward per job
            "high_performance": 0.005,  # Additional for high performance
            "perfect_rating": 0.01,  # Bonus for 5-star ratings
            "on_time_delivery": 0.002,  # Bonus for on-time delivery
            "repeat_client": 0.003,  # Bonus for repeat clients
        }

        # Performance thresholds
        self.performance_thresholds = {
            "excellent": 4.5,  # Rating threshold for excellent performance
            "good": 4.0,  # Rating threshold for good performance
            "response_time_fast": 2000,  # Response time in ms for fast
            "response_time_excellent": 1000,  # Response time in ms for excellent
        }

    def calculate_tier_multiplier(self, trust_score: float, session: Session) -> float:
        """Calculate reward multiplier based on agent's tier"""

        # Get tier configuration
        tier_config = session.execute(
            select(RewardTierConfig)
            .where(and_(RewardTierConfig.min_trust_score <= trust_score, RewardTierConfig.is_active))
            .order_by(RewardTierConfig.min_trust_score.desc())
        ).first()

        if tier_config:
            return tier_config.base_multiplier
        else:
            # Default tier calculation if no config found
            if trust_score >= 900:
                return 2.0  # Diamond
            elif trust_score >= 750:
                return 1.5  # Platinum
            elif trust_score >= 600:
                return 1.2  # Gold
            elif trust_score >= 400:
                return 1.1  # Silver
            else:
                return 1.0  # Bronze

    def calculate_performance_bonus(self, performance_metrics: dict[str, Any], session: Session) -> float:
        """Calculate performance-based bonus multiplier"""

        bonus = 0.0

        # Rating bonus
        rating = performance_metrics.get("performance_rating", 3.0)
        if rating >= self.performance_thresholds["excellent"]:
            bonus += 0.5  # 50% bonus for excellent performance
        elif rating >= self.performance_thresholds["good"]:
            bonus += 0.2  # 20% bonus for good performance

        # Response time bonus
        response_time = performance_metrics.get("average_response_time", 5000)
        if response_time <= self.performance_thresholds["response_time_excellent"]:
            bonus += 0.3  # 30% bonus for excellent response time
        elif response_time <= self.performance_thresholds["response_time_fast"]:
            bonus += 0.1  # 10% bonus for fast response time

        # Success rate bonus
        success_rate = performance_metrics.get("success_rate", 80.0)
        if success_rate >= 95.0:
            bonus += 0.2  # 20% bonus for excellent success rate
        elif success_rate >= 90.0:
            bonus += 0.1  # 10% bonus for good success rate

        # Job volume bonus
        job_count = performance_metrics.get("jobs_completed", 0)
        if job_count >= 100:
            bonus += 0.15  # 15% bonus for high volume
        elif job_count >= 50:
            bonus += 0.1  # 10% bonus for moderate volume

        return bonus

    def calculate_loyalty_bonus(self, agent_id: str, session: Session) -> float:
        """Calculate loyalty bonus based on agent history"""

        # Get agent reward profile
        reward_profile = session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()

        if not reward_profile:
            return 0.0

        bonus = 0.0

        # Streak bonus
        if reward_profile.current_streak >= 30:  # 30+ day streak
            bonus += 0.3
        elif reward_profile.current_streak >= 14:  # 14+ day streak
            bonus += 0.2
        elif reward_profile.current_streak >= 7:  # 7+ day streak
            bonus += 0.1

        # Lifetime earnings bonus
        if reward_profile.lifetime_earnings >= 1000:  # 1000+ AITBC
            bonus += 0.2
        elif reward_profile.lifetime_earnings >= 500:  # 500+ AITBC
            bonus += 0.1

        # Referral bonus
        if reward_profile.referral_count >= 10:
            bonus += 0.2
        elif reward_profile.referral_count >= 5:
            bonus += 0.1

        # Community contributions bonus
        if reward_profile.community_contributions >= 20:
            bonus += 0.15
        elif reward_profile.community_contributions >= 10:
            bonus += 0.1

        return bonus

    def calculate_referral_bonus(self, referral_data: dict[str, Any]) -> float:
        """Calculate referral bonus"""

        referral_count = referral_data.get("referral_count", 0)
        referral_quality = referral_data.get("referral_quality", 1.0)  # 0-1 scale

        base_bonus = 0.05 * referral_count  # 0.05 AITBC per referral

        # Quality multiplier
        quality_multiplier = 0.5 + (referral_quality * 0.5)  # 0.5 to 1.0

        return base_bonus * quality_multiplier

    def calculate_milestone_bonus(self, agent_id: str, session: Session) -> float:
        """Calculate milestone achievement bonus"""

        # Check for unclaimed milestones
        milestones = session.execute(
            select(RewardMilestone).where(
                and_(
                    RewardMilestone.agent_id == agent_id,
                    RewardMilestone.is_completed,
                    not RewardMilestone.is_claimed,
                )
            )
        ).all()

        total_bonus = 0.0
        for milestone in milestones:
            total_bonus += milestone.reward_amount

            # Mark as claimed
            milestone.is_claimed = True
            milestone.claimed_at = datetime.utcnow()

        return total_bonus

    def calculate_total_reward(
        self, agent_id: str, base_amount: float, performance_metrics: dict[str, Any], session: Session
    ) -> dict[str, Any]:
        """Calculate total reward with all bonuses and multipliers"""

        # Get agent's trust score and tier
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()

        trust_score = reputation.trust_score if reputation else 500.0

        # Calculate components
        tier_multiplier = self.calculate_tier_multiplier(trust_score, session)
        performance_bonus = self.calculate_performance_bonus(performance_metrics, session)
        loyalty_bonus = self.calculate_loyalty_bonus(agent_id, session)
        referral_bonus = self.calculate_referral_bonus(performance_metrics.get("referral_data", {}))
        milestone_bonus = self.calculate_milestone_bonus(agent_id, session)

        # Calculate effective multiplier
        effective_multiplier = tier_multiplier * (1 + performance_bonus + loyalty_bonus)

        # Calculate total reward
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

        # Check if profile already exists
        existing = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()

        if existing:
            return existing

        # Create new reward profile
        profile = AgentRewardProfile(
            agent_id=agent_id,
            current_tier=RewardTier.BRONZE,
            tier_progress=0.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)

        logger.info(f"Created reward profile for agent {agent_id}")
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

        # Ensure reward profile exists
        await self.create_reward_profile(agent_id)

        # Calculate reward
        reward_calculation = self.calculator.calculate_total_reward(agent_id, base_amount, performance_metrics, self.session)

        # Create calculation record
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
            reference_date=reference_date or datetime.utcnow(),
            trust_score_at_calculation=reward_calculation["trust_score"],
            performance_metrics=performance_metrics,
            calculated_at=datetime.utcnow(),
        )

        self.session.add(calculation)
        self.session.commit()
        self.session.refresh(calculation)

        # Create distribution record
        distribution = RewardDistribution(
            calculation_id=calculation.id,
            agent_id=agent_id,
            reward_amount=reward_calculation["total_reward"],
            reward_type=reward_type,
            status=RewardStatus.PENDING,
            created_at=datetime.utcnow(),
            scheduled_at=datetime.utcnow(),
        )

        self.session.add(distribution)
        self.session.commit()
        self.session.refresh(distribution)

        # Process distribution
        await self.process_reward_distribution(distribution.id)

        # Update agent profile
        await self.update_agent_reward_profile(agent_id, reward_calculation)

        # Create reward event
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
            return distribution

        try:
            # Simulate blockchain transaction (in real implementation, this would interact with blockchain)
            transaction_id = f"tx_{uuid4().hex[:8]}"
            transaction_hash = f"0x{uuid4().hex}"

            # Update distribution
            distribution.transaction_id = transaction_id
            distribution.transaction_hash = transaction_hash
            distribution.transaction_status = "confirmed"
            distribution.status = RewardStatus.DISTRIBUTED
            distribution.processed_at = datetime.utcnow()
            distribution.confirmed_at = datetime.utcnow()

            self.session.commit()
            self.session.refresh(distribution)

            logger.info(f"Processed reward distribution {distribution_id} for agent {distribution.agent_id}")

        except Exception as e:
            # Handle distribution failure
            distribution.status = RewardStatus.CANCELLED
            distribution.error_message = str(e)
            distribution.retry_count += 1
            self.session.commit()

            logger.error(f"Failed to process reward distribution {distribution_id}: {str(e)}")
            raise

        return distribution

    async def update_agent_reward_profile(self, agent_id: str, reward_calculation: dict[str, Any]):
        """Update agent reward profile after reward distribution"""

        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()

        if not profile:
            return

        # Update earnings
        profile.base_earnings += reward_calculation["base_amount"]
        profile.bonus_earnings += reward_calculation["total_reward"] - reward_calculation["base_amount"]
        profile.total_earnings += reward_calculation["total_reward"]
        profile.lifetime_earnings += reward_calculation["total_reward"]

        # Update reward count and streak
        profile.rewards_distributed += 1
        profile.last_reward_date = datetime.utcnow()
        profile.current_streak += 1
        if profile.current_streak > profile.longest_streak:
            profile.longest_streak = profile.current_streak

        # Update performance score
        profile.performance_score = reward_calculation.get("performance_rating", 0.0)

        # Check for tier upgrade
        await self.check_and_update_tier(agent_id)

        profile.updated_at = datetime.utcnow()
        profile.last_activity = datetime.utcnow()

        self.session.commit()

    async def check_and_update_tier(self, agent_id: str):
        """Check and update agent's reward tier"""

        # Get agent reputation
        reputation = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()

        if not reputation:
            return

        # Get reward profile
        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()

        if not profile:
            return

        # Determine new tier
        new_tier = self.determine_reward_tier(reputation.trust_score)
        old_tier = profile.current_tier

        if new_tier != old_tier:
            # Update tier
            profile.current_tier = new_tier
            profile.updated_at = datetime.utcnow()

            # Create tier upgrade event
            await self.create_reward_event(agent_id, "tier_upgrade", RewardType.SPECIAL_BONUS, 0.0, tier_impact=new_tier)

            logger.info(f"Agent {agent_id} upgraded from {old_tier} to {new_tier}")

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
    ):
        """Create a reward event record"""

        event = RewardEvent(
            agent_id=agent_id,
            event_type=event_type,
            trigger_source="automatic",
            reward_impact=reward_impact,
            tier_impact=tier_impact,
            related_calculation_id=calculation_id,
            related_distribution_id=distribution_id,
            occurred_at=datetime.utcnow(),
            processed_at=datetime.utcnow(),
        )

        self.session.add(event)
        self.session.commit()

    async def get_reward_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive reward summary for an agent"""

        profile = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id == agent_id)).first()

        if not profile:
            return {"error": "Reward profile not found"}

        # Get recent calculations
        recent_calculations = self.session.execute(
            select(RewardCalculation)
            .where(
                and_(
                    RewardCalculation.agent_id == agent_id,
                    RewardCalculation.calculated_at >= datetime.utcnow() - timedelta(days=30),
                )
            )
            .order_by(RewardCalculation.calculated_at.desc())
            .limit(10)
        ).all()

        # Get recent distributions
        recent_distributions = self.session.execute(
            select(RewardDistribution)
            .where(
                and_(
                    RewardDistribution.agent_id == agent_id,
                    RewardDistribution.created_at >= datetime.utcnow() - timedelta(days=30),
                )
            )
            .order_by(RewardDistribution.created_at.desc())
            .limit(10)
        ).all()

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

        # Get pending distributions
        pending_distributions = self.session.execute(
            select(RewardDistribution)
            .where(
                and_(RewardDistribution.status == RewardStatus.PENDING, RewardDistribution.scheduled_at <= datetime.utcnow())
            )
            .order_by(RewardDistribution.priority.asc(), RewardDistribution.created_at.asc())
            .limit(limit)
        ).all()

        processed = 0
        failed = 0

        for distribution in pending_distributions:
            try:
                await self.process_reward_distribution(distribution.id)
                processed += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to process distribution {distribution.id}: {str(e)}")

        return {"processed": processed, "failed": failed, "total": len(pending_distributions)}

    async def get_reward_analytics(
        self, period_type: str = "daily", start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, Any]:
        """Get reward system analytics"""

        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        # Get distributions in period
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
        )

        if not distributions:
            return {
                "period_type": period_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_rewards_distributed": 0.0,
                "total_agents_rewarded": 0,
                "average_reward_per_agent": 0.0,
            }

        # Calculate analytics
        total_rewards = sum(d.reward_amount for d in distributions)
        unique_agents = len({d.agent_id for d in distributions})
        average_reward = total_rewards / unique_agents if unique_agents > 0 else 0.0

        # Get agent profiles for tier distribution
        agent_ids = list({d.agent_id for d in distributions})
        profiles = self.session.execute(select(AgentRewardProfile).where(AgentRewardProfile.agent_id.in_(agent_ids))).all()

        tier_distribution = {}
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
        }
