"""Pricing-factor and strategy-price cluster for DynamicPricingEngine.

Methods moved verbatim from ``dynamic_pricing.py`` (issue #1860, phase 6 band
split); ``DynamicPricingEngine`` inherits this mixin so every ``self.*`` call
keeps resolving. Helpers shared with the sibling modules live in
``dynamic_pricing_common`` and the data types in ``dynamic_pricing_model``.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from .dynamic_pricing_common import _D, np
from .dynamic_pricing_model import (
    MarketConditions,
    PriceConstraints,
    PricePoint,
    PriceTrend,
    PricingFactors,
    PricingStrategy,
    ResourceType,
)

logger = get_logger(__name__)


class _PricingFactorsMixin:
    # Attributes are assigned in DynamicPricingEngine.__init__; declared here
    # for mypy (same pattern as the market-service mixins).
    config: dict[str, Any]
    pricing_history: dict[str, list[PricePoint]]
    provider_strategies: dict[str, PricingStrategy]
    price_constraints: dict[str, PriceConstraints]
    strategy_configs: dict[PricingStrategy, dict[str, Any]]
    min_price: Decimal
    max_price: Decimal
    circuit_breakers: dict[str, bool]
    circuit_breaker_threshold: float

    if TYPE_CHECKING:
        # Provided by _PricingMarketMixin via DynamicPricingEngine MRO.
        async def _reset_circuit_breaker(self, resource_id: str, delay: int) -> None: ...

    async def _calculate_pricing_factors(
        self,
        resource_id: str,
        resource_type: ResourceType,
        base_price: Decimal,
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
        self, base_price: Decimal, factors: PricingFactors, strategy: PricingStrategy, market_conditions: MarketConditions
    ) -> Decimal:
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
        price *= _D(config["base_multiplier"])
        demand_adjustment = (factors.demand_level - 0.5) * config["demand_sensitivity"]
        price *= _D(1 + demand_adjustment)
        if market_conditions.competitor_prices:
            # `price` itself stays Decimal through _D() below; this is only its divisor.
            # not-money: consumed only to form competition_ratio, a dimensionless factor
            avg_competitor_price = float(np.mean([float(p) for p in market_conditions.competitor_prices]))
            competition_ratio = avg_competitor_price / float(base_price)
            competition_adjustment = (competition_ratio - 1) * config["competition_weight"]
            price = price * _D(1 + competition_adjustment)
        price *= factors.time_multiplier
        price *= factors.performance_multiplier
        price *= factors.sentiment_multiplier
        price *= factors.regional_multiplier
        if config["growth_priority"] > 0.5:
            price *= _D(1 - (config["growth_priority"] - 0.5) * 0.2)
        return max(price, self.min_price)

    async def _apply_constraints_and_risk(
        self, resource_id: str, price: Decimal, constraints: PriceConstraints | None, factors: PricingFactors
    ) -> Decimal:
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
            max_change = last_price * Decimal("0.5")
            if abs(price - last_price) > max_change:
                price = last_price + (max_change if price > last_price else -max_change)
                logger.info("Applied max change constraint for %s", resource_id)
        if factors.market_volatility > self.circuit_breaker_threshold:
            self.circuit_breakers[resource_id] = True
            logger.warning("Triggered circuit breaker for %s due to high volatility", resource_id)
            create_task_with_logging(self._reset_circuit_breaker(resource_id, 3600), name="reset_circuit_breaker")
        return price

    def _calculate_demand_multiplier(self, demand_level: float, strategy: PricingStrategy) -> Decimal:
        """Calculate demand-based price multiplier"""
        if demand_level > 0.8:
            base_multiplier = 1.0 + (demand_level - 0.8) * 2.5
        elif demand_level > 0.5:
            base_multiplier = 1.0 + (demand_level - 0.5) * 0.5
        else:
            base_multiplier = 0.8 + demand_level * 0.4
        # #1363: clamp like the supply multiplier — the low-band formula goes
        # negative for demand_level < -2.0, and an invalid (negative) factor
        # must never reach price computation.
        if strategy == PricingStrategy.AGGRESSIVE_GROWTH:
            result = base_multiplier * 0.9
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            result = base_multiplier * 1.3
        else:
            result = base_multiplier
        return _D(max(0.5, min(2.0, result)))

    def _calculate_supply_multiplier(self, supply_level: float, strategy: PricingStrategy) -> Decimal:
        """Calculate supply-based price multiplier"""
        if supply_level < 0.3:
            base_multiplier = 1.0 + (0.3 - supply_level) * 1.5
        elif supply_level < 0.7:
            base_multiplier = 1.0 - (supply_level - 0.3) * 0.3
        else:
            base_multiplier = 0.9 - (supply_level - 0.7) * 0.3
        return _D(max(0.5, min(2.0, base_multiplier)))

    def _calculate_time_multiplier(self) -> Decimal:
        """Calculate time-based price multiplier"""
        hour = datetime.now(UTC).hour
        day_of_week = datetime.now(UTC).weekday()
        if 8 <= hour <= 20 and day_of_week < 5:
            return Decimal("1.2")
        elif 20 <= hour <= 24 or 0 <= hour <= 2:
            return Decimal("1.1")
        elif 2 <= hour <= 6:
            return Decimal("0.8")
        elif day_of_week >= 5:
            return Decimal("1.15")
        else:
            return Decimal("1.0")

    async def _calculate_performance_multiplier(self, resource_id: str) -> Decimal:
        """Calculate performance-based multiplier"""
        if resource_id in self.pricing_history and len(self.pricing_history[resource_id]) > 10:
            recent_prices = [
                float(p.price) for p in self.pricing_history[resource_id][-10:]
            ]  # not-money: strategy/score computation, not a settled amount
            price_variance = np.var(recent_prices)
            avg_price = np.mean(recent_prices)
            if price_variance < avg_price * 0.01:
                return Decimal("1.1")
            elif price_variance < avg_price * 0.05:
                return Decimal("1.05")
            else:
                return Decimal("0.95")
        else:
            return Decimal("1.0")

    def _calculate_competition_multiplier(
        self, base_price: Decimal, competitor_prices: list[Decimal], strategy: PricingStrategy
    ) -> Decimal:
        """Calculate competition-based multiplier"""
        if not competitor_prices:
            return Decimal("1.0")
        # not-money: consumed only to form price_ratio; this function returns a multiplier
        avg_competitor_price = float(np.mean([float(p) for p in competitor_prices]))
        price_ratio = float(base_price) / avg_competitor_price
        if strategy == PricingStrategy.COMPETITIVE_RESPONSE:
            if price_ratio > 1.1:
                return Decimal("0.9")
            elif price_ratio < 0.9:
                return Decimal("1.05")
            else:
                return Decimal("1.0")
        elif strategy == PricingStrategy.PROFIT_MAXIMIZATION:
            return _D(1.0 + (price_ratio - 1) * 0.3)
        else:
            return _D(1.0 + (price_ratio - 1) * 0.5)

    def _calculate_sentiment_multiplier(self, sentiment: float) -> Decimal:
        """Calculate market sentiment multiplier"""
        if sentiment > 0.3:
            return Decimal("1.1")
        elif sentiment < -0.3:
            return Decimal("0.9")
        else:
            return Decimal("1.0")

    def _calculate_regional_multiplier(self, region: str, resource_type: ResourceType) -> Decimal:
        """Calculate regional price multiplier"""
        regional_adjustments = {
            "us_west": {"gpu": Decimal("1.1"), "service": Decimal("1.05"), "storage": Decimal("1.0")},
            "us_east": {"gpu": Decimal("1.2"), "service": Decimal("1.1"), "storage": Decimal("1.05")},
            "europe": {"gpu": Decimal("1.15"), "service": Decimal("1.08"), "storage": Decimal("1.02")},
            "asia": {"gpu": Decimal("0.9"), "service": Decimal("0.95"), "storage": Decimal("0.9")},
            "global": {"gpu": Decimal("1.0"), "service": Decimal("1.0"), "storage": Decimal("1.0")},
        }
        return regional_adjustments.get(region, {}).get(resource_type.value, Decimal("1.0"))

    async def _determine_price_trend(self, resource_id: str, current_price: Decimal) -> PriceTrend:
        """Determine price trend based on historical data"""
        if resource_id not in self.pricing_history or len(self.pricing_history[resource_id]) < 5:
            return PriceTrend.STABLE
        recent_prices = [
            float(p.price) for p in self.pricing_history[resource_id][-10:]
        ]  # not-money: strategy/score computation, not a settled amount
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

    @staticmethod
    def _demand_supply_notes(factors: PricingFactors) -> list[str]:
        """Reasoning notes derived from demand and supply levels."""
        notes = []
        if factors.demand_level > 0.8:
            notes.append("High demand increases prices")
        elif factors.demand_level < 0.3:
            notes.append("Low demand allows competitive pricing")
        if factors.supply_level < 0.3:
            notes.append("Limited supply justifies premium pricing")
        elif factors.supply_level > 0.8:
            notes.append("High supply enables competitive pricing")
        return notes

    @staticmethod
    def _adjustment_notes(factors: PricingFactors) -> list[str]:
        """Reasoning notes for time-of-day, performance, and competition."""
        notes = []
        hour = datetime.now(UTC).hour
        if 8 <= hour <= 20:
            notes.append("Business hours premium applied")
        elif 2 <= hour <= 6:
            notes.append("Late night discount applied")
        if factors.performance_multiplier > 1.05:
            notes.append("High performance justifies premium")
        elif factors.performance_multiplier < 0.95:
            notes.append("Performance issues require discount")
        if factors.competition_multiplier != 1.0:
            if factors.competition_multiplier < 1.0:
                notes.append("Competitive pricing applied")
            else:
                notes.append("Premium pricing over competitors")
        return notes

    async def _generate_pricing_reasoning(
        self, factors: PricingFactors, strategy: PricingStrategy, market_conditions: MarketConditions, trend: PriceTrend
    ) -> list[str]:
        """Generate reasoning for pricing decisions"""
        reasoning = []
        reasoning.append(f"Strategy: {strategy.value} applied")
        reasoning.extend(self._demand_supply_notes(factors))
        reasoning.extend(self._adjustment_notes(factors))
        reasoning.append(f"Price trend: {trend.value}")
        return reasoning

    async def _calculate_confidence_score(self, factors: PricingFactors, market_conditions: MarketConditions) -> float:
        """Calculate confidence score for pricing decision"""
        confidence = 0.8
        stability_factor = 1.0 - market_conditions.price_volatility
        confidence *= stability_factor
        data_factor = min(1.0, len(market_conditions.competitor_prices) / 5)
        confidence = confidence * 0.7 + data_factor * 0.3
        if abs(float(factors.demand_multiplier) - 1.0) > 1.5:
            confidence *= 0.9
        if abs(float(factors.supply_multiplier) - 1.0) > 1.0:
            confidence *= 0.9
        return max(0.3, min(0.95, confidence))

    async def _calculate_time_based_price(
        self, base_price: Decimal, factors: PricingFactors, config: dict[str, Any]
    ) -> Decimal:
        """Calculate time-based pricing with peak/off-peak adjustments"""
        hour = datetime.now(UTC).hour
        day_of_week = datetime.now(UTC).weekday()
        if 8 <= hour <= 20 and day_of_week < 5:
            time_mult = config.get("peak_hours_multiplier", 1.3)
        elif day_of_week >= 5:
            time_mult = config.get("weekend_multiplier", 0.9)
        else:
            time_mult = config.get("off_peak_multiplier", 0.8)
        price = base_price * _D(config["base_multiplier"]) * _D(time_mult)
        return max(price, self.min_price)

    async def _calculate_reputation_based_price(
        self, base_price: Decimal, factors: PricingFactors, config: dict[str, Any]
    ) -> Decimal:
        """Calculate reputation-based pricing"""
        reputation_weight = config.get("reputation_weight", 0.6)
        performance_weight = config.get("performance_weight", 0.3)
        history_weight = config.get("history_weight", 0.1)
        reputation_mult = 1.0 + (factors.provider_reputation - 1.0) * reputation_weight
        performance_mult = float(factors.performance_multiplier) * performance_weight + 1.0 * (1 - performance_weight)
        history_mult = factors.historical_performance * history_weight + 1.0 * (1 - history_weight)
        price = base_price * _D(config["base_multiplier"]) * _D(reputation_mult) * _D(performance_mult) * _D(history_mult)
        return max(price, self.min_price)

    async def _calculate_multi_factor_price(
        self, base_price: Decimal, factors: PricingFactors, config: dict[str, Any]
    ) -> Decimal:
        """Calculate multi-factor pricing with weighted combination"""
        demand_weight = config.get("demand_weight", 0.25)
        supply_weight = config.get("supply_weight", 0.2)
        time_weight = config.get("time_weight", 0.15)
        reputation_weight = config.get("reputation_weight", 0.15)
        competition_weight = config.get("competition_weight", 0.15)
        regional_weight = config.get("regional_weight", 0.1)
        demand_mult = Decimal(1) + (factors.demand_multiplier - Decimal(1)) * _D(demand_weight)
        supply_mult = Decimal(1) + (factors.supply_multiplier - Decimal(1)) * _D(supply_weight)
        time_mult = Decimal(1) + (factors.time_multiplier - Decimal(1)) * _D(time_weight)
        reputation_mult = Decimal(1) + (_D(factors.provider_reputation) - Decimal(1)) * _D(reputation_weight)
        competition_mult = Decimal(1) + (factors.competition_multiplier - Decimal(1)) * _D(competition_weight)
        regional_mult = Decimal(1) + (factors.regional_multiplier - Decimal(1)) * _D(regional_weight)
        price = base_price * _D(config["base_multiplier"])
        price *= demand_mult
        price *= supply_mult
        price *= time_mult
        price *= reputation_mult
        price *= competition_mult
        price *= regional_mult
        return max(price, self.min_price)

    async def _calculate_predictive_price(
        self, base_price: Decimal, factors: PricingFactors, config: dict[str, Any], market_conditions: MarketConditions
    ) -> Decimal:
        """Calculate predictive pricing using ML-based forecasting"""
        forecast_weight = config.get("forecast_weight", 0.5)
        current_weight = config.get("current_weight", 0.3)
        trend_weight = config.get("trend_weight", 0.2)
        ml_confidence_threshold = config.get("ml_confidence_threshold", 0.7)
        forecast_price = base_price * (
            Decimal(1) + _D(factors.demand_level - 0.5) * Decimal("0.3")
        )  # not-money: strategy/score computation, not a settled amount
        current_price = base_price * factors.demand_multiplier * factors.supply_multiplier
        if market_conditions.price_volatility > 0.2:
            trend_adjustment = Decimal("1.05") if market_conditions.demand_level > 0.6 else Decimal("0.95")
        else:
            trend_adjustment = Decimal(1)
        confidence = factors.confidence_score
        if confidence >= ml_confidence_threshold:
            weighted_price = (
                forecast_price * _D(forecast_weight)
                + current_price * _D(current_weight)
                + base_price * _D(trend_weight) * trend_adjustment
            )
        else:
            weighted_price = (  # not-money: strategy/score computation, not a settled amount
                forecast_price * _D(forecast_weight) * Decimal("0.5")
                + current_price * _D(current_weight + forecast_weight * 0.5)
                + base_price * _D(trend_weight) * trend_adjustment
            )
        price = weighted_price * _D(config["base_multiplier"])
        return max(price, self.min_price)
