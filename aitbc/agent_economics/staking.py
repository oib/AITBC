"""Staking strategy and delegation shared types for AITBC (v0.13.0 §A1).

Provides ``StakingStrategy``, ``Delegation``, and ``YieldPosition`` primitives
for automated delegation, un-delegation, and yield tracking across validator
sets. These build on the ``StakeAccount`` and ``PerformanceBond`` models from
v0.12.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import StakingError


class DelegationStatus(StrEnum):
    """Lifecycle status of a delegation to a validator."""

    PENDING = "pending"
    ACTIVE = "active"
    UNBONDING = "unbonding"
    WITHDRAWN = "withdrawn"


@dataclass
class Delegation:
    """A single delegation of tokens to a validator."""

    delegation_id: str
    agent_id: str
    validator: str
    amount: Decimal
    token: str
    status: DelegationStatus | str = DelegationStatus.PENDING
    delegated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    unbonded_at: datetime | None = None
    rewards: Decimal = field(default_factory=lambda: Decimal("0"))
    chain_id: str = "ait-hub"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = DelegationStatus(self.status)
        if self.amount <= 0:
            raise ValueError("delegation amount must be positive")
        if not self.agent_id or not self.validator:
            raise ValueError("agent_id and validator are required")
        if self.rewards < 0:
            raise ValueError("rewards cannot be negative")

    def activate(self) -> None:
        """Move delegation from pending to active."""
        if self.status != DelegationStatus.PENDING:
            raise StakingError(f"cannot activate delegation in status {self.status}")
        self.status = DelegationStatus.ACTIVE

    def unbond(self) -> None:
        """Begin unbonding an active delegation."""
        if self.status != DelegationStatus.ACTIVE:
            raise StakingError(f"cannot unbond delegation in status {self.status}")
        self.status = DelegationStatus.UNBONDING
        self.unbonded_at = datetime.now(UTC)

    def withdraw(self) -> None:
        """Complete unbonding and mark delegation withdrawn."""
        if self.status != DelegationStatus.UNBONDING:
            raise StakingError(f"cannot withdraw delegation in status {self.status}")
        self.status = DelegationStatus.WITHDRAWN

    def claim_rewards(self) -> Decimal:
        """Return and reset accumulated rewards."""
        amount = self.rewards
        self.rewards = Decimal("0")
        return amount


@dataclass
class YieldPosition:
    """Aggregated yield for an agent on a chain/token."""

    agent_id: str
    chain_id: str
    token: str
    total_staked: Decimal = field(default_factory=lambda: Decimal("0"))
    total_rewards: Decimal = field(default_factory=lambda: Decimal("0"))
    last_harvested: datetime = field(default_factory=lambda: datetime.now(UTC))

    def harvest(self, amount: Decimal) -> None:
        """Record a reward harvest."""
        if amount < 0:
            raise ValueError("harvest amount cannot be negative")
        self.total_rewards += amount
        self.last_harvested = datetime.now(UTC)


@dataclass
class StakingStrategy:
    """Policy that governs how an agent delegates stake across validators."""

    strategy_id: str
    agent_id: str
    chain_id: str = "ait-hub"
    target_validators: list[str] = field(default_factory=list)
    max_per_validator: Decimal | None = None
    min_yield_percent: Decimal = field(default_factory=lambda: Decimal("0"))
    auto_compound: bool = False
    rebalance_threshold: Decimal = field(default_factory=lambda: Decimal("5"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if self.max_per_validator is not None and self.max_per_validator <= 0:
            raise ValueError("max_per_validator must be positive")
        if self.min_yield_percent < 0:
            raise ValueError("min_yield_percent cannot be negative")
        if not (Decimal("0") <= self.rebalance_threshold <= Decimal("100")):
            raise ValueError("rebalance_threshold must be between 0 and 100")

    def allowed_validator(self, validator: str) -> bool:
        """Return True if the validator is in the target set."""
        return not self.target_validators or validator in self.target_validators

    def validate_delegation(self, delegation: Delegation) -> None:
        """Raise StakingError if a delegation violates the strategy."""
        if delegation.agent_id != self.agent_id:
            raise StakingError("delegation agent_id does not match strategy")
        if delegation.chain_id != self.chain_id:
            raise StakingError("delegation chain_id does not match strategy")
        if not self.allowed_validator(delegation.validator):
            raise StakingError(f"validator {delegation.validator} not allowed by strategy")
