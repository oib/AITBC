"""
Dynamic Pricing Engine for AITBC Marketplace
Implements sophisticated pricing algorithms based on real-time market conditions
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np

from aitbc import get_logger

logger = get_logger(__name__)


class PricingStrategy(StrEnum):
    """Dynamic pricing strategy types"""

    AGGRESSIVE_GROWTH = "aggressive_growth"
    PROFIT_MAXIMIZATION = "profit_maximization"
    MARKET_BALANCE = "market_balance"
    COMPETITIVE_RESPONSE = "competitive_response"
    DEMAND_ELASTICITY = "demand_elasticity"


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
    demand_multiplier: float = 1.0  # 0.5 - 3.0
    supply_multiplier: float = 1.0  # 0.8 - 2.5
    time_multiplier: float = 1.0  # 0.7 - 1.5
    performance_multiplier: float = 1.0  # 0.9 - 1.3
    competition_multiplier: float = 1.0  # 0.8 - 1.4
    sentiment_multiplier: float = 1.0  # 0.9 - 1.2
    regional_multiplier: float = 1.0  # 0.8 - 1.3

    # Confidence and risk factors
    confidence_score: float = 0.8
    risk_adjustment: float = 0.0

    # Market conditions
    demand_level: float = 0.5
    supply_level: float = 0.5
    market_volatility: float = 0.1

    # Provider-specific factors
    provider_reputation: float = 1.0
    utilization_rate: float = 0.5
    historical_performance: float = 1.0


@dataclass
class PriceConstraints:
    """Constraints for pricing calculations"""

    min_price: float | None = None
    max_price: float | None = None
    max_change_percent: float = 0.5  # Maximum 50% change per update
    min_change_interval: int = 300  # Minimum 5 minutes between changes
    strategy_lock_period: int = 3600  # 1 hour strategy lock


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
    market_sentiment: float = 0.0  # -1 to 1
    timestamp: datetime = field(default_factory=datetime.utcnow)


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

        # Strategy configuration
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
        }

        # Pricing parameters
        self.min_price = config.get("min_price", 0.001)
        self.max_price = config.get("max_price", 1000.0)
        self.update_interval = config.get("update_interval", 300)  # 5 minutes
        self.forecast_horizon = config.get("forecast_horizon", 72)  # 72 hours

        # Risk management
        self.max_volatility_threshold = config.get("max_volatility_threshold", 0.3)
        self.circuit_breaker_threshold = config.get("circuit_breaker_threshold", 0.5)
        self.circuit_breakers: dict[str, bool] = {}

    async def initialize(self):
        """Initialize the dynamic pricing engine"""
        logger.info("Initializing Dynamic Pricing Engine")

        # Load historical pricing data
        await self._load_pricing_history()

        # Load provider strategies
        await self._load_provider_strategies()

        # Start background tasks
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
            # Get or determine strategy
            if strategy is None:
                strategy = self.provider_strategies.get(resource_id, PricingStrategy.MARKET_BALANCE)

            # Get current market conditions
            market_conditions = await self._get_market_conditions(resource_type, region)

            # Calculate pricing factors
            factors = await self._calculate_pricing_factors(
                resource_id, resource_type, base_price, strategy, market_conditions
            )

            # Apply strategy-specific calculations
            strategy_price = await self._apply_strategy_pricing(base_price, factors, strategy, market_conditions)

            # Apply constraints and risk management
            final_price = await self._apply_constraints_and_risk(resource_id, strategy_price, constraints, factors)

            # Determine price trend
            price_trend = await self._determine_price_trend(resource_id, final_price)

            # Generate reasoning
            reasoning = await self._generate_pricing_reasoning(factors, strategy, market_conditions, price_trend)

            # Calculate confidence score
            confidence = await self._calculate_confidence_score(factors, market_conditions)

            # Schedule next update
            next_update = datetime.utcnow() + timedelta(seconds=self.update_interval)

            # Store price point
            await self._store_price_point(resource_id, final_price, factors, strategy)

            # Create result
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

            logger.info(f"Calculated dynamic price for {resource_id}: {final_price:.6f} (was {base_price:.6f})")
            return result

        except Exception as e:
            logger.error(f"Failed to calculate dynamic price for {resource_id}: {e}")
            raise

    async def get_price_forecast(self, resource_id: str, hours_ahead: int = 24) -> list[PricePoint]:
        """Generate price forecast for the specified horizon"""

        try:
            if resource_id not in self.pricing_history:
                return []

            historical_data = self.pricing_history[resource_id]
            if len(historical_data) < 24:  # Need at least 24 data points
                return []

            # Extract price series
            prices = [point.price for point in historical_data[-48:]]  # Last 48 points
            demand_levels = [point.demand_level for point in historical_data[-48:]]
            supply_levels = [point.supply_level for point in historical_data[-48:]]

            # Generate forecast using time series analysis
            forecast_points = []

            for hour in range(1, hours_ahead + 1):
                # Simple linear trend with seasonal adjustment
                price_trend = self._calculate_price_trend(prices[-12:])  # Last 12 points
                seasonal_factor = self._calculate_seasonal_factor(hour)
                demand_forecast = self._forecast_demand_level(demand_levels, hour)
                supply_forecast = self._forecast_supply_level(supply_levels, hour)

                # Calculate forecasted price
                base_forecast = prices[-1] + (price_trend * hour)
                seasonal_adjusted = base_forecast * seasonal_factor
                demand_adjusted = seasonal_adjusted * (1 + (demand_forecast - 0.5) * 0.3)
                supply_adjusted = demand_adjusted * (1 + (0.5 - supply_forecast) * 0.2)

                forecast_price = max(self.min_price, min(supply_adjusted, self.max_price))

                # Calculate confidence (decreases with time)
                confidence = max(0.3, 0.9 - (hour / hours_ahead) * 0.6)

                forecast_point = PricePoint(
                    timestamp=datetime.utcnow() + timedelta(hours=hour),
                    price=forecast_price,
                    demand_level=demand_forecast,
                    supply_level=supply_forecast,
                    confidence=confidence,
                    strategy_used="forecast",
                )

                forecast_points.append(forecast_point)

            return forecast_points

        except Exception as e:
            logger.error(f"Failed to generate price forecast for {resource_id}: {e}")
            return []

    async def set_provider_strategy(
        self, provider_id: str, strategy: PricingStrategy, constraints: PriceConstraints | None = None
    ) -> bool:
        """Set pricing strategy for a provider"""

        try:
            self.provider_strategies[provider_id] = strategy
            if constraints:
                self.price_constraints[provider_id] = constraints

            logger.info(f"Set strategy {strategy.value} for provider {provider_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to set strategy for provider {provider_id}: {e}")
            return False

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

        # Demand multiplier based on market conditions
        factors.demand_multiplier = self._calculate_demand_multiplier(market_conditions.demand_level, strategy)

        # Supply multiplier based on availability
        factors.supply_multiplier = self._calculate_supply_multiplier(market_conditions.supply_level, strategy)

        # Time-based multiplier (peak/off-peak)
        factors.time_multiplier = self._calculate_time_multiplier()

        # Performance multiplier based on provider history
        factors.performance_multiplier = await self._calculate_performance_multiplier(resource_id)

        # Competition multiplier based on competitor prices
        factors.competition_multiplier = self._calculate_competition_multiplier(
            base_price, market_conditions.competitor_prices, strategy
        )

        # Market sentiment multiplier
        factors.sentiment_multiplier = self._calculate_sentiment_multiplier(market_conditions.market_sentiment)

        # Regional multiplier
        factors.regional_multiplier = self._calculate_regional_multiplier(market_conditions.region, resource_type)

        # Update market condition fields
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

        # Apply base strategy multiplier
        price *= config["base_multiplier"]

        # Apply demand sensitivity
        demand_adjustment = (factors.demand_level - 0.5) * config["demand_sensitivity"]
        price *= 1 + demand_adjustment

        # Apply competition adjustment
        if market_conditions.competitor_prices:
            avg_competitor_price = np.mean(market_conditions.competitor_prices)
            competition_ratio = avg_competitor_price / base_price
            competition_adjustment = (competition_ratio - 1) * config["competition_weight"]
            price *= 1 + competition_adjustment

        # Apply individual multipliers
        price *= factors.time_multiplier
        price *= factors.performance_multiplier
        price *= factors.sentiment_multiplier
        price *= factors.regional_multiplier

        # Apply growth priority adjustment
        if config["growth_priority"] > 0.5:
            price *= 1 - (config["growth_priority"] - 0.5) * 0.2  # Discount for growth

        return max(price, self.min_price)

    async def _apply_constraints_and_risk(
        self, resource_id: str, price: float, constraints: PriceConstraints | None, factors: PricingFactors
    ) -> float:
        """Apply pricing constraints and risk management"""

        # Check if circuit breaker is active
        if self.circuit_breakers.get(resource_id, False):
            logger.warning(f"Circuit breaker active for {resource_id}, using last price")
            if resource_id in self.pricing_history and self.pricing_history[resource_id]:
                return self.pricing_history[resource_id][-1].price

        # Apply provider-specific constraints
        if constraints:
            if constraints.min_price:
                price = max(price, constraints.min_price)
            if constraints.max_price:
                price = min(price, constraints.max_price)

        # Apply global constraints
        price = max(price, self.min_price)
        price = min(price, self.max_price)

        # Apply maximum change constraint
        if resource_id in self.pricing_history and self.pricing_history[resource_id]:
            last_price = self.pricing_history[resource_id][-1].price
            max_change = last_price * 0.5  # 50% max change
            if abs(price - last_price) > max_change:
                price = last_price + (max_change if price > last_price else -max_change)
                logger.info(f"Applied max change constraint for {resource_id}")

        # Check for high volatility and trigger circuit breaker if needed
        if factors.market_volatility > self.circuit_breaker_threshold:
            self.circuit_breakers[resource_id] = True
            logger.warning(f"Triggered circuit breaker for {resource_id} due to high volatility")
            # Schedule circuit breaker reset
            asyncio.create_task(self._reset_circuit_breaker(resource_id, 3600))  # 1 hour

        return price

    def _calculate_demand_multiplier(self, demand_level: float, strategy: PricingStrategy) -> float:
        """Calculate demand-based price multiplier"""

        # Base demand curve
        if demand_level > 0.8:
            base_multiplier = 1.0 + (demand_level - 0.8) * 2.5  # High demand
        elif demand_level > 0.5:
            base_multiplier = 1.0 + (demand_level - 0.5) * 0.5  # Normal demand
        else:
            base_multiplier = 0.8 + (demand_level * 0.4)  # Low demand

        # Strategy adjustment
        if strategy == PricingStrategy.AGGRESSIVE_GROWTH:
            return base_multiplier * 0.9  # Discount for growth
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            return base_multiplier * 1.3  # Premium for profit
        else:
            return base_multiplier

    def _calculate_supply_multiplier(self, supply_level: float, strategy: PricingStrategy) -> float:
        """Calculate supply-based price multiplier"""

        # Inverse supply curve (low supply = higher prices)
        if supply_level < 0.3:
            base_multiplier = 1.0 + (0.3 - supply_level) * 1.5  # Low supply
        elif supply_level < 0.7:
            base_multiplier = 1.0 - (supply_level - 0.3) * 0.3  # Normal supply
        else:
            base_multiplier = 0.9 - (supply_level - 0.7) * 0.3  # High supply

        return max(0.5, min(2.0, base_multiplier))

    def _calculate_time_multiplier(self) -> float:
        """Calculate time-based price multiplier"""

        hour = datetime.utcnow().hour
        day_of_week = datetime.utcnow().weekday()

        # Business hours premium (8 AM - 8 PM, Monday-Friday)
        if 8 <= hour <= 20 and day_of_week < 5:
            return 1.2
        # Evening premium (8 PM - 12 AM)
        elif 20 <= hour <= 24 or 0 <= hour <= 2:
            return 1.1
        # Late night discount (2 AM - 6 AM)
        elif 2 <= hour <= 6:
            return 0.8
        # Weekend premium
        elif day_of_week >= 5:
            return 1.15
        else:
            return 1.0

    async def _calculate_performance_multiplier(self, resource_id: str) -> float:
        """Calculate performance-based multiplier"""

        # In a real implementation, this would fetch from performance metrics
        # For now, return a default based on historical data
        if resource_id in self.pricing_history and len(self.pricing_history[resource_id]) > 10:
            # Simple performance calculation based on consistency
            recent_prices = [p.price for p in self.pricing_history[resource_id][-10:]]
            price_variance = np.var(recent_prices)
            avg_price = np.mean(recent_prices)

            # Lower variance = higher performance multiplier
            if price_variance < (avg_price * 0.01):
                return 1.1  # High consistency
            elif price_variance < (avg_price * 0.05):
                return 1.05  # Good consistency
            else:
                return 0.95  # Low consistency
        else:
            return 1.0  # Default for new resources

    def _calculate_competition_multiplier(
        self, base_price: float, competitor_prices: list[float], strategy: PricingStrategy
    ) -> float:
        """Calculate competition-based multiplier"""

        if not competitor_prices:
            return 1.0

        avg_competitor_price = np.mean(competitor_prices)
        price_ratio = base_price / avg_competitor_price

        # Strategy-specific competition response
        if strategy == PricingStrategy.COMPETITIVE_RESPONSE:
            if price_ratio > 1.1:  # We're more expensive
                return 0.9  # Discount to compete
            elif price_ratio < 0.9:  # We're cheaper
                return 1.05  # Slight premium
            else:
                return 1.0
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            return 1.0 + (price_ratio - 1) * 0.3  # Less sensitive to competition
        else:
            return 1.0 + (price_ratio - 1) * 0.5  # Moderate competition sensitivity

    def _calculate_sentiment_multiplier(self, sentiment: float) -> float:
        """Calculate market sentiment multiplier"""

        # Sentiment ranges from -1 (negative) to 1 (positive)
        if sentiment > 0.3:
            return 1.1  # Positive sentiment premium
        elif sentiment < -0.3:
            return 0.9  # Negative sentiment discount
        else:
            return 1.0  # Neutral sentiment

    def _calculate_regional_multiplier(self, region: str, resource_type: ResourceType) -> float:
        """Calculate regional price multiplier"""

        # Regional pricing adjustments
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

        # Calculate trend
        if len(recent_prices) >= 3:
            recent_avg = np.mean(recent_prices[-3:])
            older_avg = np.mean(recent_prices[-6:-3]) if len(recent_prices) >= 6 else np.mean(recent_prices[:-3])

            change = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

            # Calculate volatility
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

        # Strategy reasoning
        reasoning.append(f"Strategy: {strategy.value} applied")

        # Market conditions
        if factors.demand_level > 0.8:
            reasoning.append("High demand increases prices")
        elif factors.demand_level < 0.3:
            reasoning.append("Low demand allows competitive pricing")

        if factors.supply_level < 0.3:
            reasoning.append("Limited supply justifies premium pricing")
        elif factors.supply_level > 0.8:
            reasoning.append("High supply enables competitive pricing")

        # Time-based reasoning
        hour = datetime.utcnow().hour
        if 8 <= hour <= 20:
            reasoning.append("Business hours premium applied")
        elif 2 <= hour <= 6:
            reasoning.append("Late night discount applied")

        # Performance reasoning
        if factors.performance_multiplier > 1.05:
            reasoning.append("High performance justifies premium")
        elif factors.performance_multiplier < 0.95:
            reasoning.append("Performance issues require discount")

        # Competition reasoning
        if factors.competition_multiplier != 1.0:
            if factors.competition_multiplier < 1.0:
                reasoning.append("Competitive pricing applied")
            else:
                reasoning.append("Premium pricing over competitors")

        # Trend reasoning
        reasoning.append(f"Price trend: {trend.value}")

        return reasoning

    async def _calculate_confidence_score(self, factors: PricingFactors, market_conditions: MarketConditions) -> float:
        """Calculate confidence score for pricing decision"""

        confidence = 0.8  # Base confidence

        # Market stability factor
        stability_factor = 1.0 - market_conditions.price_volatility
        confidence *= stability_factor

        # Data availability factor
        data_factor = min(1.0, len(market_conditions.competitor_prices) / 5)
        confidence = confidence * 0.7 + data_factor * 0.3

        # Factor consistency
        if abs(factors.demand_multiplier - 1.0) > 1.5:
            confidence *= 0.9  # Extreme demand adjustments reduce confidence

        if abs(factors.supply_multiplier - 1.0) > 1.0:
            confidence *= 0.9  # Extreme supply adjustments reduce confidence

        return max(0.3, min(0.95, confidence))

    async def _store_price_point(self, resource_id: str, price: float, factors: PricingFactors, strategy: PricingStrategy):
        """Store price point in history"""

        if resource_id not in self.pricing_history:
            self.pricing_history[resource_id] = []

        price_point = PricePoint(
            timestamp=datetime.utcnow(),
            price=price,
            demand_level=factors.demand_level,
            supply_level=factors.supply_level,
            confidence=factors.confidence_score,
            strategy_used=strategy.value,
        )

        self.pricing_history[resource_id].append(price_point)

        # Keep only last 1000 points
        if len(self.pricing_history[resource_id]) > 1000:
            self.pricing_history[resource_id] = self.pricing_history[resource_id][-1000:]

    async def _get_market_conditions(self, resource_type: ResourceType, region: str) -> MarketConditions:
        """Get current market conditions"""

        cache_key = f"{region}_{resource_type.value}"

        if cache_key in self.market_conditions_cache:
            cached = self.market_conditions_cache[cache_key]
            # Use cached data if less than 5 minutes old
            if (datetime.utcnow() - cached.timestamp).total_seconds() < 300:
                return cached

        # In a real implementation, this would fetch from market data sources
        # For now, return simulated data
        conditions = MarketConditions(
            region=region,
            resource_type=resource_type,
            demand_level=0.6 + np.random.normal(0, 0.1),
            supply_level=0.7 + np.random.normal(0, 0.1),
            average_price=0.05 + np.random.normal(0, 0.01),
            price_volatility=0.1 + np.random.normal(0, 0.05),
            utilization_rate=0.65 + np.random.normal(0, 0.1),
            competitor_prices=[0.045, 0.055, 0.048, 0.052],  # Simulated competitor prices
            market_sentiment=np.random.normal(0.1, 0.2),
        )

        # Cache the conditions
        self.market_conditions_cache[cache_key] = conditions

        return conditions

    async def _load_pricing_history(self):
        """Load historical pricing data"""
        # In a real implementation, this would load from database
        pass

    async def _load_provider_strategies(self):
        """Load provider strategies from storage"""
        # In a real implementation, this would load from database
        pass

    async def _update_market_conditions(self):
        """Background task to update market conditions"""
        while True:
            try:
                # Clear cache to force refresh
                self.market_conditions_cache.clear()
                await asyncio.sleep(300)  # Update every 5 minutes
            except Exception as e:
                logger.error(f"Error updating market conditions: {e}")
                await asyncio.sleep(60)

    async def _monitor_price_volatility(self):
        """Background task to monitor price volatility"""
        while True:
            try:
                for resource_id, history in self.pricing_history.items():
                    if len(history) >= 10:
                        recent_prices = [p.price for p in history[-10:]]
                        volatility = np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0

                        if volatility > self.max_volatility_threshold:
                            logger.warning(f"High volatility detected for {resource_id}: {volatility:.3f}")

                await asyncio.sleep(600)  # Check every 10 minutes
            except Exception as e:
                logger.error(f"Error monitoring volatility: {e}")
                await asyncio.sleep(120)

    async def _optimize_strategies(self):
        """Background task to optimize pricing strategies"""
        while True:
            try:
                # Analyze strategy performance and recommend optimizations
                await asyncio.sleep(3600)  # Optimize every hour
            except Exception as e:
                logger.error(f"Error optimizing strategies: {e}")
                await asyncio.sleep(300)

    async def _reset_circuit_breaker(self, resource_id: str, delay: int):
        """Reset circuit breaker after delay"""
        await asyncio.sleep(delay)
        self.circuit_breakers[resource_id] = False
        logger.info(f"Reset circuit breaker for {resource_id}")

    def _calculate_price_trend(self, prices: list[float]) -> float:
        """Calculate simple price trend"""
        if len(prices) < 2:
            return 0.0

        # Simple linear regression
        x = np.arange(len(prices))
        y = np.array(prices)

        # Calculate slope
        slope = np.polyfit(x, y, 1)[0]
        return slope

    def _calculate_seasonal_factor(self, hour: int) -> float:
        """Calculate seasonal adjustment factor"""
        # Simple daily seasonality pattern
        if 6 <= hour <= 10:  # Morning ramp
            return 1.05
        elif 10 <= hour <= 16:  # Business peak
            return 1.1
        elif 16 <= hour <= 20:  # Evening ramp
            return 1.05
        elif 20 <= hour <= 24:  # Night
            return 0.95
        else:  # Late night
            return 0.9

    def _forecast_demand_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple demand level forecasting"""
        if not historical:
            return 0.5

        # Use recent average with some noise
        recent_avg = np.mean(historical[-6:]) if len(historical) >= 6 else np.mean(historical)

        # Add some prediction uncertainty
        noise = np.random.normal(0, 0.05)
        forecast = max(0.0, min(1.0, recent_avg + noise))

        return forecast

    def _forecast_supply_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple supply level forecasting"""
        if not historical:
            return 0.5

        # Supply is usually more stable than demand
        recent_avg = np.mean(historical[-12:]) if len(historical) >= 12 else np.mean(historical)

        # Add small prediction uncertainty
        noise = np.random.normal(0, 0.02)
        forecast = max(0.0, min(1.0, recent_avg + noise))

        return forecast
