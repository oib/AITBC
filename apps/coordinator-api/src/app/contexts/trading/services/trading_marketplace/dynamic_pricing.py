"""
Dynamic Pricing Engine for AITBC Marketplace
Implements sophisticated pricing algorithms based on real-time market conditions
"""

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np

from aitbc.aitbc_logging import get_logger

# Importing the pricing persistence models at module load registers their tables
# with SQLModel.metadata so init_db()/create_all() creates them at startup.
from ...domain.pricing_models import (  # noqa: E402
    PricingHistory,
    ProviderPricingStrategy,
)
from ...domain.pricing_models import (  # noqa: E402
    ResourceType as PricingResourceType,
)

logger = get_logger(__name__)


class PricingStrategy(StrEnum):
    """Dynamic pricing strategy types"""

    AGGRESSIVE_GROWTH = "aggressive_growth"
    PROFIT_MAXIMIZATION = "profit_maximization"
    MARKET_BALANCE = "market_balance"
    COMPETITIVE_RESPONSE = "competitive_response"
    DEMAND_ELASTICITY = "demand_elasticity"
    TIME_BASED = "time_based"
    REPUTATION_BASED = "reputation_based"
    MULTI_FACTOR = "multi_factor"
    PREDICTIVE = "predictive"


class ResourceType(StrEnum):
    """Resource types for pricing"""

    GPU = "gpu"
    SERVICE = "service"
    STORAGE = "storage"


class PriceTrend(StrEnum):
    """Price trend indicators"""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class PricingFactors:
    """Factors that influence dynamic pricing"""

    base_price: float
    demand_multiplier: float = 1.0
    supply_multiplier: float = 1.0
    time_multiplier: float = 1.0
    performance_multiplier: float = 1.0
    competition_multiplier: float = 1.0
    sentiment_multiplier: float = 1.0
    regional_multiplier: float = 1.0
    confidence_score: float = 0.8
    risk_adjustment: float = 0.0
    demand_level: float = 0.5
    supply_level: float = 0.5
    market_volatility: float = 0.1
    provider_reputation: float = 1.0
    utilization_rate: float = 0.5
    historical_performance: float = 1.0


@dataclass
class PriceConstraints:
    """Constraints for pricing calculations"""

    min_price: float | None = None
    max_price: float | None = None
    max_change_percent: float = 0.5
    min_change_interval: int = 300
    strategy_lock_period: int = 3600


@dataclass
class PricePoint:
    """Single price point in time series"""

    timestamp: datetime
    price: float
    demand_level: float
    supply_level: float
    confidence: float
    strategy_used: str


@dataclass
class MarketConditions:
    """Current market conditions snapshot"""

    region: str
    resource_type: ResourceType
    demand_level: float
    supply_level: float
    average_price: float
    price_volatility: float
    utilization_rate: float
    competitor_prices: list[float] = field(default_factory=list)
    market_sentiment: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PricingResult:
    """Result of dynamic pricing calculation"""

    resource_id: str
    resource_type: ResourceType
    current_price: float
    recommended_price: float
    price_trend: PriceTrend
    confidence_score: float
    factors_exposed: dict[str, float]
    reasoning: list[str]
    next_update: datetime
    strategy_used: PricingStrategy


