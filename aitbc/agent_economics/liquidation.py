"""Bond liquidation and provider off-boarding shared types (v0.13.0 §A2).

Provides ``LiquidationReason``, ``LiquidationEvent``, ``ProviderOffboarding``,
and helpers that consume the ``PerformanceBond`` lifecycle from
``aitbc.agent_economics.bonds``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .bonds import BondStatus, PerformanceBond
from .errors import LiquidationError


class LiquidationReason(StrEnum):
    """Canonical reasons for liquidating a performance bond."""

    INSUFFICIENT_COLLATERAL = "insufficient_collateral"
    SLA_VIOLATION = "sla_violation"
    FRAUD = "fraud"
    DOUBLE_SIGN = "double_sign"
    GOVERNANCE = "governance"
    VOLUNTARY_EXIT = "voluntary_exit"


class LiquidationStatus(StrEnum):
    """Status of a liquidation event."""

    PENDING = "pending"
    EXECUTED = "executed"
    APPEALED = "appealed"
    REVERSED = "reversed"


class OffboardingStatus(StrEnum):
    """Status of a provider off-boarding workflow."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class LiquidationEvent:
    """Record of a bond liquidation decision and execution."""

    event_id: str
    bond_id: str
    agent_id: str
    reason: LiquidationReason | str
    amount: Decimal
    status: LiquidationStatus | str = LiquidationStatus.PENDING
    timestamp: datetime = field(default_factory=datetime.utcnow)
    evidence: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.reason, str):
            self.reason = LiquidationReason(self.reason)
        if isinstance(self.status, str):
            self.status = LiquidationStatus(self.status)
        if self.amount < 0:
            raise ValueError("liquidation amount cannot be negative")

    def execute(self) -> None:
        """Mark the liquidation as executed."""
        if self.status != LiquidationStatus.PENDING:
            raise LiquidationError(f"cannot execute liquidation in status {self.status}")
        self.status = LiquidationStatus.EXECUTED


@dataclass
class ProviderOffboarding:
    """Provider off-boarding workflow triggered by liquidation or governance."""

    offboarding_id: str
    agent_id: str
    liquidation_event_id: str = ""
    reason: str = ""
    status: OffboardingStatus | str = OffboardingStatus.PENDING
    resources_released: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = OffboardingStatus(self.status)

    def start(self) -> None:
        """Move off-boarding to in-progress."""
        if self.status != OffboardingStatus.PENDING:
            raise LiquidationError(f"cannot start off-boarding in status {self.status}")
        self.status = OffboardingStatus.IN_PROGRESS

    def complete(self) -> None:
        """Mark off-boarding as completed."""
        if self.status != OffboardingStatus.IN_PROGRESS:
            raise LiquidationError(f"cannot complete off-boarding in status {self.status}")
        self.status = OffboardingStatus.COMPLETED
        self.resources_released = True


def liquidate_bond(
    bond: PerformanceBond,
    event_id: str,
    reason: LiquidationReason | str,
    amount: Decimal | None = None,
    evidence: str = "",
) -> LiquidationEvent:
    """Liquidate a bond and return a ``LiquidationEvent``.

    ponytail: this helper only updates in-memory state; on-chain settlement and
    slashing transfer are the responsibility of Agent B services.
    """
    if bond.status in {BondStatus.RELEASED, BondStatus.LIQUIDATED}:
        raise LiquidationError(f"bond already {bond.status}")
    if amount is None:
        amount = bond.amount
    if amount > bond.amount:
        raise LiquidationError("liquidation amount exceeds bond amount")

    bond.liquidate()
    event = LiquidationEvent(
        event_id=event_id,
        bond_id=bond.bond_id,
        agent_id=bond.agent_id,
        reason=reason,
        amount=amount,
        evidence=evidence,
    )
    event.execute()
    return event


def offboard_provider(
    event: LiquidationEvent,
    offboarding_id: str,
) -> ProviderOffboarding:
    """Create and start a provider off-boarding workflow from a liquidation."""
    if event.status != LiquidationStatus.EXECUTED:
        raise LiquidationError("liquidation must be executed before off-boarding")
    offboarding = ProviderOffboarding(
        offboarding_id=offboarding_id,
        agent_id=event.agent_id,
        liquidation_event_id=event.event_id,
        reason=str(event.reason),
    )
    offboarding.start()
    return offboarding
