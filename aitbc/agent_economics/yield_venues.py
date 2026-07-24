"""Pluggable yield-venue adapters for AITBC (v0.13.0 §A4).

Provides ``YieldVenue``, ``YieldOpportunity``, ``YieldStrategy``, and an
``AbstractYieldAdapter`` / ``YieldRegistry`` pattern so agents can compare
venues, deposit, withdraw, and harvest rewards in a uniform way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aitbc.risk.scoring import RiskLevel


class YieldVenue(StrEnum):
    """Supported yield-venue types."""

    STAKING = "staking"
    LIQUIDITY_POOL = "liquidity_pool"
    LENDING = "lending"
    RESTAKING = "restaking"


class AdapterStatus(StrEnum):
    """Lifecycle status of a yield adapter."""

    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"


@dataclass
class YieldOpportunity:
    """A single yield opportunity on a chain/token venue."""

    venue: YieldVenue | str
    chain_id: str
    token: str
    apy: Decimal
    tvl: Decimal
    risk_level: RiskLevel | str = RiskLevel.MEDIUM
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.venue, str):
            self.venue = YieldVenue(self.venue)
        if isinstance(self.risk_level, str):
            self.risk_level = RiskLevel(self.risk_level)
        if self.apy < 0:
            raise ValueError("apy cannot be negative")
        if self.tvl < 0:
            raise ValueError("tvl cannot be negative")


@dataclass
class YieldStrategy:
    """Agent policy that selects and rebalances across yield venues."""

    strategy_id: str
    agent_id: str
    venues: list[YieldVenue] = field(default_factory=list)
    target_apy: Decimal = field(default_factory=lambda: Decimal("0"))
    max_exposure_per_venue: Decimal = field(default_factory=lambda: Decimal("100"))
    auto_compound: bool = False
    min_harvest_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if not (Decimal("0") <= self.max_exposure_per_venue <= Decimal("100")):
            raise ValueError("max_exposure_per_venue must be between 0 and 100")
        if self.min_harvest_amount < 0:
            raise ValueError("min_harvest_amount cannot be negative")

    def allows_venue(self, venue: YieldVenue | str) -> bool:
        """Return True if the venue is in the strategy's allow list."""
        if isinstance(venue, str):
            venue = YieldVenue(venue)
        return not self.venues or venue in self.venues


@dataclass
class YieldVenuePosition:
    """A position in a yield venue for an agent.

    Distinct from ``aitbc.agent_economics.staking.YieldVenuePosition``; this
    tracks principal and accumulated rewards inside a generic yield venue.
    """

    position_id: str
    agent_id: str
    venue: YieldVenue | str
    chain_id: str
    token: str
    principal: Decimal = field(default_factory=lambda: Decimal("0"))
    rewards: Decimal = field(default_factory=lambda: Decimal("0"))
    status: AdapterStatus | str = AdapterStatus.ACTIVE
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.venue, str):
            self.venue = YieldVenue(self.venue)
        if isinstance(self.status, str):
            self.status = AdapterStatus(self.status)
        if self.principal < 0 or self.rewards < 0:
            raise ValueError("principal and rewards cannot be negative")

    @property
    def total_value(self) -> Decimal:
        return self.principal + self.rewards

    def harvest(self) -> Decimal:
        """Claim and reset accumulated rewards."""
        amount = self.rewards
        self.rewards = Decimal("0")
        return amount


@dataclass
class YieldHarvest:
    """Result of a harvest operation."""

    harvest_id: str
    position_id: str
    agent_id: str
    amount: Decimal
    venue: YieldVenue | str
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.venue, str):
            self.venue = YieldVenue(self.venue)
        if self.amount < 0:
            raise ValueError("harvest amount cannot be negative")


class AbstractYieldAdapter(ABC):
    """Interface for a pluggable yield-venue adapter.

    Adapters are stateless compute helpers; on-chain state is represented by
    ``YieldVenuePosition`` records passed in and returned.
    """

    name: str = ""
    venue: YieldVenue = YieldVenue.STAKING

    @abstractmethod
    def get_opportunities(self, chain_id: str, token: str) -> list[YieldOpportunity]:
        """Return available opportunities for a chain/token."""

    @abstractmethod
    def quote_deposit(
        self,
        position: YieldVenuePosition,
        amount: Decimal,
        opportunity: YieldOpportunity,
    ) -> Decimal:
        """Return expected principal after deposit (simplified)."""

    @abstractmethod
    def quote_withdraw(
        self,
        position: YieldVenuePosition,
        amount: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Return (principal_after, withdrawn_rewards)."""

    @abstractmethod
    def harvest(self, position: YieldVenuePosition) -> YieldHarvest:
        """Harvest rewards from a position."""


class YieldRegistry:
    """Registry of named yield adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, AbstractYieldAdapter] = {}

    def register(self, name: str, adapter: AbstractYieldAdapter) -> None:
        """Register an adapter by name."""
        self._adapters[name] = adapter

    def get(self, name: str) -> AbstractYieldAdapter:
        """Retrieve a registered adapter."""
        if name not in self._adapters:
            raise KeyError(f"yield adapter {name} not registered")
        return self._adapters[name]

    def list_adapters(self) -> list[str]:
        """Return the names of registered adapters."""
        return list(self._adapters.keys())
