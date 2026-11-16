"""Price-point persistence and market-conditions cluster for DynamicPricingEngine.

Methods moved verbatim from ``dynamic_pricing.py`` (issue #1860, phase 6 band
split); ``DynamicPricingEngine`` inherits this mixin so every ``self.*`` call
keeps resolving. Helpers shared with the sibling modules live in
``dynamic_pricing_common`` and the data types in ``dynamic_pricing_model``.
"""

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger

from .dynamic_pricing_common import _D, _OPS_ERRORS, _serialize_decimals, np
from .dynamic_pricing_model import (
    MarketConditions,
    PriceConstraints,
    PricePoint,
    PricingFactors,
    PricingStrategy,
    ResourceType,
)

# Importing the pricing persistence models registers their tables with
# SQLModel.metadata so init_db()/create_all() creates them at startup.
from ...domain.pricing_models import (
    PricingAuditLog,
    PricingHistory,
    ProviderPricingStrategy,
)
from ...domain.pricing_models import ResourceType as PricingResourceType

logger = get_logger(__name__)


class _PricingMarketMixin:
    # Attributes are assigned in DynamicPricingEngine.__init__; declared here
    # for mypy (same pattern as the market-service mixins).
    config: dict[str, Any]
    pricing_history: dict[str, list[PricePoint]]
    market_conditions_cache: dict[str, MarketConditions]
    provider_strategies: dict[str, PricingStrategy]
    price_constraints: dict[str, PriceConstraints]
    strategy_configs: dict[PricingStrategy, dict[str, Any]]
    max_volatility_threshold: float
    circuit_breakers: dict[str, bool]
    _lock: asyncio.Lock

    async def _store_price_point(
        self,
        resource_id: str,
        resource_type: ResourceType,
        price: Decimal,
        factors: PricingFactors,
        strategy: PricingStrategy,
    ) -> None:
        """Store price point in history (in-memory cache + durable persistence)."""
        async with self._lock:
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
        price: Decimal,
        factors: PricingFactors,
        strategy: PricingStrategy,
    ) -> None:
        """Persist a price point to the pricing_history table (best-effort).

        Also records a PricingAuditLog entry so every pricing decision has an
        auditable trail (action_source="automated").
        """

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
                        pricing_factors=_serialize_decimals(asdict(factors)),
                        confidence_score=factors.confidence_score,
                    )
                )
                session.add(
                    PricingAuditLog(
                        resource_id=resource_id,
                        action_type="price_change",
                        action_description=f"Automated price set to {price:.6f} via {strategy.value}",
                        action_source="automated",
                        after_state={
                            "price": str(price),
                            "base_price": str(factors.base_price),
                            "strategy": strategy.value,
                            "confidence_score": factors.confidence_score,
                        },
                        changed_fields=["price", "strategy_used"],
                        decision_reasoning=f"strategy={strategy.value}; confidence={factors.confidence_score:.3f}",
                        market_conditions={
                            "demand_level": factors.demand_level,
                            "supply_level": factors.supply_level,
                            "market_volatility": factors.market_volatility,
                        },
                    )
                )
                session.commit()

        try:
            await asyncio.to_thread(_write)
        except _OPS_ERRORS as e:
            # Persistence is best-effort: never let a DB issue break price calculation.
            logger.warning("Failed to persist price point for %s: %s", resource_id, e)

    async def _get_market_conditions(self, resource_type: ResourceType, region: str) -> MarketConditions:
        """Get current market conditions from live listings, or neutral defaults."""
        cache_key = f"{region}_{resource_type.value}"
        if cache_key in self.market_conditions_cache:
            cached = self.market_conditions_cache[cache_key]
            if (datetime.now(UTC) - cached.timestamp).total_seconds() < 300:
                return cached
        conditions = await self._load_market_conditions(resource_type, region)
        self.market_conditions_cache[cache_key] = conditions
        return conditions

    async def _load_market_conditions(self, resource_type: ResourceType, region: str) -> MarketConditions:
        """Derive conditions from real listings; fall back to deterministic
        neutral values — never synthetic random walks (#1375)."""
        if resource_type is ResourceType.GPU:
            snapshot = await asyncio.to_thread(self._read_gpu_market_snapshot, region)
            if snapshot is not None:
                return snapshot
        return MarketConditions(
            region=region,
            resource_type=resource_type,
            demand_level=0.5,
            supply_level=0.5,
            average_price=_D("0"),
            price_volatility=0.0,
            utilization_rate=0.5,
            competitor_prices=[],
            market_sentiment=0.0,
        )

    def _read_gpu_market_snapshot(self, region: str) -> MarketConditions | None:
        """Aggregate live GPURegistry listings into market conditions.

        Returns None when no active listings match (caller falls back to
        neutral conditions). ``region`` filters listings; ``"global"``/empty
        aggregates across all regions.
        """
        from sqlmodel import select

        from .....storage.db import session_scope
        from ....market.domain.gpu_market import GPURegistry

        stmt = select(GPURegistry).where(GPURegistry.status.in_(["available", "booked"]))  # type: ignore[attr-defined]
        if region and region != "global":
            stmt = stmt.where(GPURegistry.region == region)
        with session_scope() as session:
            rows = list(session.execute(stmt).scalars().all())
        if not rows:
            return None

        total = len(rows)
        available = sum(1 for gpu in rows if gpu.status == "available")
        prices = sorted({gpu.price_per_hour for gpu in rows if gpu.price_per_hour is not None and gpu.price_per_hour > 0})
        avg_price = sum(prices) / len(prices) if prices else Decimal("0")
        if len(prices) > 1 and avg_price > 0:
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility_ratio = variance.sqrt() / avg_price  # not-money: coefficient of variation, a score
            price_volatility = min(float(volatility_ratio), 1.0)
        else:
            price_volatility = 0.0
        return MarketConditions(
            region=region,
            resource_type=ResourceType.GPU,
            demand_level=0.5,  # no live demand signal — honest neutral, not fabricated
            supply_level=available / total,
            average_price=avg_price,
            price_volatility=price_volatility,
            utilization_rate=(total - available) / total,
            competitor_prices=list(prices[:8]),
            market_sentiment=0.0,
        )

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
                        price=_D(row.price),
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
        except _OPS_ERRORS as e:
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
                    min_price=_D(row.min_price) if row.min_price is not None else None,
                    max_price=_D(row.max_price) if row.max_price is not None else None,
                    max_change_percent=row.max_change_percent,
                    min_change_interval=row.min_change_interval,
                    strategy_lock_period=row.strategy_lock_period,
                )
            return strategies, constraints

        try:
            self.provider_strategies, self.price_constraints = await asyncio.to_thread(_read)
            logger.info("Loaded strategies for %d providers", len(self.provider_strategies))
        except _OPS_ERRORS as e:
            logger.warning("Failed to load provider strategies (starting empty): %s", e)

    async def _update_market_conditions(self) -> None:
        """Background task to update market conditions"""
        while True:
            try:
                self.market_conditions_cache.clear()
                await asyncio.sleep(300)
            except _OPS_ERRORS as e:
                logger.error("Error updating market conditions: %s", e)
                await asyncio.sleep(60)

    async def _monitor_price_volatility(self) -> None:
        """Background task to monitor price volatility"""
        while True:
            try:
                for resource_id, history in self.pricing_history.items():
                    if len(history) >= 10:
                        recent_prices = [
                            float(p.price) for p in history[-10:]
                        ]  # not-money: strategy/score computation, not a settled amount
                        volatility = np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0
                        if volatility > self.max_volatility_threshold:
                            logger.warning("High volatility detected for %s: %s", resource_id, volatility)
                await asyncio.sleep(600)
            except _OPS_ERRORS as e:
                logger.error("Error monitoring volatility: %s", e)
                await asyncio.sleep(120)

    async def _optimize_strategies(self) -> None:
        """Background task to optimize pricing strategies"""
        while True:
            try:
                await asyncio.sleep(3600)
            except _OPS_ERRORS as e:
                logger.error("Error optimizing strategies: %s", e)
                await asyncio.sleep(300)

    async def _reset_circuit_breaker(self, resource_id: str, delay: int) -> None:
        """Reset circuit breaker after delay"""
        await asyncio.sleep(delay)
        self.circuit_breakers[resource_id] = False
        logger.info("Reset circuit breaker for %s", resource_id)
