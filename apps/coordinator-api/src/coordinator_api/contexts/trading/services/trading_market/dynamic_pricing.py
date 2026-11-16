"""
Dynamic Pricing Engine for AITBC Market
Implements sophisticated pricing algorithms based on real-time market conditions
"""

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from .dynamic_pricing_common import (
    _D as _D,
    _OPS_ERRORS as _OPS_ERRORS,
    _serialize_decimals as _serialize_decimals,
    np as np,
)
from .dynamic_pricing_factors import _PricingFactorsMixin
from .dynamic_pricing_market import _PricingMarketMixin
from .dynamic_pricing_model import (
    MarketConditions as MarketConditions,
    PriceConstraints as PriceConstraints,
    PricePoint as PricePoint,
    PriceTrend as PriceTrend,
    PricingFactors as PricingFactors,
    PricingResult as PricingResult,
    PricingStrategy as PricingStrategy,
    ResourceType as ResourceType,
)

# Importing the pricing persistence models registers their tables with
# SQLModel.metadata so init_db()/create_all() creates them at startup. The
# full set is imported by dynamic_pricing_market.py (a sibling this module
# imports); ProviderPricingStrategy and PricingAuditLog are also used
# directly by _persist_provider_strategy below.
from ...domain.pricing_models import (
    PricingAuditLog,
    ProviderPricingStrategy,
)

logger = get_logger(__name__)


