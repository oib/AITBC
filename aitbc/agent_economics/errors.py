"""Domain exceptions for aitbc.agent_economics (v0.11.0 §A2)."""

from __future__ import annotations


class AgentEconomicsError(Exception):
    """Base exception for agent economic domain errors."""


class BudgetError(AgentEconomicsError):
    """Budget allocation, release, or spend error."""


class RevenueRouteError(AgentEconomicsError):
    """Revenue routing configuration error."""


class PricingError(AgentEconomicsError):
    """Pricing strategy configuration or calculation error."""


class OnChainActionError(AgentEconomicsError):
    """Invalid on-chain economic action payload."""


class BondError(AgentEconomicsError):
    """Performance bond state or operation error."""


class SlashError(AgentEconomicsError):
    """Slashing validation or application error."""


class RebalanceError(AgentEconomicsError):
    """Rebalancing or reinvestment policy error."""


class StakingError(AgentEconomicsError):
    """Staking delegation or yield tracking error."""


class PortfolioError(AgentEconomicsError):
    """Portfolio allocation or valuation error."""


class LiquidationError(AgentEconomicsError):
    """Bond liquidation or provider off-boarding error."""
