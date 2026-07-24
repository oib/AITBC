"""AITBC OpenClaw autonomous economics shared types (v0.11.0 §A2).

Provides:
- PricingStrategyType, RevenueRouteType, OnChainActionType: enums for economic primitives
- Budget: agent budget with allocation tracking
- RevenueRoute: revenue distribution target
- PricingStrategy: demand-aware pricing configuration
- OnChainAction: validated on-chain economic action payload
"""

from __future__ import annotations

from .errors import (
    AgentEconomicsError,
    BudgetError,
    OnChainActionError,
    PricingError,
    RevenueRouteError,
)
from .models import (
    Budget,
    OnChainAction,
    OnChainActionType,
    PricingStrategy,
    PricingStrategyType,
    RevenueRoute,
    RevenueRouteType,
)

__all__ = [
    "AgentEconomicsError",
    "Budget",
    "BudgetError",
    "OnChainAction",
    "OnChainActionError",
    "OnChainActionType",
    "PricingError",
    "PricingStrategy",
    "PricingStrategyType",
    "RevenueRoute",
    "RevenueRouteError",
    "RevenueRouteType",
]
