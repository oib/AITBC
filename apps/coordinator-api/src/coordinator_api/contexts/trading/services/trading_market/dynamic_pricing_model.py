"""Data model for the dynamic pricing engine.

Enums and dataclasses moved verbatim from ``dynamic_pricing.py`` (issue #1860,
phase 6 band split); ``dynamic_pricing.py`` re-exports every name.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


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

    base_price: Decimal
    demand_multiplier: Decimal = Decimal("1.0")
    supply_multiplier: Decimal = Decimal("1.0")
    time_multiplier: Decimal = Decimal("1.0")
    performance_multiplier: Decimal = Decimal("1.0")
    competition_multiplier: Decimal = Decimal("1.0")
    sentiment_multiplier: Decimal = Decimal("1.0")
    regional_multiplier: Decimal = Decimal("1.0")
    confidence_score: float = 0.8
    risk_adjustment: Decimal = Decimal("0.0")
    demand_level: float = 0.5
    supply_level: float = 0.5
    market_volatility: float = 0.1
    provider_reputation: float = 1.0
    utilization_rate: float = 0.5
    historical_performance: float = 1.0


@dataclass
class PriceConstraints:
    """Constraints for pricing calculations"""

    min_price: Decimal | None = None
    max_price: Decimal | None = None
    max_change_percent: float = 0.5
    min_change_interval: int = 300
    strategy_lock_period: int = 3600


@dataclass
class PricePoint:
    """Single price point in time series"""

    timestamp: datetime
    price: Decimal
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
    average_price: Decimal
    price_volatility: float
    utilization_rate: float
    competitor_prices: list[Decimal] = field(default_factory=list)
    market_sentiment: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PricingResult:
    """Result of dynamic pricing calculation"""

    resource_id: str
    resource_type: ResourceType
    current_price: Decimal
    recommended_price: Decimal
    price_trend: PriceTrend
    confidence_score: float
    factors_exposed: dict[str, Any]
    reasoning: list[str]
    next_update: datetime
    strategy_used: PricingStrategy
