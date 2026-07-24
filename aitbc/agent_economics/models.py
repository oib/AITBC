"""Shared OpenClaw autonomous economics types for AITBC (v0.11.0 §A2).

These are the canonical dependency-free primitives consumed by the OpenClaw
agent runtime, the `apps/coordinator-api` economic domains, and the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class PricingStrategyType(StrEnum):
    """Type of pricing strategy an agent may apply to its services."""

    FIXED = "fixed"
    MARKET = "market"
    DYNAMIC = "dynamic"
    SURGE = "surge"


class RevenueRouteType(StrEnum):
    """Destination category for a share of agent revenue."""

    TREASURY = "treasury"
    STAKING = "staking"
    PROVIDER = "provider"
    VALIDATOR = "validator"
    BURN = "burn"
    RESERVE = "reserve"


class OnChainActionType(StrEnum):
    """Economic actions an agent can execute on-chain."""

    STAKE = "stake"
    UNSTAKE = "unstake"
    DELEGATE = "delegate"
    UNDELEGATE = "undelegate"
    TRANSFER = "transfer"
    FEE_PAYMENT = "fee_payment"
    REWARD_CLAIM = "reward_claim"
    BOND_LOCK = "bond_lock"
    BOND_RELEASE = "bond_release"


@dataclass
class Budget:
    """Agent budget for a given chain/token.

    Tracks total funds available to an agent for economic operations and the
    amount already allocated to pending actions.
    """

    budget_id: str
    agent_id: str
    chain_id: str
    token: str
    total: Decimal = field(default_factory=lambda: Decimal("0"))
    allocated: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> Decimal:
        """Funds not currently allocated."""
        return self.total - self.allocated

    def allocate(self, amount: Decimal) -> None:
        """Reserve funds for a pending operation."""
        if amount <= 0:
            raise ValueError("allocate amount must be positive")
        if amount > self.available:
            raise ValueError("allocate amount exceeds available budget")
        self.allocated += amount

    def release(self, amount: Decimal) -> None:
        """Return previously allocated funds to the available pool."""
        if amount <= 0:
            raise ValueError("release amount must be positive")
        if amount > self.allocated:
            raise ValueError("release amount exceeds allocated budget")
        self.allocated -= amount

    def spend(self, amount: Decimal) -> None:
        """Finalize a spend against allocated funds."""
        if amount <= 0:
            raise ValueError("spend amount must be positive")
        if amount > self.allocated:
            raise ValueError("spend amount exceeds allocated budget")
        self.total -= amount
        self.allocated -= amount


@dataclass
class RevenueRoute:
    """Revenue distribution target for an agent's earnings."""

    route_id: str
    route_type: RevenueRouteType | str
    recipient: str
    percentage: Decimal = field(default_factory=lambda: Decimal("0"))
    min_amount: Decimal | None = None
    chain_id: str = "ait-hub"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize enum values and validate percentage bounds."""
        if isinstance(self.route_type, str):
            self.route_type = RevenueRouteType(self.route_type)
        if not (Decimal("0") <= self.percentage <= Decimal("100")):
            raise ValueError("route percentage must be between 0 and 100")


@dataclass
class PricingStrategy:
    """Demand-aware pricing configuration for agent services."""

    strategy_id: str
    agent_id: str
    strategy_type: PricingStrategyType | str
    base_price: Decimal = field(default_factory=lambda: Decimal("0"))
    demand_factor: Decimal = field(default_factory=lambda: Decimal("1"))
    surge_multiplier: Decimal = field(default_factory=lambda: Decimal("1"))
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    chain_id: str = "ait-hub"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize enum values and validate pricing bounds."""
        if isinstance(self.strategy_type, str):
            self.strategy_type = PricingStrategyType(self.strategy_type)
        if self.base_price < 0:
            raise ValueError("base_price cannot be negative")
        if self.demand_factor < 0 or self.surge_multiplier < 0:
            raise ValueError("demand_factor and surge_multiplier cannot be negative")
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price cannot exceed max_price")

    def price(self, base_cost: Decimal | None = None) -> Decimal:
        """Compute the current price given base cost and market factors."""
        cost = base_cost if base_cost is not None else self.base_price
        raw = cost * self.demand_factor * self.surge_multiplier
        if self.min_price is not None and raw < self.min_price:
            return self.min_price
        if self.max_price is not None and raw > self.max_price:
            return self.max_price
        return raw


@dataclass
class OnChainAction:
    """Validated payload for an economic action submitted on-chain."""

    action_id: str
    agent_id: str
    action_type: OnChainActionType | str
    chain_id: str
    contract_address: str
    amount: Decimal = field(default_factory=lambda: Decimal("0"))
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize enum values and validate required identifiers."""
        if isinstance(self.action_type, str):
            self.action_type = OnChainActionType(self.action_type)
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if not self.chain_id:
            raise ValueError("chain_id is required")
        if not self.contract_address:
            raise ValueError("contract_address is required")
        if self.amount < 0:
            raise ValueError("amount cannot be negative")
