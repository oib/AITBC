"""
Staking Management Service
Business logic for AI agent staking system with reputation-based yield farming
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from aitbc import get_logger
from ..domain.bounty import AgentMetrics, AgentStake, PerformanceTier, StakeStatus, StakingPool

logger = get_logger(__name__)


class StakingService:
    """Service for managing AI agent staking"""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _normalize_stake_datetimes(self, stake: AgentStake) -> AgentStake:
        stake.start_time = self._ensure_utc_datetime(stake.start_time)  # type: ignore[assignment]
        stake.end_time = self._ensure_utc_datetime(stake.end_time)  # type: ignore[assignment]
        stake.last_reward_time = self._ensure_utc_datetime(stake.last_reward_time)  # type: ignore[assignment]
        stake.unbonding_time = self._ensure_utc_datetime(stake.unbonding_time)  # type: ignore[assignment]
        return stake

    def _normalize_agent_metrics_datetimes(self, agent_metrics: AgentMetrics) -> AgentMetrics:
        agent_metrics.last_update_time = self._ensure_utc_datetime(agent_metrics.last_update_time)  # type: ignore[assignment]
        agent_metrics.first_submission_time = self._ensure_utc_datetime(agent_metrics.first_submission_time)  # type: ignore[assignment]
        return agent_metrics

    def _normalize_staking_pool_datetimes(self, staking_pool: StakingPool) -> StakingPool:
        staking_pool.last_distribution_time = self._ensure_utc_datetime(staking_pool.last_distribution_time)  # type: ignore[assignment]
        return staking_pool

    async def create_stake(
        self, staker_address: str, agent_wallet: str, amount: float, lock_period: int, auto_compound: bool
    ) -> AgentStake:
        """Create a new stake on an agent wallet"""
        try:
            # Validate agent is supported
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                raise ValueError("Agent not supported for staking")

            # Validate stake amount
            if amount < 100:
                raise ValueError("Stake amount must be at least 100 AITBC")

            # Calculate APY
            current_apy = await self.calculate_apy(agent_wallet, lock_period)

            # Calculate end time
            end_time = datetime.now(timezone.utc) + timedelta(days=lock_period)

            stake = AgentStake(
                staker_address=staker_address,
                agent_wallet=agent_wallet,
                amount=amount,
                lock_period=lock_period,
                end_time=end_time,
                current_apy=current_apy,
                agent_tier=agent_metrics.current_tier,
                auto_compound=auto_compound,
            )

            self.session.add(stake)

            # Update agent metrics
            agent_metrics.total_staked += amount
            # Check if this is the first stake from this staker
            existing_stakes = await self.get_user_stakes(staker_address, agent_wallet=agent_wallet)
            if not existing_stakes:
                agent_metrics.staker_count += 1

            # Update staking pool
            await self._update_staking_pool(agent_wallet, staker_address, amount, True)

            self.session.commit()
            self.session.refresh(stake)

            logger.info(f"Created stake {stake.stake_id}: {amount} on {agent_wallet}")
            return self._normalize_stake_datetimes(stake)

        except Exception as e:
            logger.error(f"Failed to create stake: {e}")
            self.session.rollback()
            raise

    async def get_stake(self, stake_id: str) -> AgentStake:
        """Get stake by ID"""
        try:
            stmt = select(AgentStake).where(AgentStake.stake_id == stake_id)
            result = self.session.execute(stmt).scalar_one_or_none()
            if not result:
                raise ValueError("Stake not found")
            return self._normalize_stake_datetimes(result)

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to get stake {stake_id}: {e}")
            raise

    async def get_user_stakes(
        self,
        user_address: str,
        status: StakeStatus | None = None,
        agent_wallet: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        agent_tier: PerformanceTier | None = None,
        auto_compound: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[AgentStake]:
        """Get filtered list of user's stakes"""
        try:
            query = select(AgentStake).where(AgentStake.staker_address == user_address)

            # Apply filters
            if status:
                query = query.where(AgentStake.status == status)
            if agent_wallet:
                query = query.where(AgentStake.agent_wallet == agent_wallet)
            if min_amount:
                query = query.where(AgentStake.amount >= min_amount)
            if max_amount:
                query = query.where(AgentStake.amount <= max_amount)
            if agent_tier:
                query = query.where(AgentStake.agent_tier == agent_tier)
            if auto_compound is not None:
                query = query.where(AgentStake.auto_compound == auto_compound)

            # Order by creation time (newest first)
            query = query.order_by(AgentStake.start_time.desc())

            # Apply pagination
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)

            result = self.session.execute(query).scalars().all()
            return [self._normalize_stake_datetimes(stake) for stake in result]

        except Exception as e:
            logger.error(f"Failed to get user stakes: {e}")
            raise

    async def add_to_stake(self, stake_id: str, additional_amount: float) -> AgentStake:
        """Add more tokens to an existing stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")

            if stake.status != StakeStatus.ACTIVE:
                raise ValueError("Stake is not active")

            # Update stake amount
            stake.amount += additional_amount

            # Recalculate APY
            stake.current_apy = await self.calculate_apy(stake.agent_wallet, stake.lock_period)

            # Update agent metrics
            agent_metrics = await self.get_agent_metrics(stake.agent_wallet)
            if agent_metrics:
                agent_metrics.total_staked += additional_amount

            # Update staking pool
            await self._update_staking_pool(stake.agent_wallet, stake.staker_address, additional_amount, True)

            self.session.commit()
            self.session.refresh(stake)

            logger.info(f"Added {additional_amount} to stake {stake_id}")
            return stake

        except Exception as e:
            logger.error(f"Failed to add to stake: {e}")
            self.session.rollback()
            raise

    async def unbond_stake(self, stake_id: str) -> AgentStake:
        """Initiate unbonding for a stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")

            if stake.status != StakeStatus.ACTIVE:
                raise ValueError("Stake is not active")

            if datetime.now(timezone.utc) < stake.end_time:
                raise ValueError("Lock period has not ended")

            # Calculate final rewards
            await self._calculate_rewards(stake_id)

            stake.status = StakeStatus.UNBONDING
            stake.unbonding_time = datetime.now(timezone.utc)

            self.session.commit()
            self.session.refresh(stake)

            logger.info(f"Initiated unbonding for stake {stake_id}")
            return stake

        except Exception as e:
            logger.error(f"Failed to unbond stake: {e}")
            self.session.rollback()
            raise

    async def complete_unbonding(self, stake_id: str) -> dict[str, float]:
        """Complete unbonding and return stake + rewards"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")

            if stake.status != StakeStatus.UNBONDING:
                raise ValueError("Stake is not unbonding")

            # Calculate penalty if applicable
            penalty = 0.0
            total_amount = stake.amount

            if stake.unbonding_time and datetime.now(timezone.utc) < stake.unbonding_time + timedelta(days=30):
                penalty = total_amount * 0.10  # 10% early unbond penalty
                total_amount -= penalty

            # Update status
            stake.status = StakeStatus.COMPLETED

            # Update agent metrics
            agent_metrics = await self.get_agent_metrics(stake.agent_wallet)
            if agent_metrics:
                agent_metrics.total_staked -= stake.amount
                # Check if this is the last stake from this staker
                remaining_stakes = await self.get_user_stakes(stake.staker_address, agent_wallet=stake.agent_wallet, status=StakeStatus.ACTIVE)
                if not remaining_stakes:
                    agent_metrics.staker_count -= 1

            # Update staking pool
            await self._update_staking_pool(stake.agent_wallet, stake.staker_address, stake.amount, False)

            self.session.commit()

            result = {"total_amount": total_amount, "total_rewards": stake.accumulated_rewards, "penalty": penalty}

            logger.info(f"Completed unbonding for stake {stake_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to complete unbonding: {e}")
            self.session.rollback()
            raise

    async def calculate_rewards(self, stake_id: str) -> float:
        """Calculate current rewards for a stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")

            if stake.status != StakeStatus.ACTIVE:
                return stake.accumulated_rewards

            # Calculate time-based rewards
            time_elapsed = datetime.now(timezone.utc) - stake.last_reward_time
            yearly_rewards = (stake.amount * stake.current_apy) / 100
            current_rewards = (yearly_rewards * time_elapsed.total_seconds()) / (365 * 24 * 3600)

            return stake.accumulated_rewards + current_rewards

        except Exception as e:
            logger.error(f"Failed to calculate rewards: {e}")
            raise

    async def get_agent_metrics(self, agent_wallet: str) -> AgentMetrics | None:
        """Get agent performance metrics"""
        try:
            stmt = select(AgentMetrics).where(AgentMetrics.agent_wallet == agent_wallet)
            result = self.session.execute(stmt).scalar_one_or_none()
            return self._normalize_agent_metrics_datetimes(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get agent metrics: {e}")
            raise

    async def get_staking_pool(self, agent_wallet: str) -> StakingPool | None:
        """Get staking pool for an agent"""
        try:
            stmt = select(StakingPool).where(StakingPool.agent_wallet == agent_wallet)
            result = self.session.execute(stmt).scalar_one_or_none()
            return self._normalize_staking_pool_datetimes(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get staking pool: {e}")
            raise

    async def calculate_apy(self, agent_wallet: str, lock_period: int) -> float:
        """Calculate APY for staking on an agent"""
        try:
            # Base APY
            base_apy = 5.0

            # Get agent metrics
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                return base_apy

            # Tier multiplier
            tier_multipliers = {
                PerformanceTier.BRONZE: 1.0,
                PerformanceTier.SILVER: 1.2,
                PerformanceTier.GOLD: 1.5,
                PerformanceTier.PLATINUM: 2.0,
                PerformanceTier.DIAMOND: 3.0,
            }

            tier_multiplier = tier_multipliers.get(agent_metrics.current_tier, 1.0)

            # Lock period multiplier
            lock_multipliers = {30: 1.1, 90: 1.25, 180: 1.5, 365: 2.0}  # 30 days  # 90 days  # 180 days  # 365 days

            lock_multiplier = lock_multipliers.get(lock_period, 1.0)

            # Calculate final APY
            apy = base_apy * tier_multiplier * lock_multiplier

            # Cap at maximum
            return min(apy, 20.0)  # Max 20% APY

        except Exception as e:
            logger.error(f"Failed to calculate APY: {e}")
            return 5.0  # Return base APY on error

    async def update_agent_performance(
        self,
        agent_wallet: str,
        accuracy: float,
        successful: bool,
        response_time: float | None = None,
        compute_power: float | None = None,
        energy_efficiency: float | None = None,
    ) -> AgentMetrics:
        """Update agent performance metrics"""
        try:
            # Get or create agent metrics
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                agent_metrics = AgentMetrics(agent_wallet=agent_wallet, current_tier=PerformanceTier.BRONZE, tier_score=60.0)
                self.session.add(agent_metrics)

            # Update performance metrics
            agent_metrics.total_submissions += 1
            if successful:
                agent_metrics.successful_submissions += 1

            # Update average accuracy
            total_accuracy = agent_metrics.average_accuracy * (agent_metrics.total_submissions - 1) + accuracy
            agent_metrics.average_accuracy = total_accuracy / agent_metrics.total_submissions

            # Update success rate
            agent_metrics.success_rate = (agent_metrics.successful_submissions / agent_metrics.total_submissions) * 100

            # Update other metrics
            if response_time:
                if agent_metrics.average_response_time is None:
                    agent_metrics.average_response_time = response_time
                else:
                    agent_metrics.average_response_time = (agent_metrics.average_response_time + response_time) / 2

            if energy_efficiency:
                agent_metrics.energy_efficiency_score = energy_efficiency

            # Calculate new tier
            new_tier = await self._calculate_agent_tier(agent_metrics)
            old_tier = agent_metrics.current_tier

            if new_tier != old_tier:
                agent_metrics.current_tier = new_tier
                agent_metrics.tier_score = await self._get_tier_score(new_tier)

                # Update APY for all active stakes on this agent
                await self._update_stake_apy_for_agent(agent_wallet, new_tier)

            agent_metrics.last_update_time = datetime.now(timezone.utc)

            self.session.commit()
            self.session.refresh(agent_metrics)

            logger.info(f"Updated performance for agent {agent_wallet}")
            return agent_metrics

        except Exception as e:
            logger.error(f"Failed to update agent performance: {e}")
            self.session.rollback()
            raise

    async def distribute_earnings(
        self, agent_wallet: str, total_earnings: float, distribution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Distribute agent earnings to stakers"""
        try:
            # Get staking pool
            pool = await self.get_staking_pool(agent_wallet)
            if not pool or pool.total_staked == 0:
                raise ValueError("No stakers in pool")

            # Calculate platform fee (1%)
            platform_fee = total_earnings * 0.01
            distributable_amount = total_earnings - platform_fee

            # Distribute to stakers proportionally
            total_distributed = 0.0
            staker_count = 0

            # Get active stakes for this agent
            stmt = select(AgentStake).where(
                and_(AgentStake.agent_wallet == agent_wallet, AgentStake.status == StakeStatus.ACTIVE)
            )
            stakes = self.session.execute(stmt).scalars().all()

            for stake in stakes:
                # Calculate staker's share
                staker_share = (distributable_amount * stake.amount) / pool.total_staked

                if staker_share > 0:
                    stake.accumulated_rewards += staker_share
                    total_distributed += staker_share
                    staker_count += 1

            # Update pool metrics
            pool.total_rewards += total_distributed
            pool.last_distribution_time = datetime.now(timezone.utc)

            # Update agent metrics
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if agent_metrics:
                agent_metrics.total_rewards_distributed += total_distributed

            self.session.commit()

            result = {"total_distributed": total_distributed, "staker_count": staker_count, "platform_fee": platform_fee}

            logger.info(f"Distributed {total_distributed} earnings to {staker_count} stakers")
            return result

        except Exception as e:
            logger.error(f"Failed to distribute earnings: {e}")
            self.session.rollback()
            raise

    async def get_supported_agents(
        self, page: int = 1, limit: int = 50, tier: PerformanceTier | None = None
    ) -> list[dict[str, Any]]:
        """Get list of supported agents for staking"""
        try:
            query = select(AgentMetrics)

            if tier:
                query = query.where(AgentMetrics.current_tier == tier)

            query = query.order_by(AgentMetrics.total_staked.desc())

            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)

            result = self.session.execute(query).scalars().all()

            agents = []
            for metrics in result:
                agents.append(
                    {
                        "agent_wallet": metrics.agent_wallet,
                        "total_staked": metrics.total_staked,
                        "staker_count": metrics.staker_count,
                        "current_tier": metrics.current_tier,
                        "average_accuracy": metrics.average_accuracy,
                        "success_rate": metrics.success_rate,
                        "current_apy": await self.calculate_apy(metrics.agent_wallet, 30),
                    }
                )

            return agents

        except Exception as e:
            logger.error(f"Failed to get supported agents: {e}")
            raise

    async def get_staking_stats(self, period: str = "daily") -> dict[str, Any]:
        """Get staking system statistics"""
        try:
            # Calculate time period
            if period == "hourly":
                start_date = datetime.now(timezone.utc) - timedelta(hours=1)
            elif period == "daily":
                start_date = datetime.now(timezone.utc) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(timezone.utc) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(timezone.utc) - timedelta(days=30)
            else:
                start_date = datetime.now(timezone.utc) - timedelta(days=1)

            # Get total staked
            total_staked_stmt = select(func.sum(AgentStake.amount)).where(AgentStake.start_time >= start_date)
            total_staked = self.session.execute(total_staked_stmt).scalar() or 0.0

            # Get active stakes
            active_stakes_stmt = select(func.count(AgentStake.stake_id)).where(
                and_(AgentStake.start_time >= start_date, AgentStake.status == StakeStatus.ACTIVE)
            )
            active_stakes = self.session.execute(active_stakes_stmt).scalar() or 0

            # Get unique stakers
            unique_stakers_stmt = select(func.count(func.distinct(AgentStake.staker_address))).where(
                AgentStake.start_time >= start_date
            )
            unique_stakers = self.session.execute(unique_stakers_stmt).scalar() or 0

            # Get average APY
            avg_apy_stmt = select(func.avg(AgentStake.current_apy)).where(AgentStake.start_time >= start_date)
            avg_apy = self.session.execute(avg_apy_stmt).scalar() or 0.0

            # Get total rewards
            total_rewards_stmt = select(func.sum(AgentMetrics.total_rewards_distributed)).where(
                AgentMetrics.last_update_time >= start_date
            )
            total_rewards = self.session.execute(total_rewards_stmt).scalar() or 0.0

            # Get tier distribution
            tier_stmt = (
                select(AgentStake.agent_tier, func.count(AgentStake.stake_id).label("count"))
                .where(AgentStake.start_time >= start_date)
                .group_by(AgentStake.agent_tier)
            )

            tier_result = self.session.execute(tier_stmt).all()
            tier_distribution = {row.agent_tier.value: row.count for row in tier_result}

            return {
                "total_staked": total_staked,
                "total_stakers": unique_stakers,
                "active_stakes": active_stakes,
                "average_apy": avg_apy,
                "total_rewards_distributed": total_rewards,
                "tier_distribution": tier_distribution,
            }

        except Exception as e:
            logger.error(f"Failed to get staking stats: {e}")
            raise

    async def get_leaderboard(
        self, period: str = "weekly", metric: str = "total_staked", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get staking leaderboard"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.now(timezone.utc) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(timezone.utc) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(timezone.utc) - timedelta(days=30)
            else:
                start_date = datetime.now(timezone.utc) - timedelta(weeks=1)

            if metric == "total_staked":
                stmt = (
                    select(
                        AgentStake.agent_wallet,
                        func.sum(AgentStake.amount).label("total_staked"),
                        func.count(AgentStake.stake_id).label("stake_count"),
                    )
                    .where(AgentStake.start_time >= start_date)
                    .group_by(AgentStake.agent_wallet)
                    .order_by(func.sum(AgentStake.amount).desc())
                    .limit(limit)
                )

            elif metric == "total_rewards":
                stmt = (
                    select(AgentMetrics.agent_wallet, AgentMetrics.total_rewards_distributed, AgentMetrics.staker_count)
                    .where(AgentMetrics.last_update_time >= start_date)
                    .order_by(AgentMetrics.total_rewards_distributed.desc())
                    .limit(limit)
                )

            elif metric == "apy":
                stmt = (
                    select(
                        AgentStake.agent_wallet,
                        func.avg(AgentStake.current_apy).label("avg_apy"),
                        func.count(AgentStake.stake_id).label("stake_count"),
                    )
                    .where(AgentStake.start_time >= start_date)
                    .group_by(AgentStake.agent_wallet)
                    .order_by(func.avg(AgentStake.current_apy).desc())
                    .limit(limit)
                )

            result = self.session.execute(stmt).all()

            leaderboard = []
            for row in result:
                leaderboard.append({"agent_wallet": row.agent_wallet, "rank": len(leaderboard) + 1, **row._asdict()})

            return leaderboard

        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            raise

    async def get_user_rewards(self, user_address: str, period: str = "monthly") -> dict[str, Any]:
        """Get user's staking rewards"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.now(timezone.utc) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(timezone.utc) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(timezone.utc) - timedelta(days=30)
            else:
                start_date = datetime.now(timezone.utc) - timedelta(days=30)

            # Get user's stakes
            stmt = select(AgentStake).where(
                and_(AgentStake.staker_address == user_address, AgentStake.start_time >= start_date)
            )
            stakes = self.session.execute(stmt).scalars().all()

            total_rewards = 0.0
            total_staked = 0.0
            active_stakes = 0

            for stake in stakes:
                total_rewards += stake.accumulated_rewards
                total_staked += stake.amount
                if stake.status == StakeStatus.ACTIVE:
                    active_stakes += 1

            return {
                "user_address": user_address,
                "period": period,
                "total_rewards": total_rewards,
                "total_staked": total_staked,
                "active_stakes": active_stakes,
                "average_apy": (total_rewards / total_staked * 100) if total_staked > 0 else 0.0,
            }

        except Exception as e:
            logger.error(f"Failed to get user rewards: {e}")
            raise

    async def claim_rewards(self, stake_ids: list[str]) -> dict[str, Any]:
        """Claim accumulated rewards for multiple stakes"""
        try:
            total_rewards = 0.0

            for stake_id in stake_ids:
                stake = await self.get_stake(stake_id)
                if not stake:
                    continue

                total_rewards += stake.accumulated_rewards
                stake.accumulated_rewards = 0.0
                stake.last_reward_time = datetime.now(timezone.utc)

            self.session.commit()

            return {"total_rewards": total_rewards, "claimed_stakes": len(stake_ids)}

        except Exception as e:
            logger.error(f"Failed to claim rewards: {e}")
            self.session.rollback()
            raise

    async def get_risk_assessment(self, agent_wallet: str) -> dict[str, Any]:
        """Get risk assessment for staking on an agent"""
        try:
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                raise ValueError("Agent not found")

            # Calculate risk factors
            risk_factors = {
                "performance_risk": max(0, 100 - agent_metrics.average_accuracy) / 100,
                "volatility_risk": 0.1 if agent_metrics.success_rate < 80 else 0.05,
                "concentration_risk": min(1.0, agent_metrics.total_staked / 100000),  # High concentration if >100k
                "new_agent_risk": 0.2 if agent_metrics.total_submissions < 10 else 0.0,
            }

            # Calculate overall risk score
            risk_score = sum(risk_factors.values()) / len(risk_factors)

            # Determine risk level
            if risk_score < 0.2:
                risk_level = "low"
            elif risk_score < 0.5:
                risk_level = "medium"
            else:
                risk_level = "high"

            return {
                "agent_wallet": agent_wallet,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "recommendations": self._get_risk_recommendations(risk_level, risk_factors),
            }

        except Exception as e:
            logger.error(f"Failed to get risk assessment: {e}")
            raise

    # Private helper methods

    async def _update_staking_pool(self, agent_wallet: str, staker_address: str, amount: float, is_stake: bool):
        """Update staking pool"""
        try:
            pool = await self.get_staking_pool(agent_wallet)
            if not pool:
                pool = StakingPool(agent_wallet=agent_wallet)
                self.session.add(pool)
                self.session.commit()
                self.session.refresh(pool)
            else:
                self.session.refresh(pool)

            if is_stake:
                if staker_address not in pool.active_stakers:
                    pool.active_stakers.append(staker_address)
                pool.total_staked += amount
            else:
                pool.total_staked -= amount
                if staker_address in pool.active_stakers:
                    pool.active_stakers.remove(staker_address)

            # Update pool APY
            if pool.total_staked > 0:
                pool.pool_apy = await self.calculate_apy(agent_wallet, 30)

            self.session.commit()
            self.session.refresh(pool)

        except Exception as e:
            logger.error(f"Failed to update staking pool: {e}")
            raise

    async def _calculate_rewards(self, stake_id: str):
        """Calculate and update rewards for a stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake or stake.status != StakeStatus.ACTIVE:
                return

            time_elapsed = datetime.now(timezone.utc) - stake.last_reward_time
            yearly_rewards = (stake.amount * stake.current_apy) / 100
            current_rewards = (yearly_rewards * time_elapsed.total_seconds()) / (365 * 24 * 3600)

            stake.accumulated_rewards += current_rewards
            stake.last_reward_time = datetime.now(timezone.utc)

            # Auto-compound if enabled
            if stake.auto_compound and current_rewards >= 100.0:
                stake.amount += current_rewards
                stake.accumulated_rewards = 0.0

        except Exception as e:
            logger.error(f"Failed to calculate rewards: {e}")
            raise

    async def _calculate_agent_tier(self, agent_metrics: AgentMetrics) -> PerformanceTier:
        """Calculate agent performance tier"""
        success_rate = agent_metrics.success_rate
        accuracy = agent_metrics.average_accuracy

        score = (accuracy * 0.6) + (success_rate * 0.4)

        if score >= 95:
            return PerformanceTier.DIAMOND
        elif score >= 90:
            return PerformanceTier.PLATINUM
        elif score >= 80:
            return PerformanceTier.GOLD
        elif score >= 70:
            return PerformanceTier.SILVER
        else:
            return PerformanceTier.BRONZE

    async def _get_tier_score(self, tier: PerformanceTier) -> float:
        """Get score for a tier"""
        tier_scores = {
            PerformanceTier.DIAMOND: 95.0,
            PerformanceTier.PLATINUM: 90.0,
            PerformanceTier.GOLD: 80.0,
            PerformanceTier.SILVER: 70.0,
            PerformanceTier.BRONZE: 60.0,
        }
        return tier_scores.get(tier, 60.0)

    async def _update_stake_apy_for_agent(self, agent_wallet: str, new_tier: PerformanceTier):
        """Update APY for all active stakes on an agent"""
        try:
            stmt = select(AgentStake).where(
                and_(AgentStake.agent_wallet == agent_wallet, AgentStake.status == StakeStatus.ACTIVE)
            )
            stakes = self.session.execute(stmt).scalars().all()

            for stake in stakes:
                stake.current_apy = await self.calculate_apy(agent_wallet, stake.lock_period)
                stake.agent_tier = new_tier

        except Exception as e:
            logger.error(f"Failed to update stake APY: {e}")
            raise

    def _get_risk_recommendations(self, risk_level: str, risk_factors: dict[str, float]) -> list[str]:
        """Get risk recommendations based on risk level and factors"""
        recommendations = []

        if risk_level == "high":
            recommendations.append("Consider staking a smaller amount")
            recommendations.append("Monitor agent performance closely")

        if risk_factors.get("performance_risk", 0) > 0.3:
            recommendations.append("Agent has low accuracy - consider waiting for improvement")

        if risk_factors.get("concentration_risk", 0) > 0.5:
            recommendations.append("High concentration - diversify across multiple agents")

        if risk_factors.get("new_agent_risk", 0) > 0.1:
            recommendations.append("New agent - consider waiting for more performance data")

        if not recommendations:
            recommendations.append("Agent appears to be low risk for staking")

        return recommendations
