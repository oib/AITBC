"""AITBC OpenClaw autonomous economics shared types (v0.11.0–v0.13.0).

Provides:
- PricingStrategyType, RevenueRouteType, OnChainActionType: enums for economic primitives
- Budget: agent budget with allocation tracking
- RevenueRoute: revenue distribution target
- PricingStrategy: demand-aware pricing configuration
- OnChainAction: validated on-chain economic action payload
- PerformanceBond, StakeAccount: bond and stake primitives
- SlashReason, SlashingCondition, SlashEvent: slashing validators
- StakingStrategy, Delegation, YieldPosition: staking primitives
- Portfolio: portfolio tracking
- MarketMakerStrategy, SurgePricing, DynamicFeeMarket: dynamic pricing
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
    PortfolioError,
    PricingError,
    RebalanceError,
    RevenueRouteError,
    SlashError,
    StakingError,
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
from .portfolio import Portfolio
from .pricing import (
    DemandForecast,
    DemandTrend,
    DynamicFeeMarket,
    MarketMakerStrategy,
    SurgePricing,
)
from .rebalance import (
    ChainHoldings,
    ConstraintType,
    ReinvestmentPolicy,
    RebalanceAction,
    RebalanceActionType,
    RebalanceConstraint,
    Rebalancer,
    RebalancingTrigger,
)
from .staking import (
    Delegation,
    DelegationStatus,
    StakingStrategy,
    YieldPosition,
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
    "ChainHoldings",
    "ConstraintType",
    "Delegation",
    "DelegationStatus",
    "DemandForecast",
    "DemandTrend",
    "DynamicFeeMarket",
    "MarketMakerStrategy",
    "OnChainAction",
    "OnChainActionError",
    "OnChainActionType",
    "PerformanceBond",
    "Portfolio",
    "PortfolioError",
    "PricingError",
    "PricingStrategy",
    "PricingStrategyType",
    "RebalanceAction",
    "RebalanceActionType",
    "RebalanceConstraint",
    "RebalanceError",
    "Rebalancer",
    "RebalancingTrigger",
    "ReinvestmentPolicy",
    "RevenueRoute",
    "RevenueRouteError",
    "RevenueRouteType",
    "SlashError",
    "SlashEvent",
    "SlashReason",
    "SlashingCondition",
    "StakeAccount",
    "StakeStatus",
    "StakingError",
    "StakingStrategy",
    "SurgePricing",
    "YieldPosition",
    "compute_slash_amount",
    "slash_bond",
    "slash_stake",
    "validate_slash_event",
]
