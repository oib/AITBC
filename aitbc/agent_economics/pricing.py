"""Dynamic fee market and demand-aware pricing primitives (v0.12.0 §A4).

Extends the existing dynamic pricing API in ``aitbc.agent_economics.models``
with market-maker, demand forecast, and surge pricing primitives for the
OpenClaw autonomous economics layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class DemandTrend(StrEnum):
    """Trend direction for a demand forecast."""

    FLAT = "flat"
    RISING = "rising"
    FALLING = "falling"
    VOLATILE = "volatile"


@dataclass
class DemandForecast:
    """Predicted demand for a service or resource over a bounded period."""

    forecast_id: str
    period: str  # e.g. "1h", "24h"
    predicted_demand: Decimal  # units of demand
    confidence: Decimal = field(default_factory=lambda: Decimal("1"))
    trend: DemandTrend | str = DemandTrend.FLAT
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.trend, str):
            self.trend = DemandTrend(self.trend)
        if self.predicted_demand < 0:
            raise ValueError("predicted_demand cannot be negative")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class SurgePricing:
    """Surge multiplier derived from observed or predicted demand."""

    base_price: Decimal
    current_multiplier: Decimal = field(default_factory=lambda: Decimal("1"))
    demand_threshold: Decimal = field(default_factory=lambda: Decimal("100"))
    max_multiplier: Decimal = field(default_factory=lambda: Decimal("5"))
    current_demand: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.base_price < 0:
            raise ValueError("base_price cannot be negative")
        if self.current_multiplier < 1:
            raise ValueError("current_multiplier cannot be below 1")
        if self.max_multiplier < 1:
            raise ValueError("max_multiplier cannot be below 1")
        if self.current_multiplier > self.max_multiplier:
            raise ValueError("current_multiplier cannot exceed max_multiplier")

    def price(self) -> Decimal:
        """Return the surge-adjusted price."""
        return self.base_price * self.current_multiplier

    def update(self, demand: Decimal | None = None) -> None:
        """Recalculate surge multiplier from current or supplied demand."""
        if demand is None:
            demand = self.current_demand
        if demand < 0:
            raise ValueError("demand cannot be negative")
        self.current_demand = demand
        if demand <= self.demand_threshold:
            self.current_multiplier = Decimal("1")
            return
        extra = demand - self.demand_threshold
        # Each full threshold unit above the threshold adds 1x multiplier
        multiplier = Decimal("1") + (extra / self.demand_threshold)
        self.current_multiplier = min(multiplier, self.max_multiplier)


@dataclass
class MarketMakerStrategy:
    """Market-maker pricing with bid/ask spread around a base price.

    The spread is expressed as a percentage of the base price. Inventory
    pressure can widen or narrow the quoted spread.
    """

    strategy_id: str
    agent_id: str
    base_price: Decimal
    spread_percent: Decimal = field(default_factory=lambda: Decimal("1"))
    inventory: Decimal = field(default_factory=lambda: Decimal("0"))
    max_position: Decimal | None = None
    token: str = ""
    chain_id: str = "ait-hub"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if self.base_price < 0:
            raise ValueError("base_price cannot be negative")
        if self.spread_percent < 0:
            raise ValueError("spread_percent cannot be negative")
        if self.max_position is not None and self.max_position <= 0:
            raise ValueError("max_position must be positive if set")

    def bid_price(self) -> Decimal:
        """Return the price the agent is willing to pay to buy."""
        return self.base_price * (Decimal("1") - self.spread_percent / Decimal("200"))

    def ask_price(self) -> Decimal:
        """Return the price the agent demands to sell."""
        return self.base_price * (Decimal("1") + self.spread_percent / Decimal("200"))

    def mid_price(self) -> Decimal:
        """Return the midpoint between bid and ask."""
        return (self.bid_price() + self.ask_price()) / Decimal("2")

    def _inventory_risk_pressure(self, overrun: Decimal) -> Decimal:
        """Return an S-shaped pressure in [0, 1] using the error function.

        The steepness is controlled by ``meta["order_book_depth"]`` (a positive
        Decimal, default 1). A higher depth means the spread widens faster as the
        position overruns the limit.
        """
        depth = Decimal(str(self.meta.get("order_book_depth", "1")))
        if depth <= 0:
            depth = Decimal("1")
        pressure = math.erf(float(overrun * depth))
        return Decimal(str(pressure))

    def adjust_for_inventory(self) -> None:
        """Widen ask and narrow bid when inventory is near max position.

        Uses a smooth inventory-risk utility (sigmoid via ``math.erf``). The
        ``meta`` key ``order_book_depth`` tunes responsiveness; a real
        production model would derive this from the actual order book.
        """
        if self.max_position is None or self.max_position == 0:
            return
        ratio = self.inventory / self.max_position
        if ratio <= 1:
            return
        overrun = ratio - 1
        pressure = self._inventory_risk_pressure(overrun)
        max_multiplier = Decimal(str(self.meta.get("max_spread_multiplier", "3")))
        if max_multiplier <= 1:
            max_multiplier = Decimal("3")
        self.spread_percent = self.spread_percent * (Decimal("1") + pressure * (max_multiplier - Decimal("1")))


class DynamicFeeMarket:
    """Combine demand forecast and surge pricing into a single fee quote."""

    def __init__(
        self,
        surge: SurgePricing,
        forecast: DemandForecast | None = None,
    ) -> None:
        self.surge = surge
        self.forecast = forecast

    def fee(
        self,
        base_cost: Decimal | None = None,
    ) -> Decimal:
        """Return the current market fee.

        If a forecast is attached and the trend is rising or volatile, the
        multiplier is boosted by an additional forecast confidence factor.
        """
        price = self.surge.price()
        if base_cost is not None and base_cost >= 0:
            price = base_cost * self.surge.current_multiplier
        if self.forecast is None:
            return price
        if self.forecast.trend in {DemandTrend.RISING, DemandTrend.VOLATILE}:
            # confidence-based boost, capped at 2x the surge price
            boost = Decimal("1") + self.forecast.confidence
            if boost > Decimal("2"):
                boost = Decimal("2")
            return price * boost
        return price
