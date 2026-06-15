"""
Bid Strategy Engine for hermes Autonomous Economics
Implements intelligent bidding algorithms for GPU rental negotiations
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


class BidStrategy(StrEnum):
    """Bidding strategy types"""

    URGENT_BID = "urgent_bid"
    COST_OPTIMIZED = "cost_optimized"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"


class UrgencyLevel(StrEnum):
    """Task urgency levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GPU_Tier(StrEnum):
    """GPU resource tiers"""

    CPU_ONLY = "cpu_only"
    LOW_END_GPU = "low_end_gpu"
    MID_RANGE_GPU = "mid_range_gpu"
    HIGH_END_GPU = "high_end_gpu"
    PREMIUM_GPU = "premium_gpu"


@dataclass
class MarketConditions:
    """Current market conditions"""

    current_gas_price: float
    gpu_utilization_rate: float
    average_hourly_price: float
    price_volatility: float
    demand_level: float
    supply_level: float
    timestamp: datetime


@dataclass
class TaskRequirements:
    """Task requirements for bidding"""

    task_id: str
    agent_id: str
    urgency: UrgencyLevel
    estimated_duration: float
    gpu_tier: GPU_Tier
    memory_requirement: int
    compute_intensity: float
    deadline: datetime | None
    max_budget: float
    priority_score: float


@dataclass
class BidParameters:
    """Parameters for bid calculation"""

    base_price: float
    urgency_multiplier: float
    tier_multiplier: float
    market_multiplier: float
    competition_factor: float
    time_factor: float
    risk_premium: float


@dataclass
class BidResult:
    """Result of bid calculation"""

    bid_price: float
    bid_strategy: BidStrategy
    confidence_score: float
    expected_wait_time: float
    success_probability: float
    cost_efficiency: float
    reasoning: list[str]
    bid_parameters: BidParameters