class DynamicPricingEngine:
    """Core dynamic pricing engine with advanced algorithms"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.pricing_history: dict[str, list[PricePoint]] = {}
        self.market_conditions_cache: dict[str, MarketConditions] = {}
        self.provider_strategies: dict[str, PricingStrategy] = {}
        self.price_constraints: dict[str, PriceConstraints] = {}
        self.strategy_configs = {
            PricingStrategy.AGGRESSIVE_GROWTH: {
                "base_multiplier": 0.85,
                "demand_sensitivity": 0.3,
                "competition_weight": 0.4,
                "growth_priority": 0.8,
            },
            PricingStrategy.PROFIT_MAXIMIZATION: {
                "base_multiplier": 1.25,
                "demand_sensitivity": 0.7,
                "competition_weight": 0.2,
                "growth_priority": 0.2,
            },
            PricingStrategy.MARKET_BALANCE: {
                "base_multiplier": 1.0,
                "demand_sensitivity": 0.5,
                "competition_weight": 0.3,
                "growth_priority": 0.5,
            },
            PricingStrategy.COMPETITIVE_RESPONSE: {
                "base_multiplier": 0.95,
                "demand_sensitivity": 0.4,
                "competition_weight": 0.6,
                "growth_priority": 0.4,
            },
            PricingStrategy.DEMAND_ELASTICITY: {
                "base_multiplier": 1.0,
                "demand_sensitivity": 0.8,
                "competition_weight": 0.3,
                "growth_priority": 0.6,
            },
            PricingStrategy.TIME_BASED: {
                "base_multiplier": 1.0,
                "peak_hours_multiplier": 1.3,
                "off_peak_multiplier": 0.8,
                "weekend_multiplier": 0.9,
                "hourly_sensitivity": 0.5,
            },
            PricingStrategy.REPUTATION_BASED: {
                "base_multiplier": 1.0,
                "reputation_weight": 0.6,
                "performance_weight": 0.3,
                "history_weight": 0.1,
            },
            PricingStrategy.MULTI_FACTOR: {
                "base_multiplier": 1.0,
                "demand_weight": 0.25,
                "supply_weight": 0.2,
                "time_weight": 0.15,
                "reputation_weight": 0.15,
                "competition_weight": 0.15,
                "regional_weight": 0.1,
            },
            PricingStrategy.PREDICTIVE: {
                "base_multiplier": 1.0,
                "forecast_weight": 0.5,
                "current_weight": 0.3,
                "trend_weight": 0.2,
                "ml_confidence_threshold": 0.7,
            },
        }
        self.min_price = config.get("min_price", 0.001)
        self.max_price = config.get("max_price", 1000.0)
        self.update_interval = config.get("update_interval", 300)
        self.forecast_horizon = config.get("forecast_horizon", 72)
        self.max_volatility_threshold = config.get("max_volatility_threshold", 0.3)
        self.circuit_breaker_threshold = config.get("circuit_breaker_threshold", 0.5)
        self.circuit_breakers: dict[str, bool] = {}

    async def initialize(self) -> None:
        """Initialize the dynamic pricing engine"""
        logger.info("Initializing Dynamic Pricing Engine")
        await self._load_pricing_history()
        await self._load_provider_strategies()
        asyncio.create_task(self._update_market_conditions())
        asyncio.create_task(self._monitor_price_volatility())
        asyncio.create_task(self._optimize_strategies())
        logger.info("Dynamic Pricing Engine initialized")

    async def calculate_dynamic_price(
        self,
        resource_id: str,
        resource_type: ResourceType,
        base_price: float,
        strategy: PricingStrategy | None = None,
        constraints: PriceConstraints | None = None,
        region: str = "global",
    ) -> PricingResult:
        """Calculate dynamic price for a resource"""
        try:
            if strategy is None:
                strategy = self.provider_strategies.get(resource_id, PricingStrategy.MARKET_BALANCE)
            market_conditions = await self._get_market_conditions(resource_type, region)
            factors = await self._calculate_pricing_factors(
                resource_id, resource_type, base_price, strategy, market_conditions
            )
            strategy_price = await self._apply_strategy_pricing(base_price, factors, strategy, market_conditions)
            final_price = await self._apply_constraints_and_risk(resource_id, strategy_price, constraints, factors)
            price_trend = await self._determine_price_trend(resource_id, final_price)
            reasoning = await self._generate_pricing_reasoning(factors, strategy, market_conditions, price_trend)
            confidence = await self._calculate_confidence_score(factors, market_conditions)
            next_update = datetime.now(UTC) + timedelta(seconds=self.update_interval)
            await self._store_price_point(resource_id, resource_type, final_price, factors, strategy)
            result = PricingResult(
                resource_id=resource_id,
                resource_type=resource_type,
                current_price=base_price,
                recommended_price=final_price,
                price_trend=price_trend,
                confidence_score=confidence,
                factors_exposed=asdict(factors),
                reasoning=reasoning,
                next_update=next_update,
                strategy_used=strategy,
            )
            logger.info("Calculated dynamic price for %s: %s (was %s)", resource_id, final_price, base_price)
            return result
        except Exception as e:
            logger.error("Failed to calculate dynamic price for %s: %s", resource_id, e)
            raise

    async def get_price_forecast(self, resource_id: str, hours_ahead: int = 24) -> list[PricePoint]:
        """Generate price forecast for the specified horizon"""
        try:
            if resource_id not in self.pricing_history:
                return []
            historical_data = self.pricing_history[resource_id]
            if len(historical_data) < 24:
                return []
            prices = [point.price for point in historical_data[-48:]]
            demand_levels = [point.demand_level for point in historical_data[-48:]]
            supply_levels = [point.supply_level for point in historical_data[-48:]]
            forecast_points = []
            for hour in range(1, hours_ahead + 1):
                price_trend = self._calculate_price_trend(prices[-12:])
                seasonal_factor = self._calculate_seasonal_factor(hour)
                demand_forecast = self._forecast_demand_level(demand_levels, hour)
                supply_forecast = self._forecast_supply_level(supply_levels, hour)
                base_forecast = prices[-1] + price_trend * hour
                seasonal_adjusted = base_forecast * seasonal_factor
                demand_adjusted = seasonal_adjusted * (1 + (demand_forecast - 0.5) * 0.3)
                supply_adjusted = demand_adjusted * (1 + (0.5 - supply_forecast) * 0.2)
                forecast_price = max(self.min_price, min(supply_adjusted, self.max_price))
                confidence = max(0.3, 0.9 - hour / hours_ahead * 0.6)
                forecast_point = PricePoint(
                    timestamp=datetime.now(UTC) + timedelta(hours=hour),
                    price=forecast_price,
                    demand_level=demand_forecast,
                    supply_level=supply_forecast,
                    confidence=confidence,
                    strategy_used="forecast",
                )
                forecast_points.append(forecast_point)
            return forecast_points
        except Exception as e:
            logger.error("Failed to generate price forecast for %s: %s", resource_id, e)
            return []

    async def set_provider_strategy(
        self, provider_id: str, strategy: PricingStrategy, constraints: PriceConstraints | None = None
    ) -> bool:
        """Set pricing strategy for a provider"""
        try:
            self.provider_strategies[provider_id] = strategy
            if constraints:
                self.price_constraints[provider_id] = constraints
            await self._persist_provider_strategy(provider_id, strategy, constraints)
            logger.info("Set strategy %s for provider %s", strategy.value, provider_id)
            return True
        except Exception as e:
            logger.error("Failed to set strategy for provider %s: %s", provider_id, e)
            return False

    async def _persist_provider_strategy(
        self, provider_id: str, strategy: PricingStrategy, constraints: PriceConstraints | None
    ) -> None:
        """Persist a provider strategy, deactivating any prior active row (best-effort)."""

        def _write() -> None:
            from sqlmodel import select

            from .....storage.db import session_scope

            with session_scope() as session:
                existing = (
                    session.execute(
                        select(ProviderPricingStrategy).where(
                            ProviderPricingStrategy.provider_id == provider_id,
                            ProviderPricingStrategy.is_active == True,  # noqa: E712
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in existing:
                    row.is_active = False
                    session.add(row)
                session.add(
                    ProviderPricingStrategy(
                        provider_id=provider_id,
                        strategy_type=strategy.value,
                        strategy_name=strategy.value,
                        parameters=self.strategy_configs.get(strategy, {}),
                        min_price=constraints.min_price if constraints else None,
                        max_price=constraints.max_price if constraints else None,
                        max_change_percent=constraints.max_change_percent if constraints else 0.5,
                        min_change_interval=constraints.min_change_interval if constraints else 300,
                        strategy_lock_period=constraints.strategy_lock_period if constraints else 3600,
                        is_active=True,
                    )
                )
                session.commit()

        try:
            await asyncio.to_thread(_write)
        except Exception as e:
            logger.warning("Failed to persist strategy for provider %s: %s", provider_id, e)

    async def _calculate_pricing_factors(
        self,
        resource_id: str,
        resource_type: ResourceType,
        base_price: float,
        strategy: PricingStrategy,
        market_conditions: MarketConditions,
    ) -> PricingFactors:
        """Calculate all pricing factors"""
        factors = PricingFactors(base_price=base_price)
        factors.demand_multiplier = self._calculate_demand_multiplier(market_conditions.demand_level, strategy)
        factors.supply_multiplier = self._calculate_supply_multiplier(market_conditions.supply_level, strategy)
        factors.time_multiplier = self._calculate_time_multiplier()
        factors.performance_multiplier = await self._calculate_performance_multiplier(resource_id)
        factors.competition_multiplier = self._calculate_competition_multiplier(
            base_price, market_conditions.competitor_prices, strategy
        )
        factors.sentiment_multiplier = self._calculate_sentiment_multiplier(market_conditions.market_sentiment)
        factors.regional_multiplier = self._calculate_regional_multiplier(market_conditions.region, resource_type)
        factors.demand_level = market_conditions.demand_level
        factors.supply_level = market_conditions.supply_level
        factors.market_volatility = market_conditions.price_volatility
        return factors

    async def _apply_strategy_pricing(
        self, base_price: float, factors: PricingFactors, strategy: PricingStrategy, market_conditions: MarketConditions
    ) -> float:
        """Apply strategy-specific pricing logic"""
        config = self.strategy_configs[strategy]
        price = base_price
        if strategy == PricingStrategy.TIME_BASED:
            return await self._calculate_time_based_price(base_price, factors, config)
        elif strategy == PricingStrategy.REPUTATION_BASED:
            return await self._calculate_reputation_based_price(base_price, factors, config)
        elif strategy == PricingStrategy.MULTI_FACTOR:
            return await self._calculate_multi_factor_price(base_price, factors, config)
        elif strategy == PricingStrategy.PREDICTIVE:
            return await self._calculate_predictive_price(base_price, factors, config, market_conditions)
        price *= config["base_multiplier"]
        demand_adjustment = (factors.demand_level - 0.5) * config["demand_sensitivity"]
        price *= 1 + demand_adjustment
        if market_conditions.competitor_prices:
            avg_competitor_price = np.mean(market_conditions.competitor_prices)
            competition_ratio = avg_competitor_price / base_price
            competition_adjustment = (competition_ratio - 1) * config["competition_weight"]
            price = float(price * (1 + competition_adjustment))
        price *= factors.time_multiplier
        price *= factors.performance_multiplier
        price *= factors.sentiment_multiplier
        price *= factors.regional_multiplier
        if config["growth_priority"] > 0.5:
            price *= 1 - (config["growth_priority"] - 0.5) * 0.2
        return max(price, self.min_price)  # type: ignore[no-any-return]

    async def _apply_constraints_and_risk(
        self, resource_id: str, price: float, constraints: PriceConstraints | None, factors: PricingFactors
    ) -> float:
        """Apply pricing constraints and risk management"""
        if self.circuit_breakers.get(resource_id, False):
            logger.warning("Circuit breaker active for %s, using last price", resource_id)
            if resource_id in self.pricing_history and self.pricing_history[resource_id]:
                return self.pricing_history[resource_id][-1].price
        if constraints:
            if constraints.min_price:
                price = max(price, constraints.min_price)
            if constraints.max_price:
                price = min(price, constraints.max_price)
        price = max(price, self.min_price)
        price = min(price, self.max_price)
        if resource_id in self.pricing_history and self.pricing_history[resource_id]:
            last_price = self.pricing_history[resource_id][-1].price
            max_change = last_price * 0.5
            if abs(price - last_price) > max_change:
                price = last_price + (max_change if price > last_price else -max_change)
                logger.info("Applied max change constraint for %s", resource_id)
        if factors.market_volatility > self.circuit_breaker_threshold:
            self.circuit_breakers[resource_id] = True
            logger.warning("Triggered circuit breaker for %s due to high volatility", resource_id)
            asyncio.create_task(self._reset_circuit_breaker(resource_id, 3600))
        return price

    def _calculate_demand_multiplier(self, demand_level: float, strategy: PricingStrategy) -> float:
        """Calculate demand-based price multiplier"""
        if demand_level > 0.8:
            base_multiplier = 1.0 + (demand_level - 0.8) * 2.5
        elif demand_level > 0.5:
            base_multiplier = 1.0 + (demand_level - 0.5) * 0.5
        else:
            base_multiplier = 0.8 + demand_level * 0.4
        if strategy == PricingStrategy.AGGRESSIVE_GROWTH:
            return base_multiplier * 0.9
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            return base_multiplier * 1.3
        else:
            return base_multiplier

    def _calculate_supply_multiplier(self, supply_level: float, strategy: PricingStrategy) -> float:
        """Calculate supply-based price multiplier"""
        if supply_level < 0.3:
            base_multiplier = 1.0 + (0.3 - supply_level) * 1.5
        elif supply_level < 0.7:
            base_multiplier = 1.0 - (supply_level - 0.3) * 0.3
        else:
            base_multiplier = 0.9 - (supply_level - 0.7) * 0.3
        return max(0.5, min(2.0, base_multiplier))

    def _calculate_time_multiplier(self) -> float:
        """Calculate time-based price multiplier"""
        hour = datetime.now(UTC).hour
        day_of_week = datetime.now(UTC).weekday()
        if 8 <= hour <= 20 and day_of_week < 5:
            return 1.2
        elif 20 <= hour <= 24 or 0 <= hour <= 2:
            return 1.1
        elif 2 <= hour <= 6:
            return 0.8
        elif day_of_week >= 5:
            return 1.15
        else:
            return 1.0

    async def _calculate_performance_multiplier(self, resource_id: str) -> float:
        """Calculate performance-based multiplier"""
        if resource_id in self.pricing_history and len(self.pricing_history[resource_id]) > 10:
            recent_prices = [p.price for p in self.pricing_history[resource_id][-10:]]
            price_variance = np.var(recent_prices)
            avg_price = np.mean(recent_prices)
            if price_variance < avg_price * 0.01:
                return 1.1
            elif price_variance < avg_price * 0.05:
                return 1.05
            else:
                return 0.95
        else:
            return 1.0

    def _calculate_competition_multiplier(
        self, base_price: float, competitor_prices: list[float], strategy: PricingStrategy
    ) -> float:
        """Calculate competition-based multiplier"""
        if not competitor_prices:
            return 1.0
        avg_competitor_price = np.mean(competitor_prices)
        price_ratio = base_price / avg_competitor_price
        if strategy == PricingStrategy.COMPETITIVE_RESPONSE:
            if price_ratio > 1.1:
                return 0.9
            elif price_ratio < 0.9:
                return 1.05
            else:
                return 1.0
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            return float(1.0 + (price_ratio - 1) * 0.3)
        else:
            return float(1.0 + (price_ratio - 1) * 0.5)

    def _calculate_sentiment_multiplier(self, sentiment: float) -> float:
        """Calculate market sentiment multiplier"""
        if sentiment > 0.3:
            return 1.1
        elif sentiment < -0.3:
            return 0.9
        else:
            return 1.0

    def _calculate_regional_multiplier(self, region: str, resource_type: ResourceType) -> float:
        """Calculate regional price multiplier"""
        regional_adjustments = {
            "us_west": {"gpu": 1.1, "service": 1.05, "storage": 1.0},
            "us_east": {"gpu": 1.2, "service": 1.1, "storage": 1.05},
            "europe": {"gpu": 1.15, "service": 1.08, "storage": 1.02},
            "asia": {"gpu": 0.9, "service": 0.95, "storage": 0.9},
            "global": {"gpu": 1.0, "service": 1.0, "storage": 1.0},
        }
        return regional_adjustments.get(region, {}).get(resource_type.value, 1.0)

    async def _determine_price_trend(self, resource_id: str, current_price: float) -> PriceTrend:
        """Determine price trend based on historical data"""
        if resource_id not in self.pricing_history or len(self.pricing_history[resource_id]) < 5:
            return PriceTrend.STABLE
        recent_prices = [p.price for p in self.pricing_history[resource_id][-10:]]
        if len(recent_prices) >= 3:
            recent_avg = np.mean(recent_prices[-3:])
            older_avg = np.mean(recent_prices[-6:-3]) if len(recent_prices) >= 6 else np.mean(recent_prices[:-3])
            change = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            volatility = np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0
            if volatility > 0.2:
                return PriceTrend.VOLATILE
            elif change > 0.05:
                return PriceTrend.INCREASING
            elif change < -0.05:
                return PriceTrend.DECREASING
            else:
                return PriceTrend.STABLE
        else:
            return PriceTrend.STABLE

    async def _generate_pricing_reasoning(
        self, factors: PricingFactors, strategy: PricingStrategy, market_conditions: MarketConditions, trend: PriceTrend
    ) -> list[str]:
        """Generate reasoning for pricing decisions"""
        reasoning = []
        reasoning.append(f"Strategy: {strategy.value} applied")
        if factors.demand_level > 0.8:
            reasoning.append("High demand increases prices")
        elif factors.demand_level < 0.3:
            reasoning.append("Low demand allows competitive pricing")
        if factors.supply_level < 0.3:
            reasoning.append("Limited supply justifies premium pricing")
        elif factors.supply_level > 0.8:
            reasoning.append("High supply enables competitive pricing")
        hour = datetime.now(UTC).hour
        if 8 <= hour <= 20:
            reasoning.append("Business hours premium applied")
        elif 2 <= hour <= 6:
            reasoning.append("Late night discount applied")
        if factors.performance_multiplier > 1.05:
            reasoning.append("High performance justifies premium")
        elif factors.performance_multiplier < 0.95:
            reasoning.append("Performance issues require discount")
        if factors.competition_multiplier != 1.0:
            if factors.competition_multiplier < 1.0:
                reasoning.append("Competitive pricing applied")
            else:
                reasoning.append("Premium pricing over competitors")
        reasoning.append(f"Price trend: {trend.value}")
        return reasoning

    async def _calculate_confidence_score(self, factors: PricingFactors, market_conditions: MarketConditions) -> float:
        """Calculate confidence score for pricing decision"""
        confidence = 0.8
        stability_factor = 1.0 - market_conditions.price_volatility
        confidence *= stability_factor
        data_factor = min(1.0, len(market_conditions.competitor_prices) / 5)
        confidence = confidence * 0.7 + data_factor * 0.3
        if abs(factors.demand_multiplier - 1.0) > 1.5:
            confidence *= 0.9
        if abs(factors.supply_multiplier - 1.0) > 1.0:
            confidence *= 0.9
        return max(0.3, min(0.95, confidence))

    async def _store_price_point(
        self,
        resource_id: str,
        resource_type: ResourceType,
        price: float,
        factors: PricingFactors,
        strategy: PricingStrategy,
    ) -> None:
        """Store price point in history (in-memory cache + durable persistence)."""
        if resource_id not in self.pricing_history:
            self.pricing_history[resource_id] = []
        price_point = PricePoint(
            timestamp=datetime.now(UTC),
            price=price,
            demand_level=factors.demand_level,
            supply_level=factors.supply_level,
            confidence=factors.confidence_score,
            strategy_used=strategy.value,
        )
        self.pricing_history[resource_id].append(price_point)
        if len(self.pricing_history[resource_id]) > 1000:
            self.pricing_history[resource_id] = self.pricing_history[resource_id][-1000:]
        await self._persist_price_point(resource_id, resource_type, price, factors, strategy)

    async def _persist_price_point(
        self,
        resource_id: str,
        resource_type: ResourceType,
        price: float,
        factors: PricingFactors,
        strategy: PricingStrategy,
    ) -> None:
        """Persist a price point to the pricing_history table (best-effort)."""

        def _write() -> None:
            from .....storage.db import session_scope

            with session_scope() as session:
                session.add(
                    PricingHistory(
                        resource_id=resource_id,
                        resource_type=PricingResourceType(resource_type.value),
                        price=price,
                        base_price=factors.base_price,
                        demand_level=factors.demand_level,
                        supply_level=factors.supply_level,
                        market_volatility=factors.market_volatility,
                        utilization_rate=factors.utilization_rate,
                        strategy_used=strategy.value,
                        strategy_parameters=self.strategy_configs.get(strategy, {}),
                        pricing_factors=asdict(factors),
                        confidence_score=factors.confidence_score,
                    )
                )
                session.commit()

        try:
            await asyncio.to_thread(_write)
        except Exception as e:
            # Persistence is best-effort: never let a DB issue break price calculation.
            logger.warning("Failed to persist price point for %s: %s", resource_id, e)

    async def _get_market_conditions(self, resource_type: ResourceType, region: str) -> MarketConditions:
        """Get current market conditions"""
        cache_key = f"{region}_{resource_type.value}"
        if cache_key in self.market_conditions_cache:
            cached = self.market_conditions_cache[cache_key]
            if (datetime.now(UTC) - cached.timestamp).total_seconds() < 300:
                return cached
        conditions = MarketConditions(
            region=region,
            resource_type=resource_type,
            demand_level=0.6 + np.random.normal(0, 0.1),
            supply_level=0.7 + np.random.normal(0, 0.1),
            average_price=0.05 + np.random.normal(0, 0.01),
            price_volatility=0.1 + np.random.normal(0, 0.05),
            utilization_rate=0.65 + np.random.normal(0, 0.1),
            competitor_prices=[0.045, 0.055, 0.048, 0.052],
            market_sentiment=np.random.normal(0.1, 0.2),
        )
        self.market_conditions_cache[cache_key] = conditions
        return conditions

    async def _load_pricing_history(self) -> None:
        """Load recent historical pricing data from the pricing_history table."""

        def _read() -> dict[str, list[PricePoint]]:
            from sqlmodel import select

            from .....storage.db import session_scope

            history: dict[str, list[PricePoint]] = {}
            with session_scope() as session:
                rows = (
                    session.execute(
                        select(PricingHistory).order_by(PricingHistory.timestamp.asc()).limit(10000)  # type: ignore[attr-defined]
                    )
                    .scalars()
                    .all()
                )
            for row in rows:
                points = history.setdefault(row.resource_id, [])
                points.append(
                    PricePoint(
                        timestamp=row.timestamp,
                        price=row.price,
                        demand_level=row.demand_level,
                        supply_level=row.supply_level,
                        confidence=row.confidence_score,
                        strategy_used=row.strategy_used,
                    )
                )
            for resource_id, points in history.items():
                if len(points) > 1000:
                    history[resource_id] = points[-1000:]
            return history

        try:
            self.pricing_history = await asyncio.to_thread(_read)
            logger.info("Loaded pricing history for %d resources", len(self.pricing_history))
        except Exception as e:
            logger.warning("Failed to load pricing history (starting empty): %s", e)
            self.pricing_history = {}

    async def _load_provider_strategies(self) -> None:
        """Load active provider strategies and constraints from storage."""

        def _read() -> tuple[dict[str, PricingStrategy], dict[str, PriceConstraints]]:
            from sqlmodel import select

            from .....storage.db import session_scope

            strategies: dict[str, PricingStrategy] = {}
            constraints: dict[str, PriceConstraints] = {}
            with session_scope() as session:
                rows = (
                    session.execute(
                        select(ProviderPricingStrategy).where(
                            ProviderPricingStrategy.is_active == True  # noqa: E712
                        )
                    )
                    .scalars()
                    .all()
                )
            for row in rows:
                try:
                    strategies[row.provider_id] = PricingStrategy(row.strategy_type)
                except ValueError:
                    logger.warning("Skipping unknown stored strategy %r for provider %s", row.strategy_type, row.provider_id)
                    continue
                constraints[row.provider_id] = PriceConstraints(
                    min_price=row.min_price,
                    max_price=row.max_price,
                    max_change_percent=row.max_change_percent,
                    min_change_interval=row.min_change_interval,
                    strategy_lock_period=row.strategy_lock_period,
                )
            return strategies, constraints

        try:
            self.provider_strategies, self.price_constraints = await asyncio.to_thread(_read)
            logger.info("Loaded strategies for %d providers", len(self.provider_strategies))
        except Exception as e:
            logger.warning("Failed to load provider strategies (starting empty): %s", e)

    async def _update_market_conditions(self) -> None:
        """Background task to update market conditions"""
        while True:
            try:
                self.market_conditions_cache.clear()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error("Error updating market conditions: %s", e)
                await asyncio.sleep(60)

    async def _monitor_price_volatility(self) -> None:
        """Background task to monitor price volatility"""
        while True:
            try:
                for resource_id, history in self.pricing_history.items():
                    if len(history) >= 10:
                        recent_prices = [p.price for p in history[-10:]]
                        volatility = np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0
                        if volatility > self.max_volatility_threshold:
                            logger.warning("High volatility detected for %s: %s", resource_id, volatility)
                await asyncio.sleep(600)
            except Exception as e:
                logger.error("Error monitoring volatility: %s", e)
                await asyncio.sleep(120)

    async def _optimize_strategies(self) -> None:
        """Background task to optimize pricing strategies"""
        while True:
            try:
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error("Error optimizing strategies: %s", e)
                await asyncio.sleep(300)

    async def _reset_circuit_breaker(self, resource_id: str, delay: int) -> None:
        """Reset circuit breaker after delay"""
        await asyncio.sleep(delay)
        self.circuit_breakers[resource_id] = False
        logger.info("Reset circuit breaker for %s", resource_id)

    def _calculate_price_trend(self, prices: list[float]) -> float:
        """Calculate simple price trend"""
        if len(prices) < 2:
            return 0.0
        x = np.arange(len(prices))
        y = np.array(prices)
        slope = np.polyfit(x, y, 1)[0]
        return slope  # type: ignore[no-any-return]

    def _calculate_seasonal_factor(self, hour: int) -> float:
        """Calculate seasonal adjustment factor"""
        if 6 <= hour <= 10:
            return 1.05
        elif 10 <= hour <= 16:
            return 1.1
        elif 16 <= hour <= 20:
            return 1.05
        elif 20 <= hour <= 24:
            return 0.95
        else:
            return 0.9

    def _forecast_demand_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple demand level forecasting"""
        if not historical:
            return 0.5
        recent_avg = np.mean(historical[-6:]) if len(historical) >= 6 else np.mean(historical)
        noise = np.random.normal(0, 0.05)
        forecast = max(0.0, min(1.0, recent_avg + noise))
        return float(forecast)  # type: ignore[arg-type]

    def _forecast_supply_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple supply level forecasting"""
        if not historical:
            return 0.5
        recent_avg = np.mean(historical[-12:]) if len(historical) >= 12 else np.mean(historical)
        noise = np.random.normal(0, 0.02)
        forecast = max(0.0, min(1.0, recent_avg + noise))
        return float(forecast)  # type: ignore[arg-type]

    async def _calculate_time_based_price(self, base_price: float, factors: PricingFactors, config: dict[str, Any]) -> float:
        """Calculate time-based pricing with peak/off-peak adjustments"""
        hour = datetime.now(UTC).hour
        day_of_week = datetime.now(UTC).weekday()
        if 8 <= hour <= 20 and day_of_week < 5:
            time_mult = config.get("peak_hours_multiplier", 1.3)
        elif day_of_week >= 5:
            time_mult = config.get("weekend_multiplier", 0.9)
        else:
            time_mult = config.get("off_peak_multiplier", 0.8)
        price = base_price * config["base_multiplier"] * time_mult
        return max(price, self.min_price)  # type: ignore[no-any-return]

    async def _calculate_reputation_based_price(
        self, base_price: float, factors: PricingFactors, config: dict[str, Any]
    ) -> float:
        """Calculate reputation-based pricing"""
        reputation_weight = config.get("reputation_weight", 0.6)
        performance_weight = config.get("performance_weight", 0.3)
        history_weight = config.get("history_weight", 0.1)
        reputation_mult = 1.0 + (factors.provider_reputation - 1.0) * reputation_weight
        performance_mult = factors.performance_multiplier * performance_weight + 1.0 * (1 - performance_weight)
        history_mult = factors.historical_performance * history_weight + 1.0 * (1 - history_weight)
        price = base_price * config["base_multiplier"] * reputation_mult * performance_mult * history_mult
        return max(price, self.min_price)  # type: ignore[no-any-return]

    async def _calculate_multi_factor_price(self, base_price: float, factors: PricingFactors, config: dict[str, Any]) -> float:
        """Calculate multi-factor pricing with weighted combination"""
        demand_weight = config.get("demand_weight", 0.25)
        supply_weight = config.get("supply_weight", 0.2)
        time_weight = config.get("time_weight", 0.15)
        reputation_weight = config.get("reputation_weight", 0.15)
        competition_weight = config.get("competition_weight", 0.15)
        regional_weight = config.get("regional_weight", 0.1)
        demand_mult = 1.0 + (factors.demand_multiplier - 1.0) * demand_weight
        supply_mult = 1.0 + (factors.supply_multiplier - 1.0) * supply_weight
        time_mult = 1.0 + (factors.time_multiplier - 1.0) * time_weight
        reputation_mult = 1.0 + (factors.provider_reputation - 1.0) * reputation_weight
        competition_mult = 1.0 + (factors.competition_multiplier - 1.0) * competition_weight
        regional_mult = 1.0 + (factors.regional_multiplier - 1.0) * regional_weight
        price = base_price * config["base_multiplier"]
        price *= demand_mult
        price *= supply_mult
        price *= time_mult
        price *= reputation_mult
        price *= competition_mult
        price *= regional_mult
        return max(price, self.min_price)  # type: ignore[no-any-return]

    async def _calculate_predictive_price(
        self, base_price: float, factors: PricingFactors, config: dict[str, Any], market_conditions: MarketConditions
    ) -> float:
        """Calculate predictive pricing using ML-based forecasting"""
        forecast_weight = config.get("forecast_weight", 0.5)
        current_weight = config.get("current_weight", 0.3)
        trend_weight = config.get("trend_weight", 0.2)
        ml_confidence_threshold = config.get("ml_confidence_threshold", 0.7)
        forecast_price = base_price * (1 + (factors.demand_level - 0.5) * 0.3)
        current_price = base_price * factors.demand_multiplier * factors.supply_multiplier
        if market_conditions.price_volatility > 0.2:
            trend_adjustment = 1.05 if market_conditions.demand_level > 0.6 else 0.95
        else:
            trend_adjustment = 1.0
        confidence = factors.confidence_score
        if confidence >= ml_confidence_threshold:
            weighted_price = (
                forecast_price * forecast_weight
                + current_price * current_weight
                + base_price * trend_weight * trend_adjustment
            )
        else:
            weighted_price = (
                forecast_price * forecast_weight * 0.5
                + current_price * (current_weight + forecast_weight * 0.5)
                + base_price * trend_weight * trend_adjustment
            )
        price = weighted_price * config["base_multiplier"]
        return max(price, self.min_price)  # type: ignore[no-any-return]
