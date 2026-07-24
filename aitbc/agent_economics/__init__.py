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
- AbstractYieldAdapter, YieldVenue, YieldStrategy, YieldOpportunity: yield venues
- CrossChainSwap, SwapRoute, SwapQuote, quote_swap: cross-chain swaps
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
    LiquidationError,
    OnChainActionError,
    PortfolioError,
    PricingError,
    RebalanceError,
    RevenueRouteError,
    SlashError,
    StakingError,
    SwapError,
    YieldVenueError,
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
from .liquidation import (
    LiquidationEvent,
    LiquidationReason,
    LiquidationStatus,
    OffboardingStatus,
    ProviderOffboarding,
    liquidate_bond,
    offboard_provider,
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
from .swaps import (
    CrossChainSwap,
    SwapQuote,
    SwapRoute,
    SwapStatus,
    quote_swap,
)
from .yield_venues import (
    AbstractYieldAdapter,
    AdapterStatus,
    YieldHarvest,
    YieldOpportunity,
    YieldRegistry,
    YieldStrategy,
    YieldVenue,
    YieldVenuePosition,
)

__all__ = [
    "AbstractYieldAdapter",
    "AdapterStatus",
    "AgentEconomicsError",
    "BondError",
    "BondStatus",
    "Budget",
    "BudgetError",
    "ChainHoldings",
    "ConstraintType",
    "CrossChainSwap",
    "Delegation",
    "DelegationStatus",
    "DemandForecast",
    "DemandTrend",
    "DynamicFeeMarket",
    "LiquidationError",
    "LiquidationEvent",
    "LiquidationReason",
    "LiquidationStatus",
    "MarketMakerStrategy",
    "OffboardingStatus",
    "OnChainAction",
    "OnChainActionError",
    "OnChainActionType",
    "PerformanceBond",
    "Portfolio",
    "PortfolioError",
    "PricingError",
    "PricingStrategy",
    "PricingStrategyType",
    "ProviderOffboarding",
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
    "SwapError",
    "SwapQuote",
    "SwapRoute",
    "SwapStatus",
    "YieldHarvest",
    "YieldOpportunity",
    "YieldPosition",
    "YieldRegistry",
    "YieldStrategy",
    "YieldVenue",
    "YieldVenueError",
    "YieldVenuePosition",
    "compute_slash_amount",
    "liquidate_bond",
    "offboard_provider",
    "quote_swap",
    "slash_bond",
    "slash_stake",
    "validate_slash_event",
]