class BidStrategyEngine:
    """Intelligent bidding engine for GPU rental negotiations"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.market_history: list[MarketConditions] = []
        self.bid_history: list[BidResult] = []
        self.agent_preferences: dict[str, dict[str, Any]] = {}
        self.strategy_weights = {
            BidStrategy.URGENT_BID: 0.25,
            BidStrategy.COST_OPTIMIZED: 0.25,
            BidStrategy.BALANCED: 0.25,
            BidStrategy.AGGRESSIVE: 0.15,
            BidStrategy.CONSERVATIVE: 0.1,
        }
        self.market_window = 24
        self.price_history_days = 30
        self.volatility_threshold = 0.15

    async def initialize(self) -> None:
        """Initialize the bid strategy engine"""
        logger.info("Initializing Bid Strategy Engine")
        await self._load_market_history()
        await self._load_agent_preferences()
        asyncio.create_task(self._monitor_market_conditions())
        logger.info("Bid Strategy Engine initialized")

    async def calculate_bid(
        self,
        task_requirements: TaskRequirements,
        strategy: BidStrategy | None = None,
        custom_parameters: dict[str, Any] | None = None,
    ) -> BidResult:
        """Calculate optimal bid for GPU rental"""
        try:
            market_conditions = await self._get_current_market_conditions()
            if strategy is None:
                strategy = await self._select_optimal_strategy(task_requirements, market_conditions)
            bid_params = await self._calculate_bid_parameters(
                task_requirements, market_conditions, strategy, custom_parameters
            )
            bid_price = await self._calculate_bid_price(bid_params, task_requirements)
            success_probability = await self._calculate_success_probability(bid_price, task_requirements, market_conditions)
            expected_wait_time = await self._estimate_wait_time(bid_price, task_requirements, market_conditions)
            confidence_score = await self._calculate_confidence_score(bid_params, market_conditions, strategy)
            cost_efficiency = await self._calculate_cost_efficiency(bid_price, task_requirements)
            reasoning = await self._generate_bid_reasoning(bid_params, task_requirements, market_conditions, strategy)
            bid_result = BidResult(
                bid_price=bid_price,
                bid_strategy=strategy,
                confidence_score=confidence_score,
                expected_wait_time=expected_wait_time,
                success_probability=success_probability,
                cost_efficiency=cost_efficiency,
                reasoning=reasoning,
                bid_parameters=bid_params,
            )
            self.bid_history.append(bid_result)
            logger.info("Calculated bid for task %s: %s AITBC/hour", task_requirements.task_id, bid_price)
            return bid_result
        except Exception as e:
            logger.error("Failed to calculate bid: %s", e)
            raise

    async def update_agent_preferences(self, agent_id: str, preferences: dict[str, Any]) -> None:
        """Update agent bidding preferences"""
        self.agent_preferences[agent_id] = {
            "preferred_strategy": preferences.get("preferred_strategy", "balanced"),
            "risk_tolerance": preferences.get("risk_tolerance", 0.5),
            "cost_sensitivity": preferences.get("cost_sensitivity", 0.5),
            "urgency_preference": preferences.get("urgency_preference", 0.5),
            "max_wait_time": preferences.get("max_wait_time", 3600),
            "min_success_probability": preferences.get("min_success_probability", 0.7),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Updated preferences for agent %s", agent_id)

    async def get_market_analysis(self) -> dict[str, Any]:
        """Get comprehensive market analysis"""
        market_conditions = await self._get_current_market_conditions()
        price_trend = await self._calculate_price_trend()
        demand_trend = await self._calculate_demand_trend()
        volatility_trend = await self._calculate_volatility_trend()
        future_conditions = await self._predict_market_conditions(24)
        return {
            "current_conditions": asdict(market_conditions),
            "price_trend": price_trend,
            "demand_trend": demand_trend,
            "volatility_trend": volatility_trend,
            "future_prediction": asdict(future_conditions),
            "recommendations": await self._generate_market_recommendations(market_conditions),
            "analysis_timestamp": datetime.now(UTC).isoformat(),
        }

    async def _select_optimal_strategy(
        self, task_requirements: TaskRequirements, market_conditions: MarketConditions
    ) -> BidStrategy:
        """Select optimal bidding strategy based on requirements and conditions"""
        agent_prefs = self.agent_preferences.get(task_requirements.agent_id, {})
        strategy_scores = {}
        if task_requirements.urgency in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL]:
            strategy_scores[BidStrategy.URGENT_BID] = 0.9
        else:
            strategy_scores[BidStrategy.URGENT_BID] = 0.3
        if task_requirements.max_budget < market_conditions.average_hourly_price:
            strategy_scores[BidStrategy.COST_OPTIMIZED] = 0.8
        else:
            strategy_scores[BidStrategy.COST_OPTIMIZED] = 0.5
        strategy_scores[BidStrategy.BALANCED] = 0.7
        if market_conditions.demand_level > 0.8:
            strategy_scores[BidStrategy.AGGRESSIVE] = 0.6
        else:
            strategy_scores[BidStrategy.AGGRESSIVE] = 0.3
        if market_conditions.price_volatility > self.volatility_threshold:
            strategy_scores[BidStrategy.CONSERVATIVE] = 0.7
        else:
            strategy_scores[BidStrategy.CONSERVATIVE] = 0.4
        preferred_strategy = agent_prefs.get("preferred_strategy")
        if preferred_strategy:
            strategy_scores[BidStrategy(preferred_strategy)] *= 1.2
        optimal_strategy = max(strategy_scores, key=strategy_scores.get)  # type: ignore[arg-type]
        logger.debug("Selected strategy %s for task %s", optimal_strategy, task_requirements.task_id)
        return optimal_strategy

    async def _calculate_bid_parameters(
        self,
        task_requirements: TaskRequirements,
        market_conditions: MarketConditions,
        strategy: BidStrategy,
        custom_parameters: dict[str, Any] | None,
    ) -> BidParameters:
        """Calculate bid parameters based on strategy and conditions"""
        base_price = market_conditions.average_hourly_price
        tier_multipliers = {
            GPU_Tier.CPU_ONLY: 0.3,
            GPU_Tier.LOW_END_GPU: 0.6,
            GPU_Tier.MID_RANGE_GPU: 1.0,
            GPU_Tier.HIGH_END_GPU: 1.8,
            GPU_Tier.PREMIUM_GPU: 3.0,
        }
        tier_multiplier = tier_multipliers[task_requirements.gpu_tier]
        urgency_multipliers = {
            BidStrategy.URGENT_BID: 1.5,
            BidStrategy.COST_OPTIMIZED: 0.8,
            BidStrategy.BALANCED: 1.0,
            BidStrategy.AGGRESSIVE: 1.3,
            BidStrategy.CONSERVATIVE: 0.9,
        }
        urgency_multiplier = urgency_multipliers[strategy]
        market_multiplier = 1.0
        if market_conditions.demand_level > 0.8:
            market_multiplier *= 1.2
        if market_conditions.supply_level < 0.3:
            market_multiplier *= 1.3
        if market_conditions.price_volatility > self.volatility_threshold:
            market_multiplier *= 1.1
        competition_factor = market_conditions.demand_level / max(market_conditions.supply_level, 0.1)
        time_factor = 1.0
        if task_requirements.deadline:
            time_remaining = (task_requirements.deadline - datetime.now(UTC)).total_seconds() / 3600
            if time_remaining < 2:
                time_factor = 1.5
            elif time_remaining < 6:
                time_factor = 1.2
            elif time_remaining < 24:
                time_factor = 1.1
        risk_premiums = {
            BidStrategy.URGENT_BID: 0.2,
            BidStrategy.COST_OPTIMIZED: 0.05,
            BidStrategy.BALANCED: 0.1,
            BidStrategy.AGGRESSIVE: 0.25,
            BidStrategy.CONSERVATIVE: 0.08,
        }
        risk_premium = risk_premiums[strategy]
        if custom_parameters:
            if "base_price_adjustment" in custom_parameters:
                base_price *= 1 + custom_parameters["base_price_adjustment"]
            if "tier_multiplier_adjustment" in custom_parameters:
                tier_multiplier *= 1 + custom_parameters["tier_multiplier_adjustment"]
            if "risk_premium_adjustment" in custom_parameters:
                risk_premium *= 1 + custom_parameters["risk_premium_adjustment"]
        return BidParameters(
            base_price=base_price,
            urgency_multiplier=urgency_multiplier,
            tier_multiplier=tier_multiplier,
            market_multiplier=market_multiplier,
            competition_factor=competition_factor,
            time_factor=time_factor,
            risk_premium=risk_premium,
        )

    async def _calculate_bid_price(self, bid_params: BidParameters, task_requirements: TaskRequirements) -> float:
        """Calculate final bid price"""
        price = bid_params.base_price
        price *= bid_params.urgency_multiplier
        price *= bid_params.tier_multiplier
        price *= bid_params.market_multiplier
        price *= 1 + bid_params.competition_factor * 0.3
        price *= bid_params.time_factor
        price *= 1 + bid_params.risk_premium
        duration_multiplier = max(0.8, min(1.2, 1.0 - (task_requirements.estimated_duration - 1) * 0.05))
        price *= duration_multiplier
        max_hourly_rate = task_requirements.max_budget / max(task_requirements.estimated_duration, 0.1)
        price = min(price, max_hourly_rate)
        price = round(price, 6)
        return max(price, 0.001)

    async def _calculate_success_probability(
        self, bid_price: float, task_requirements: TaskRequirements, market_conditions: MarketConditions
    ) -> float:
        """Calculate probability of bid success"""
        base_prob = 1.0 - market_conditions.demand_level
        price_competitiveness = market_conditions.average_hourly_price / max(bid_price, 0.001)
        price_factor = min(1.0, price_competitiveness)
        urgency_factor = 1.0
        if task_requirements.urgency == UrgencyLevel.CRITICAL:
            urgency_factor = 0.8
        elif task_requirements.urgency == UrgencyLevel.HIGH:
            urgency_factor = 0.9
        time_factor = 1.0
        if task_requirements.deadline:
            time_remaining = (task_requirements.deadline - datetime.now(UTC)).total_seconds() / 3600
            if time_remaining < 2:
                time_factor = 0.7
            elif time_remaining < 6:
                time_factor = 0.85
        success_prob = base_prob * 0.4 + price_factor * 0.3 + urgency_factor * 0.2 + time_factor * 0.1
        return max(0.1, min(0.95, success_prob))

    async def _estimate_wait_time(
        self, bid_price: float, task_requirements: TaskRequirements, market_conditions: MarketConditions
    ) -> float:
        """Estimate wait time for resource allocation"""
        base_wait = 300
        demand_factor = market_conditions.demand_level * 600
        price_ratio = bid_price / market_conditions.average_hourly_price
        price_factor = max(0.5, 2.0 - price_ratio) * 300
        urgency_factor = 0
        if task_requirements.urgency == UrgencyLevel.CRITICAL:
            urgency_factor = -300
        elif task_requirements.urgency == UrgencyLevel.HIGH:
            urgency_factor = -120
        tier_factors = {
            GPU_Tier.CPU_ONLY: -180,
            GPU_Tier.LOW_END_GPU: -60,
            GPU_Tier.MID_RANGE_GPU: 0,
            GPU_Tier.HIGH_END_GPU: 120,
            GPU_Tier.PREMIUM_GPU: 300,
        }
        tier_factor = tier_factors[task_requirements.gpu_tier]
        wait_time = base_wait + demand_factor + price_factor + urgency_factor + tier_factor
        return max(60, wait_time)

    async def _calculate_confidence_score(
        self, bid_params: BidParameters, market_conditions: MarketConditions, strategy: BidStrategy
    ) -> float:
        """Calculate confidence in bid calculation"""
        stability_factor = 1.0 - market_conditions.price_volatility
        strategy_confidence = {
            BidStrategy.BALANCED: 0.9,
            BidStrategy.COST_OPTIMIZED: 0.8,
            BidStrategy.CONSERVATIVE: 0.85,
            BidStrategy.URGENT_BID: 0.7,
            BidStrategy.AGGRESSIVE: 0.6,
        }
        data_factor = min(1.0, len(self.market_history) / 24)
        param_factor = 1.0
        if bid_params.urgency_multiplier > 2.0 or bid_params.tier_multiplier > 3.0:
            param_factor = 0.8
        confidence = stability_factor * 0.3 + strategy_confidence[strategy] * 0.3 + data_factor * 0.2 + param_factor * 0.2
        return max(0.3, min(0.95, confidence))

    async def _calculate_cost_efficiency(self, bid_price: float, task_requirements: TaskRequirements) -> float:
        """Calculate cost efficiency of the bid"""
        market_price = await self._get_market_price_for_tier(task_requirements.gpu_tier)
        price_efficiency = market_price / max(bid_price, 0.001)
        duration_efficiency = min(1.2, 1.0 + (task_requirements.estimated_duration - 1) * 0.05)
        compute_efficiency = task_requirements.compute_intensity
        budget_utilization = bid_price * task_requirements.estimated_duration / max(task_requirements.max_budget, 0.001)
        budget_efficiency = 1.0 - abs(budget_utilization - 0.8)
        efficiency = price_efficiency * 0.4 + duration_efficiency * 0.2 + compute_efficiency * 0.2 + budget_efficiency * 0.2
        return max(0.1, min(1.0, efficiency))

    async def _generate_bid_reasoning(
        self,
        bid_params: BidParameters,
        task_requirements: TaskRequirements,
        market_conditions: MarketConditions,
        strategy: BidStrategy,
    ) -> list[str]:
        """Generate reasoning for bid calculation"""
        reasoning = []
        reasoning.append(f"Strategy: {strategy.value} selected based on task urgency and market conditions")
        if market_conditions.demand_level > 0.8:
            reasoning.append("High market demand increases bid price")
        elif market_conditions.demand_level < 0.3:
            reasoning.append("Low market demand allows for competitive pricing")
        tier_names = {
            GPU_Tier.CPU_ONLY: "CPU-only resources",
            GPU_Tier.LOW_END_GPU: "low-end GPU",
            GPU_Tier.MID_RANGE_GPU: "mid-range GPU",
            GPU_Tier.HIGH_END_GPU: "high-end GPU",
            GPU_Tier.PREMIUM_GPU: "premium GPU",
        }
        reasoning.append(
            f"Selected {tier_names[task_requirements.gpu_tier]} with {bid_params.tier_multiplier:.1f}x multiplier"
        )
        if task_requirements.urgency == UrgencyLevel.CRITICAL:
            reasoning.append("Critical urgency requires aggressive bidding")
        elif task_requirements.urgency == UrgencyLevel.LOW:
            reasoning.append("Low urgency allows for cost-optimized bidding")
        if bid_params.market_multiplier > 1.1:
            reasoning.append("Market conditions require price premium")
        elif bid_params.market_multiplier < 0.9:
            reasoning.append("Favorable market conditions enable discount pricing")
        if bid_params.risk_premium > 0.15:
            reasoning.append("High risk premium applied due to strategy and volatility")
        return reasoning

    async def _get_current_market_conditions(self) -> MarketConditions:
        """Get current market conditions"""
        return MarketConditions(
            current_gas_price=20.0,
            gpu_utilization_rate=0.75,
            average_hourly_price=0.05,
            price_volatility=0.12,
            demand_level=0.68,
            supply_level=0.72,
            timestamp=datetime.now(UTC),
        )

    async def _load_market_history(self) -> None:
        """Load historical market data"""
        pass

    async def _load_agent_preferences(self) -> None:
        """Load agent preferences from storage"""
        pass

    async def _monitor_market_conditions(self) -> None:
        """Monitor market conditions continuously"""
        while True:
            try:
                conditions = await self._get_current_market_conditions()
                self.market_history.append(conditions)
                if len(self.market_history) > self.price_history_days * 24:
                    self.market_history = self.market_history[-(self.price_history_days * 24) :]
                await asyncio.sleep(300)
            except Exception as e:
                logger.error("Error monitoring market conditions: %s", e)
                await asyncio.sleep(60)

    async def _calculate_price_trend(self) -> str:
        """Calculate price trend"""
        if len(self.market_history) < 2:
            return "insufficient_data"
        recent_prices = [c.average_hourly_price for c in self.market_history[-24:]]
        older_prices = [c.average_hourly_price for c in self.market_history[-48:-24]]
        if not older_prices:
            return "insufficient_data"
        recent_avg = sum(recent_prices) / len(recent_prices)
        older_avg = sum(older_prices) / len(older_prices)
        change = (recent_avg - older_avg) / older_avg
        if change > 0.05:
            return "increasing"
        elif change < -0.05:
            return "decreasing"
        else:
            return "stable"

    async def _calculate_demand_trend(self) -> str:
        """Calculate demand trend"""
        if len(self.market_history) < 2:
            return "insufficient_data"
        recent_demand = [c.demand_level for c in self.market_history[-24:]]
        older_demand = [c.demand_level for c in self.market_history[-48:-24]]
        if not older_demand:
            return "insufficient_data"
        recent_avg = sum(recent_demand) / len(recent_demand)
        older_avg = sum(older_demand) / len(older_demand)
        change = recent_avg - older_avg
        if change > 0.1:
            return "increasing"
        elif change < -0.1:
            return "decreasing"
        else:
            return "stable"

    async def _calculate_volatility_trend(self) -> str:
        """Calculate volatility trend"""
        if len(self.market_history) < 2:
            return "insufficient_data"
        recent_vol = [c.price_volatility for c in self.market_history[-24:]]
        older_vol = [c.price_volatility for c in self.market_history[-48:-24]]
        if not older_vol:
            return "insufficient_data"
        recent_avg = sum(recent_vol) / len(recent_vol)
        older_avg = sum(older_vol) / len(older_vol)
        change = recent_avg - older_avg
        if change > 0.05:
            return "increasing"
        elif change < -0.05:
            return "decreasing"
        else:
            return "stable"

    async def _predict_market_conditions(self, hours_ahead: int) -> MarketConditions:
        """Predict future market conditions"""
        if len(self.market_history) < 24:
            return await self._get_current_market_conditions()
        self.market_history[-24:]
        price_trend = await self._calculate_price_trend()
        demand_trend = await self._calculate_demand_trend()
        current = await self._get_current_market_conditions()
        predicted = MarketConditions(
            current_gas_price=current.current_gas_price,
            gpu_utilization_rate=current.gpu_utilization_rate,
            average_hourly_price=current.average_hourly_price,
            price_volatility=current.price_volatility,
            demand_level=current.demand_level,
            supply_level=current.supply_level,
            timestamp=datetime.now(UTC) + timedelta(hours=hours_ahead),
        )
        if price_trend == "increasing":
            predicted.average_hourly_price *= 1.05
        elif price_trend == "decreasing":
            predicted.average_hourly_price *= 0.95
        if demand_trend == "increasing":
            predicted.demand_level = min(1.0, predicted.demand_level + 0.1)
        elif demand_trend == "decreasing":
            predicted.demand_level = max(0.0, predicted.demand_level - 0.1)
        return predicted

    async def _generate_market_recommendations(self, market_conditions: MarketConditions) -> list[str]:
        """Generate market recommendations"""
        recommendations = []
        if market_conditions.demand_level > 0.8:
            recommendations.append("High demand detected - consider urgent bidding strategy")
        if market_conditions.price_volatility > self.volatility_threshold:
            recommendations.append("High volatility - consider conservative bidding")
        if market_conditions.gpu_utilization_rate > 0.9:
            recommendations.append("GPU utilization very high - expect longer wait times")
        if market_conditions.supply_level < 0.3:
            recommendations.append("Low supply - expect higher prices")
        if market_conditions.average_hourly_price < 0.03:
            recommendations.append("Low prices - good opportunity for cost optimization")
        return recommendations

    async def _get_market_price_for_tier(self, gpu_tier: GPU_Tier) -> float:
        """Get market price for specific GPU tier"""
        tier_prices = {
            GPU_Tier.CPU_ONLY: 0.01,
            GPU_Tier.LOW_END_GPU: 0.03,
            GPU_Tier.MID_RANGE_GPU: 0.05,
            GPU_Tier.HIGH_END_GPU: 0.09,
            GPU_Tier.PREMIUM_GPU: 0.15,
        }
        return tier_prices.get(gpu_tier, 0.05)
