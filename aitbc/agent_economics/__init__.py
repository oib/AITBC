"""AITBC OpenClaw autonomous economics shared types (v0.11.0 §A2, v0.12.0 §A2).

Provides:
- PricingStrategyType, RevenueRouteType, OnChainActionType: enums for economic primitives
- Budget: agent budget with allocation tracking
- RevenueRoute: revenue distribution target
- PricingStrategy: demand-aware pricing configuration
- OnChainAction: validated on-chain economic action payload
- PerformanceBond, StakeAccount: bond and stake primitives
- SlashReason, SlashingCondition, SlashEvent: slashing validators
"""

from __future__ import annotations

from .bonds import (
    BondStatus,
    PerformanceBond,
    StakeAccount,
    StakeStatus,
)
from .errors import (
    AgentEconomicsError,
    BondError,
    BudgetError,
    OnChainActionError,
    PricingError,
    RevenueRouteError,
    SlashError,
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
from .slash import (
    SlashEvent,
    SlashReason,
    SlashingCondition,
    compute_slash_amount,
    slash_bond,
    slash_stake,
    validate_slash_event,
)

__all__ = [
    "AgentEconomicsError",
    "BondError",
    "BondStatus",
    "Budget",
    "BudgetError",
    "OnChainAction",
    "OnChainActionError",
    "OnChainActionType",
    "PerformanceBond",
    "PricingError",
    "PricingStrategy",
    "PricingStrategyType",
    "RevenueRoute",
    "RevenueRouteError",
    "RevenueRouteType",
    "SlashError",
    "SlashEvent",
    "SlashReason",
    "SlashingCondition",
    "StakeAccount",
    "StakeStatus",
    "compute_slash_amount",
    "slash_bond",
    "slash_stake",
    "validate_slash_event",
]
