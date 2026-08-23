"""
Staking Management Service
Business logic for AI agent staking system with reputation-based yield farming
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.utils.units import ait_to_seconds

from ..domain.staking import AgentMetrics, AgentStake, PerformanceTier, StakeStatus, StakingPool

logger = get_logger(__name__)


class StakingService:
    """Service for managing AI agent staking"""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _as_decimal(value: Decimal | float | int | str) -> Decimal:
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @staticmethod
    def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _normalize_stake_datetimes(self, stake: AgentStake) -> AgentStake:
        stake.start_time = self._ensure_utc_datetime(stake.start_time)  # type: ignore[assignment]
        stake.end_time = self._ensure_utc_datetime(stake.end_time)  # type: ignore[assignment]
        stake.last_reward_time = self._ensure_utc_datetime(stake.last_reward_time)  # type: ignore[assignment]
        stake.unbonding_time = self._ensure_utc_datetime(stake.unbonding_time)
        return stake

    def _normalize_agent_metrics_datetimes(self, agent_metrics: AgentMetrics) -> AgentMetrics:
        agent_metrics.last_update_time = self._ensure_utc_datetime(agent_metrics.last_update_time)  # type: ignore[assignment]
        agent_metrics.first_submission_time = self._ensure_utc_datetime(agent_metrics.first_submission_time)
        return agent_metrics

    def _normalize_staking_pool_datetimes(self, staking_pool: StakingPool) -> StakingPool:
        staking_pool.last_distribution_time = self._ensure_utc_datetime(staking_pool.last_distribution_time)  # type: ignore[assignment]
        return staking_pool

    async def create_stake(
        self,
        staker_address: str,
        agent_wallet: str,
        amount: Decimal,
        lock_period: int,
        auto_compound: bool,
        stake_id: str | None = None,
    ) -> AgentStake:
        """Create a new stake on an agent wallet"""
        try:
            amount = self._as_decimal(amount)
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                raise ValueError("Agent not supported for staking")
            min_seconds = 360000  # 100 AIT in compute-seconds
            if ait_to_seconds(amount) < min_seconds:
                raise ValueError("Stake amount must be at least 100 AITBC")
            current_apy = await self.calculate_apy(agent_wallet, lock_period)
            end_time = datetime.now(UTC) + timedelta(days=lock_period)
            stake = AgentStake(
                stake_id=stake_id or None,
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
            agent_metrics.total_staked += amount
            existing_stakes = await self.get_user_stakes(staker_address, agent_wallet=agent_wallet)
            if not existing_stakes:
                agent_metrics.staker_count += 1
            await self._update_staking_pool(agent_wallet, staker_address, amount, True)
            self.session.commit()
            self.session.refresh(stake)
            logger.info("Created stake %s: %s on %s", stake.stake_id, amount, agent_wallet)
            return self._normalize_stake_datetimes(stake)
        except Exception as e:
            logger.error("Failed to create stake: %s", e)
            self.session.rollback()
            raise

    async def get_stake(self, stake_id: str) -> AgentStake | None:
        """Get stake by ID"""
        try:
            stmt = select(AgentStake).where(AgentStake.stake_id == stake_id)  # type: ignore[arg-type]
            result = self.session.execute(stmt).scalar_one_or_none()
            if not result:
                return None
            return self._normalize_stake_datetimes(result)
        except Exception as e:
            logger.error("Failed to get stake %s: %s", stake_id, e)
            raise

    async def get_user_stakes(
        self,
        user_address: str,
        status: StakeStatus | None = None,
        agent_wallet: str | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        agent_tier: PerformanceTier | None = None,
        auto_compound: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[AgentStake]:
        """Get filtered list of user's stakes"""
        try:
            query = select(AgentStake).where(AgentStake.staker_address == user_address)  # type: ignore[arg-type]
            if status:
                query = query.where(AgentStake.status == status)  # type: ignore[arg-type]
            if agent_wallet:
                query = query.where(AgentStake.agent_wallet == agent_wallet)  # type: ignore[arg-type]
            if min_amount:
                query = query.where(AgentStake.amount >= min_amount)  # type: ignore[arg-type]
            if max_amount:
                query = query.where(AgentStake.amount <= max_amount)  # type: ignore[arg-type]
            if agent_tier:
                query = query.where(AgentStake.agent_tier == agent_tier)  # type: ignore[arg-type]
            if auto_compound is not None:
                query = query.where(AgentStake.auto_compound == auto_compound)  # type: ignore[arg-type]
            query = query.order_by(AgentStake.start_time.desc())  # type: ignore[attr-defined]
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)
            result = self.session.execute(query).scalars().all()
            return [self._normalize_stake_datetimes(stake) for stake in result]
        except Exception as e:
            logger.error("Failed to get user stakes: %s", e)
            raise

    async def add_to_stake(self, stake_id: str, additional_amount: Decimal) -> AgentStake:
        """Add more tokens to an existing stake"""
        try:
            additional_amount = self._as_decimal(additional_amount)
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")
            if stake.status != StakeStatus.ACTIVE:
                raise ValueError("Stake is not active")
            stake.amount += additional_amount
            stake.current_apy = await self.calculate_apy(stake.agent_wallet, stake.lock_period)
            agent_metrics = await self.get_agent_metrics(stake.agent_wallet)
            if agent_metrics:
                agent_metrics.total_staked += additional_amount
            await self._update_staking_pool(stake.agent_wallet, stake.staker_address, additional_amount, True)
            self.session.commit()
            self.session.refresh(stake)
            logger.info("Added %s to stake %s", additional_amount, stake_id)
            return stake
        except Exception as e:
            logger.error("Failed to add to stake: %s", e)
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
            if datetime.now(UTC) < stake.end_time:
                raise ValueError("Lock period has not ended")
            await self._calculate_rewards(stake_id)
            stake.status = StakeStatus.UNBONDING
            stake.unbonding_time = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(stake)
            logger.info("Initiated unbonding for stake %s", stake_id)
            return stake
        except Exception as e:
            logger.error("Failed to unbond stake: %s", e)
            self.session.rollback()
            raise

    async def complete_unbonding(self, stake_id: str) -> dict[str, Decimal]:
        """Complete unbonding and return stake + rewards"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")
            if stake.status != StakeStatus.UNBONDING:
                raise ValueError("Stake is not unbonding")
            penalty = Decimal("0.0")
            total_amount = stake.amount
            if stake.unbonding_time and datetime.now(UTC) < stake.unbonding_time + timedelta(days=30):
                penalty = total_amount * Decimal("0.1")
                total_amount -= penalty
            stake.status = StakeStatus.COMPLETED
            agent_metrics = await self.get_agent_metrics(stake.agent_wallet)
            if agent_metrics:
                agent_metrics.total_staked -= stake.amount
                remaining_stakes = await self.get_user_stakes(
                    stake.staker_address, agent_wallet=stake.agent_wallet, status=StakeStatus.ACTIVE
                )
                if not remaining_stakes:
                    agent_metrics.staker_count -= 1
            await self._update_staking_pool(stake.agent_wallet, stake.staker_address, stake.amount, False)
            self.session.commit()
            result = {"total_amount": total_amount, "total_rewards": stake.accumulated_rewards, "penalty": penalty}
            logger.info("Completed unbonding for stake %s", stake_id)
            return result
        except Exception as e:
            logger.error("Failed to complete unbonding: %s", e)
            self.session.rollback()
            raise

    async def calculate_rewards(self, stake_id: str) -> Decimal:
        """Calculate current rewards for a stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake:
                raise ValueError("Stake not found")
            if stake.status != StakeStatus.ACTIVE:
                return stake.accumulated_rewards
            time_elapsed = datetime.now(UTC) - stake.last_reward_time
            yearly_rewards = stake.amount * stake.current_apy / 100
            current_rewards = yearly_rewards * Decimal(str(time_elapsed.total_seconds())) / (365 * 24 * 3600)
            return stake.accumulated_rewards + current_rewards
        except Exception as e:
            logger.error("Failed to calculate rewards: %s", e)
            raise

    async def get_agent_metrics(self, agent_wallet: str) -> AgentMetrics | None:
        """Get agent performance metrics"""
        try:
            stmt = select(AgentMetrics).where(AgentMetrics.agent_wallet == agent_wallet)  # type: ignore[arg-type]
            result = self.session.execute(stmt).scalar_one_or_none()
            return self._normalize_agent_metrics_datetimes(result) if result else None
        except Exception as e:
            logger.error("Failed to get agent metrics: %s", e)
            raise

    async def get_staking_pool(self, agent_wallet: str) -> StakingPool | None:
        """Get staking pool for an agent"""
        try:
            stmt = select(StakingPool).where(StakingPool.agent_wallet == agent_wallet)  # type: ignore[arg-type]
            result = self.session.execute(stmt).scalar_one_or_none()
            return self._normalize_staking_pool_datetimes(result) if result else None
        except Exception as e:
            logger.error("Failed to get staking pool: %s", e)
            raise

    async def calculate_apy(self, agent_wallet: str, lock_period: int) -> Decimal:
        """Calculate APY for staking on an agent"""
        try:
            base_apy = Decimal("5.0")
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                return base_apy
            tier_multipliers = {
                PerformanceTier.BRONZE: Decimal("1.0"),
                PerformanceTier.SILVER: Decimal("1.2"),
                PerformanceTier.GOLD: Decimal("1.5"),
                PerformanceTier.PLATINUM: Decimal("2.0"),
                PerformanceTier.DIAMOND: Decimal("3.0"),
            }
            tier_multiplier = tier_multipliers.get(agent_metrics.current_tier, Decimal("1.0"))
            lock_multipliers = {30: Decimal("1.1"), 90: Decimal("1.25"), 180: Decimal("1.5"), 365: Decimal("2.0")}
            lock_multiplier = lock_multipliers.get(lock_period, Decimal("1.0"))
            apy = base_apy * tier_multiplier * lock_multiplier
            return min(apy, Decimal("20.0"))
        except Exception as e:
            logger.error("Failed to calculate APY: %s", e)
            return Decimal("5.0")

    async def update_agent_performance(
        self,
        agent_wallet: str,
        accuracy: Decimal,
        successful: bool,
        response_time: Decimal | None = None,
        compute_power: Decimal | None = None,
        energy_efficiency: Decimal | None = None,
    ) -> AgentMetrics:
        """Update agent performance metrics"""
        try:
            accuracy = self._as_decimal(accuracy)
            response_time = self._as_decimal(response_time) if response_time is not None else None
            energy_efficiency = self._as_decimal(energy_efficiency) if energy_efficiency is not None else None
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                agent_metrics = AgentMetrics(
                    agent_wallet=agent_wallet, current_tier=PerformanceTier.BRONZE, tier_score=Decimal("60.0")
                )
                self.session.add(agent_metrics)
            agent_metrics.total_submissions += 1
            if successful:
                agent_metrics.successful_submissions += 1
            total_accuracy = agent_metrics.average_accuracy * (agent_metrics.total_submissions - 1) + accuracy
            agent_metrics.average_accuracy = total_accuracy / agent_metrics.total_submissions
            agent_metrics.success_rate = Decimal(agent_metrics.successful_submissions) / agent_metrics.total_submissions * 100
            if response_time:
                if agent_metrics.average_response_time is None:
                    agent_metrics.average_response_time = response_time
                else:
                    agent_metrics.average_response_time = (agent_metrics.average_response_time + response_time) / 2
            if energy_efficiency:
                agent_metrics.energy_efficiency_score = energy_efficiency
            new_tier = await self._calculate_agent_tier(agent_metrics)
            old_tier = agent_metrics.current_tier
            if new_tier != old_tier:
                agent_metrics.current_tier = new_tier
                agent_metrics.tier_score = await self._get_tier_score(new_tier)
                await self._update_stake_apy_for_agent(agent_wallet, new_tier)
            agent_metrics.last_update_time = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(agent_metrics)
            logger.info("Updated performance for agent %s", agent_wallet)
            return agent_metrics
        except Exception as e:
            logger.error("Failed to update agent performance: %s", e)
            self.session.rollback()
            raise

    async def distribute_earnings(
        self, agent_wallet: str, total_earnings: Decimal, distribution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Distribute agent earnings to stakers"""
        try:
            total_earnings = self._as_decimal(total_earnings)
            pool = await self.get_staking_pool(agent_wallet)
            if not pool or pool.total_staked == 0:
                raise ValueError("No stakers in pool")
            platform_fee = total_earnings * Decimal("0.01")
            distributable_amount = total_earnings - platform_fee
            total_distributed = Decimal("0.0")
            staker_count = 0
            stmt = select(AgentStake).where(
                and_(AgentStake.agent_wallet == agent_wallet, AgentStake.status == StakeStatus.ACTIVE)  # type: ignore[arg-type]
            )
            stakes = self.session.execute(stmt).scalars().all()
            for stake in stakes:
                staker_share = distributable_amount * stake.amount / pool.total_staked
                if staker_share > 0:
                    stake.accumulated_rewards += staker_share
                    total_distributed += staker_share
                    staker_count += 1
            pool.total_rewards += total_distributed
            pool.last_distribution_time = datetime.now(UTC)
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if agent_metrics:
                agent_metrics.total_rewards_distributed += total_distributed
            self.session.commit()
            result = {"total_distributed": total_distributed, "staker_count": staker_count, "platform_fee": platform_fee}
            logger.info("Distributed %s earnings to %s stakers", total_distributed, staker_count)
            return result
        except Exception as e:
            logger.error("Failed to distribute earnings: %s", e)
            self.session.rollback()
            raise

    async def get_supported_agents(
        self, page: int = 1, limit: int = 50, tier: PerformanceTier | None = None
    ) -> list[dict[str, Any]]:
        """Get list of supported agents for staking"""
        try:
            query = select(AgentMetrics)
            if tier:
                query = query.where(AgentMetrics.current_tier == tier)  # type: ignore[arg-type]
            query = query.order_by(AgentMetrics.total_staked.desc())  # type: ignore[attr-defined]
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
            logger.error("Failed to get supported agents: %s", e)
            raise

    async def get_staking_stats(self, period: str = "daily") -> dict[str, Any]:
        """Get staking system statistics"""
        try:
            if period == "hourly":
                start_date = datetime.now(UTC) - timedelta(hours=1)
            elif period == "daily":
                start_date = datetime.now(UTC) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(UTC) - timedelta(days=30)
            else:
                start_date = datetime.now(UTC) - timedelta(days=1)
            total_staked_stmt = select(func.sum(AgentStake.amount)).where(AgentStake.start_time >= start_date)  # type: ignore[arg-type]
            total_staked = self.session.execute(total_staked_stmt).scalar() or 0.0
            active_stakes_stmt = select(func.count(AgentStake.stake_id)).where(  # type: ignore[arg-type]
                and_(AgentStake.start_time >= start_date, AgentStake.status == StakeStatus.ACTIVE)  # type: ignore[arg-type]
            )
            active_stakes = self.session.execute(active_stakes_stmt).scalar() or 0
            unique_stakers_stmt = select(func.count(func.distinct(AgentStake.staker_address))).where(
                AgentStake.start_time >= start_date  # type: ignore[arg-type]
            )
            unique_stakers = self.session.execute(unique_stakers_stmt).scalar() or 0
            avg_apy_stmt = select(func.avg(AgentStake.current_apy)).where(AgentStake.start_time >= start_date)  # type: ignore[arg-type]
            avg_apy = self.session.execute(avg_apy_stmt).scalar() or 0.0
            total_rewards_stmt = select(func.sum(AgentMetrics.total_rewards_distributed)).where(
                AgentMetrics.last_update_time >= start_date  # type: ignore[arg-type]
            )
            total_rewards = self.session.execute(total_rewards_stmt).scalar() or 0.0
            tier_stmt = (
                select(AgentStake.agent_tier, func.count(AgentStake.stake_id).label("count"))  # type: ignore[arg-type, call-overload]
                .where(AgentStake.start_time >= start_date)
                .group_by(AgentStake.agent_tier)
            )
            tier_result = self.session.execute(
                tier_stmt
            ).all()  # ponytail: multi-column select, .all() returns Row objects with both columns
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
            logger.error("Failed to get staking stats: %s", e)
            raise

    async def get_leaderboard(
        self, period: str = "weekly", metric: str = "total_staked", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get staking leaderboard"""
        try:
            if period == "daily":
                start_date = datetime.now(UTC) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(UTC) - timedelta(days=30)
            else:
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            if metric == "total_staked":
                stmt = (
                    select(  # type: ignore[call-overload]
                        AgentStake.agent_wallet,
                        func.sum(AgentStake.amount).label("total_staked"),
                        func.count(AgentStake.stake_id).label("stake_count"),  # type: ignore[arg-type]
                    )
                    .where(AgentStake.start_time >= start_date)
                    .group_by(AgentStake.agent_wallet)
                    .order_by(func.sum(AgentStake.amount).desc())
                    .limit(limit)
                )
            elif metric == "total_rewards":
                stmt = (
                    select(AgentMetrics.agent_wallet, AgentMetrics.total_rewards_distributed, AgentMetrics.staker_count)  # type: ignore[call-overload]
                    .where(AgentMetrics.last_update_time >= start_date)
                    .order_by(AgentMetrics.total_rewards_distributed.desc())  # type: ignore[attr-defined]
                    .limit(limit)
                )
            elif metric == "apy":
                stmt = (
                    select(  # type: ignore[call-overload]
                        AgentStake.agent_wallet,
                        func.avg(AgentStake.current_apy).label("avg_apy"),
                        func.count(AgentStake.stake_id).label("stake_count"),  # type: ignore[arg-type]
                    )
                    .where(AgentStake.start_time >= start_date)
                    .group_by(AgentStake.agent_wallet)
                    .order_by(func.avg(AgentStake.current_apy).desc())
                    .limit(limit)
                )
            result = self.session.execute(stmt).all()  # ponytail: multi-column select, .all() returns Row objects
            leaderboard: list[dict[str, Any]] = []
            for row in result:
                leaderboard.append({"agent_wallet": row.agent_wallet, "rank": len(leaderboard) + 1, **row._asdict()})
            return leaderboard
        except Exception as e:
            logger.error("Failed to get leaderboard: %s", e)
            raise

    async def get_user_rewards(self, user_address: str, period: str = "monthly") -> dict[str, Any]:
        """Get user's staking rewards"""
        try:
            if period == "daily":
                start_date = datetime.now(UTC) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(UTC) - timedelta(days=30)
            else:
                start_date = datetime.now(UTC) - timedelta(days=30)
            stmt = select(AgentStake).where(
                and_(AgentStake.staker_address == user_address, AgentStake.start_time >= start_date)  # type: ignore[arg-type]
            )
            stakes = self.session.execute(stmt).scalars().all()
            total_rewards = Decimal("0.0")
            total_staked = Decimal("0.0")
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
                "average_apy": total_rewards / total_staked * 100 if total_staked > 0 else 0.0,
            }
        except Exception as e:
            logger.error("Failed to get user rewards: %s", e)
            raise

    async def claim_rewards(self, stake_ids: list[str]) -> dict[str, Any]:
        """Claim accumulated rewards for multiple stakes"""
        try:
            total_rewards = Decimal("0.0")
            for stake_id in stake_ids:
                stake = await self.get_stake(stake_id)
                if not stake:
                    continue
                total_rewards += stake.accumulated_rewards
                stake.accumulated_rewards = Decimal("0.0")
                stake.last_reward_time = datetime.now(UTC)
            self.session.commit()
            return {"total_rewards": total_rewards, "claimed_stakes": len(stake_ids)}
        except Exception as e:
            logger.error("Failed to claim rewards: %s", e)
            self.session.rollback()
            raise

    async def get_risk_assessment(self, agent_wallet: str) -> dict[str, Any]:
        """Get risk assessment for staking on an agent"""
        try:
            agent_metrics = await self.get_agent_metrics(agent_wallet)
            if not agent_metrics:
                raise ValueError("Agent not found")
            risk_factors = {
                "performance_risk": max(0.0, 100 - float(agent_metrics.average_accuracy)) / 100,
                "volatility_risk": 0.1 if agent_metrics.success_rate < 80 else 0.05,
                "concentration_risk": min(1.0, float(agent_metrics.total_staked) / 100000),
                "new_agent_risk": 0.2 if agent_metrics.total_submissions < 10 else 0.0,
            }
            risk_score = sum(risk_factors.values()) / len(risk_factors)
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
            logger.error("Failed to get risk assessment: %s", e)
            raise

    async def _update_staking_pool(self, agent_wallet: str, staker_address: str, amount: Decimal, is_stake: bool) -> None:
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
            if pool.total_staked > 0:
                pool.pool_apy = await self.calculate_apy(agent_wallet, 30)
            self.session.commit()
            self.session.refresh(pool)
        except Exception as e:
            logger.error("Failed to update staking pool: %s", e)
            raise

    async def _calculate_rewards(self, stake_id: str) -> None:
        """Calculate and update rewards for a stake"""
        try:
            stake = await self.get_stake(stake_id)
            if not stake or stake.status != StakeStatus.ACTIVE:
                return
            time_elapsed = datetime.now(UTC) - stake.last_reward_time
            yearly_rewards = stake.amount * stake.current_apy / 100
            current_rewards = yearly_rewards * Decimal(str(time_elapsed.total_seconds())) / (365 * 24 * 3600)
            stake.accumulated_rewards += current_rewards
            stake.last_reward_time = datetime.now(UTC)
            if stake.auto_compound and current_rewards >= 100:
                stake.amount += current_rewards
                stake.accumulated_rewards = Decimal("0.0")
        except Exception as e:
            logger.error("Failed to calculate rewards: %s", e)
            raise

    async def _calculate_agent_tier(self, agent_metrics: AgentMetrics) -> PerformanceTier:
        """Calculate agent performance tier"""
        success_rate = agent_metrics.success_rate
        accuracy = agent_metrics.average_accuracy
        score = accuracy * Decimal("0.6") + success_rate * Decimal("0.4")
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

    async def _get_tier_score(self, tier: PerformanceTier) -> Decimal:
        """Get score for a tier"""
        tier_scores = {
            PerformanceTier.DIAMOND: Decimal("95.0"),
            PerformanceTier.PLATINUM: Decimal("90.0"),
            PerformanceTier.GOLD: Decimal("80.0"),
            PerformanceTier.SILVER: Decimal("70.0"),
            PerformanceTier.BRONZE: Decimal("60.0"),
        }
        return tier_scores.get(tier, Decimal("60.0"))

    async def _update_stake_apy_for_agent(self, agent_wallet: str, new_tier: PerformanceTier) -> None:
        """Update APY for all active stakes on an agent"""
        try:
            stmt = select(AgentStake).where(
                and_(AgentStake.agent_wallet == agent_wallet, AgentStake.status == StakeStatus.ACTIVE)  # type: ignore[arg-type]
            )
            stakes = self.session.execute(stmt).scalars().all()
            for stake in stakes:
                stake.current_apy = await self.calculate_apy(agent_wallet, stake.lock_period)
                stake.agent_tier = new_tier
        except Exception as e:
            logger.error("Failed to update stake APY: %s", e)
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
