"""Rebalancing and reinvestment policy shared types for AITBC (v0.12.0 §A3).

Provides ``ReinvestmentPolicy``, ``ChainHoldings``, ``RebalanceConstraint``,
and ``RebalanceAction`` primitives plus a simple ``Rebalancer`` helper for
deciding when and how an agent moves AITBC across chains or into provider
capacity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import RebalanceError


class RebalanceActionType(StrEnum):
    """Types of rebalancing actions an agent may take."""

    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"
    STAKE = "stake"
    REINVEST = "reinvest"
    HOLD = "hold"


class ConstraintType(StrEnum):
    """Constraint categories for rebalancing decisions."""

    MAX_EXPOSURE = "max_exposure"
    MIN_LIQUIDITY = "min_liquidity"
    DIVERSIFICATION = "diversification"
    MIN_REINVEST_AMOUNT = "min_reinvest_amount"


@dataclass
class RebalanceConstraint:
    """A single constraint on rebalancing behavior."""

    constraint_type: ConstraintType | str
    parameter: str = ""
    limit: Decimal = field(default_factory=lambda: Decimal("0"))

    def __post_init__(self) -> None:
        if isinstance(self.constraint_type, str):
            self.constraint_type = ConstraintType(self.constraint_type)
        if self.limit < 0:
            raise ValueError("constraint limit cannot be negative")


@dataclass
class ChainHoldings:
    """Snapshot of an agent's holdings on a single chain/token."""

    chain_id: str
    token: str
    amount: Decimal = field(default_factory=lambda: Decimal("0"))
    target_percent: Decimal = field(default_factory=lambda: Decimal("0"))
    current_percent: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("amount cannot be negative")
        if not (Decimal("0") <= self.target_percent <= Decimal("100")):
            raise ValueError("target_percent must be between 0 and 100")
        if not (Decimal("0") <= self.current_percent <= Decimal("100")):
            raise ValueError("current_percent must be between 0 and 100")

    @property
    def deviation(self) -> Decimal:
        """Difference between current and target allocation percent."""
        return self.current_percent - self.target_percent


@dataclass
class ReinvestmentPolicy:
    """Policy that governs how an agent reinvests earnings."""

    policy_id: str
    agent_id: str
    target_allocations: dict[str, Decimal] = field(default_factory=dict)
    min_reinvest_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    max_exposure_per_chain: Decimal = field(default_factory=lambda: Decimal("100"))
    trigger_threshold: Decimal = field(default_factory=lambda: Decimal("5"))
    rebalance_frequency: int = 3600  # seconds
    chain_id: str = "ait-hub"
    constraints: list[RebalanceConstraint] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if self.min_reinvest_amount < 0:
            raise ValueError("min_reinvest_amount cannot be negative")
        if not (Decimal("0") <= self.max_exposure_per_chain <= Decimal("100")):
            raise ValueError("max_exposure_per_chain must be between 0 and 100")
        if not (Decimal("0") <= self.trigger_threshold <= Decimal("100")):
            raise ValueError("trigger_threshold must be between 0 and 100")
        total = sum(self.target_allocations.values(), Decimal("0"))
        if total > Decimal("100"):
            raise RebalanceError("target_allocations sum cannot exceed 100%")

    def target_for(self, chain_id: str) -> Decimal:
        """Return the target allocation percent for a chain."""
        return self.target_allocations.get(chain_id, Decimal("0"))


@dataclass
class RebalanceAction:
    """A concrete rebalancing instruction."""

    action_id: str
    action_type: RebalanceActionType | str
    source_chain: str
    target_chain: str
    token: str
    amount: Decimal = field(default_factory=lambda: Decimal("0"))
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.action_type, str):
            self.action_type = RebalanceActionType(self.action_type)
        if self.amount < 0:
            raise ValueError("amount cannot be negative")
        if not self.source_chain or not self.target_chain:
            raise ValueError("source_chain and target_chain are required")


class Rebalancer:
    """Compute rebalancing actions from holdings and a reinvestment policy."""

    def __init__(self, policy: ReinvestmentPolicy) -> None:
        self.policy = policy

    def plan(
        self,
        holdings: list[ChainHoldings],
        available_tokens: dict[str, Decimal] | None = None,
    ) -> list[RebalanceAction]:
        """Return a list of rebalance actions to align holdings with targets.

        ``available_tokens`` maps ``chain_id`` to unallocated token balance on
        that chain. Underweight chains are addressed first with available
        funds; if no funds are available, a transfer from an overweight chain
        is proposed.
        """
        if available_tokens is None:
            available_tokens = {}
        actions: list[RebalanceAction] = []
        total = sum(h.amount for h in holdings)
        if total <= 0:
            return actions

        for h in holdings:
            deviation = h.deviation
            move_amount = (abs(deviation) / Decimal("100")) * total
            if move_amount < self.policy.min_reinvest_amount:
                continue
            if abs(deviation) < self.policy.trigger_threshold:
                continue

            if deviation > 0:
                # Overweight chains are handled when paired with an underweight chain
                continue

            # Underweight: prefer reinvesting unallocated funds on this chain
            available = available_tokens.get(h.chain_id, Decimal("0"))
            if available >= move_amount:
                actions.append(
                    RebalanceAction(
                        action_id=f"rebal-buy-{h.chain_id}",
                        action_type=RebalanceActionType.REINVEST,
                        source_chain=h.chain_id,
                        target_chain=h.chain_id,
                        token=h.token,
                        amount=move_amount,
                        reason="increase underweight allocation",
                    )
                )
                continue

            # Fall back to transferring from an overweight chain
            overweight = next(
                (o for o in holdings if o.deviation > 0 and o.chain_id != h.chain_id and self._within_exposure(o.chain_id)),
                None,
            )
            if overweight is not None:
                actions.append(
                    RebalanceAction(
                        action_id=f"rebal-{overweight.chain_id}-{h.chain_id}",
                        action_type=RebalanceActionType.TRANSFER,
                        source_chain=overweight.chain_id,
                        target_chain=h.chain_id,
                        token=h.token,
                        amount=move_amount,
                        reason="reduce overweight",
                    )
                )

        return actions

    def _within_exposure(self, chain_id: str) -> bool:
        return self.policy.target_for(chain_id) <= self.policy.max_exposure_per_chain