class DynamicPricingEngine(_PricingFactorsMixin, _PricingMarketMixin):
    """Core dynamic pricing engine with advanced algorithms"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.pricing_history: dict[str, list[PricePoint]] = {}
        self.market_conditions_cache: dict[str, MarketConditions] = {}
        self.provider_strategies: dict[str, PricingStrategy] = {}
        self.price_constraints: dict[str, PriceConstraints] = {}
        self._lock = asyncio.Lock()
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
        self.min_price = _D(config.get("min_price", 0.001))  # not-money: strategy/score computation, not a settled amount
        self.max_price = _D(config.get("max_price", 1000.0))  # not-money: strategy/score computation, not a settled amount
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
        create_task_with_logging(self._update_market_conditions(), name="update_market_conditions")
        create_task_with_logging(self._monitor_price_volatility(), name="monitor_price_volatility")
        create_task_with_logging(self._optimize_strategies(), name="optimize_strategies")
        logger.info("Dynamic Pricing Engine initialized")

    async def calculate_dynamic_price(
        self,
        resource_id: str,
        resource_type: ResourceType,
        base_price: Decimal,
        strategy: PricingStrategy | None = None,
        constraints: PriceConstraints | None = None,
        region: str = "global",
    ) -> PricingResult:
        """Calculate dynamic price for a resource"""
        try:
            base_price_dec = _D(base_price)
            if strategy is None:
                strategy = self.provider_strategies.get(resource_id, PricingStrategy.MARKET_BALANCE)
            market_conditions = await self._get_market_conditions(resource_type, region)
            factors = await self._calculate_pricing_factors(
                resource_id, resource_type, base_price_dec, strategy, market_conditions
            )
            strategy_price = await self._apply_strategy_pricing(base_price_dec, factors, strategy, market_conditions)
            final_price = await self._apply_constraints_and_risk(resource_id, strategy_price, constraints, factors)
            price_trend = await self._determine_price_trend(resource_id, final_price)
            reasoning = await self._generate_pricing_reasoning(factors, strategy, market_conditions, price_trend)
            confidence = await self._calculate_confidence_score(factors, market_conditions)
            next_update = datetime.now(UTC) + timedelta(seconds=self.update_interval)
            await self._store_price_point(resource_id, resource_type, final_price, factors, strategy)
            result = PricingResult(
                resource_id=resource_id,
                resource_type=resource_type,
                current_price=base_price_dec,
                recommended_price=final_price,
                price_trend=price_trend,
                confidence_score=confidence,
                factors_exposed=_serialize_decimals(asdict(factors)),
                reasoning=reasoning,
                next_update=next_update,
                strategy_used=strategy,
            )
            logger.info("Calculated dynamic price for %s: %s (was %s)", resource_id, final_price, base_price_dec)
            return result
        except _OPS_ERRORS as e:
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
            prices = [
                float(point.price) for point in historical_data[-48:]
            ]  # not-money: strategy/score computation, not a settled amount
            demand_levels = [point.demand_level for point in historical_data[-48:]]
            supply_levels = [point.supply_level for point in historical_data[-48:]]
            forecast_points = []
            for hour in range(1, hours_ahead + 1):
                price_trend = self._calculate_price_trend(prices[-12:])
                seasonal_factor = self._calculate_seasonal_factor(hour)
                demand_forecast = self._forecast_demand_level(demand_levels, hour)
                supply_forecast = self._forecast_supply_level(supply_levels, hour)
                base_forecast = prices[-1] + price_trend * hour
                seasonal_adjusted = base_forecast * float(seasonal_factor)
                demand_adjusted = seasonal_adjusted * (1 + (demand_forecast - 0.5) * 0.3)
                supply_adjusted = demand_adjusted * (1 + (0.5 - supply_forecast) * 0.2)
                forecast_price = max(
                    float(self.min_price), min(supply_adjusted, float(self.max_price))
                )  # not-money: strategy/score computation, not a settled amount
                confidence = max(0.3, 0.9 - hour / hours_ahead * 0.6)
                forecast_point = PricePoint(
                    timestamp=datetime.now(UTC) + timedelta(hours=hour),
                    price=_D(forecast_price),
                    demand_level=demand_forecast,
                    supply_level=supply_forecast,
                    confidence=confidence,
                    strategy_used="forecast",
                )
                forecast_points.append(forecast_point)
            return forecast_points
        except _OPS_ERRORS as e:
            logger.error("Failed to generate price forecast for %s: %s", resource_id, e)
            return []

    async def set_provider_strategy(
        self, provider_id: str, strategy: PricingStrategy, constraints: PriceConstraints | None = None
    ) -> bool:
        """Set pricing strategy for a provider"""
        try:
            async with self._lock:
                self.provider_strategies[provider_id] = strategy
                if constraints:
                    self.price_constraints[provider_id] = constraints
                await self._persist_provider_strategy(provider_id, strategy, constraints)
            logger.info("Set strategy %s for provider %s", strategy.value, provider_id)
            return True
        except _OPS_ERRORS as e:
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
                        min_price=constraints.min_price if constraints and constraints.min_price else None,
                        max_price=constraints.max_price if constraints and constraints.max_price else None,
                        max_change_percent=constraints.max_change_percent if constraints else 0.5,
                        min_change_interval=constraints.min_change_interval if constraints else 300,
                        strategy_lock_period=constraints.strategy_lock_period if constraints else 3600,
                        is_active=True,
                    )
                )
                session.add(
                    PricingAuditLog(
                        provider_id=provider_id,
                        action_type="strategy_update",
                        action_description=f"Provider strategy set to {strategy.value}",
                        action_source="automated",
                        after_state={
                            "strategy": strategy.value,
                            "min_price": str(constraints.min_price) if constraints and constraints.min_price else None,
                            "max_price": str(constraints.max_price) if constraints and constraints.max_price else None,
                        },
                        changed_fields=["strategy_type", "is_active"],
                        decision_reasoning=f"strategy={strategy.value}",
                    )
                )
                session.commit()

        try:
            await asyncio.to_thread(_write)
        except _OPS_ERRORS as e:
            logger.warning("Failed to persist strategy for provider %s: %s", provider_id, e)

    # not-money: np.polyfit over a price series, returning a slope. Same reasoning as
    # _calculate_rsi -- a dimensionless statistic, and numpy has no Decimal dtype.
    def _calculate_price_trend(self, prices: list[float]) -> float:
        """Calculate simple price trend"""
        if len(prices) < 2:
            return 0.0
        x = np.arange(len(prices))
        y = np.array(prices)
        slope = np.polyfit(x, y, 1)[0]
        return slope  # type: ignore[no-any-return]

    def _calculate_seasonal_factor(self, hour: int) -> Decimal:
        """Calculate seasonal adjustment factor"""
        if 6 <= hour <= 10:
            return Decimal("1.05")
        elif 10 <= hour <= 16:
            return Decimal("1.1")
        elif 16 <= hour <= 20:
            return Decimal("1.05")
        elif 20 <= hour <= 24:
            return Decimal("0.95")
        else:
            return Decimal("0.9")

    def _forecast_demand_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple demand level forecasting.

        #1375: the forecast is the recent average itself — no random noise.
        Deterministic given the same pricing history.
        """
        if not historical:
            return 0.5
        recent_avg = np.mean(historical[-6:]) if len(historical) >= 6 else np.mean(historical)
        return float(max(0.0, min(1.0, recent_avg)))  # type: ignore[arg-type]

    def _forecast_supply_level(self, historical: list[float], hour_ahead: int) -> float:
        """Simple supply level forecasting (deterministic — see #1375)."""
        if not historical:
            return 0.5
        recent_avg = np.mean(historical[-12:]) if len(historical) >= 12 else np.mean(historical)
        return float(max(0.0, min(1.0, recent_avg)))  # type: ignore[arg-type]
