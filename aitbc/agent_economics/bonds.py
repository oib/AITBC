"""Performance bond and staking shared types for AITBC (v0.12.0 §A2, v0.13.0 §A2).

Defines ``PerformanceBond`` and ``StakeAccount`` primitives consumed by the
OpenClaw agent runtime, ``apps/coordinator-api`` governance/economic domains,
and the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import BondError


class BondStatus(StrEnum):
    """Lifecycle status of a performance bond."""

    PENDING = "pending"
    ACTIVE = "active"
    LOCKED = "locked"
    SLASHED = "slashed"
    RELEASED = "released"
    PARTIALLY_RELEASED = "partially_released"
    LIQUIDATED = "liquidated"
    EXPIRED = "expired"


class StakeStatus(StrEnum):
    """Lifecycle status of a stake account."""

    PENDING = "pending"
    ACTIVE = "active"
    UNSTAKING = "unstaking"
    UNSTAKED = "unstaked"


@dataclass
class PerformanceBond:
    """Performance bond posted by a provider/agent to guarantee service.

    The bond transitions through pending → active → locked, then to
    released/slashed/liquidated. State transitions are validated.
    """

    bond_id: str
    agent_id: str
    amount: Decimal
    token: str
    chain_id: str = "ait-hub"
    status: BondStatus | str = BondStatus.PENDING
    collateral_address: str = ""
    locked_until: datetime | None = None
    slash_conditions: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = BondStatus(self.status)
        if self.amount <= 0:
            raise ValueError("bond amount must be positive")
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def activate(self) -> None:
        """Move bond from pending to active."""
        if self.status != BondStatus.PENDING:
            raise BondError(f"cannot activate bond in status {self.status}")
        self.status = BondStatus.ACTIVE

    def lock(self, until: datetime, now: datetime | None = None) -> None:
        """Lock the bond until ``until``."""
        if now is None:
            now = datetime.now(UTC)
        if self.status not in {BondStatus.PENDING, BondStatus.ACTIVE}:
            raise BondError(f"cannot lock bond in status {self.status}")
        if until <= now:
            raise BondError("locked_until must be in the future")
        self.status = BondStatus.LOCKED
        self.locked_until = until

    def release(self, now: datetime | None = None) -> None:
        """Release the remaining bond amount back to the agent."""
        if now is None:
            now = datetime.now(UTC)
        if self.status not in {
            BondStatus.ACTIVE,
            BondStatus.LOCKED,
            BondStatus.EXPIRED,
            BondStatus.PARTIALLY_RELEASED,
        }:
            raise BondError(f"cannot release bond in status {self.status}")
        if self.status == BondStatus.LOCKED and self.locked_until is not None:
            if self.locked_until > now:
                raise BondError("bond is still locked")
        self.status = BondStatus.RELEASED

    def top_up(self, amount: Decimal) -> None:
        """Add collateral to the bond."""
        if amount <= 0:
            raise ValueError("top-up amount must be positive")
        if self.status not in {
            BondStatus.PENDING,
            BondStatus.ACTIVE,
            BondStatus.LOCKED,
            BondStatus.SLASHED,
            BondStatus.PARTIALLY_RELEASED,
        }:
            raise BondError(f"cannot top up bond in status {self.status}")
        self.amount += amount

    def partial_release(self, amount: Decimal, now: datetime | None = None) -> None:
        """Release part of the bond collateral."""
        if now is None:
            now = datetime.now(UTC)
        if amount <= 0:
            raise ValueError("partial release amount must be positive")
        if self.status not in {
            BondStatus.ACTIVE,
            BondStatus.LOCKED,
            BondStatus.EXPIRED,
            BondStatus.PARTIALLY_RELEASED,
        }:
            raise BondError(f"cannot partially release bond in status {self.status}")
        if self.status == BondStatus.LOCKED and self.locked_until is not None:
            if self.locked_until > now:
                raise BondError("bond is still locked")
        if amount > self.amount:
            raise BondError("partial release amount exceeds bond amount")
        self.amount -= amount
        if self.amount > 0:
            self.status = BondStatus.PARTIALLY_RELEASED
        else:
            self.status = BondStatus.RELEASED

    def slash(self) -> None:
        """Mark the bond as slashed."""
        if self.status not in {BondStatus.ACTIVE, BondStatus.LOCKED}:
            raise BondError(f"cannot slash bond in status {self.status}")
        self.status = BondStatus.SLASHED

    def liquidate(self) -> None:
        """Liquidate the bond to cover a shortfall."""
        if self.status not in {
            BondStatus.ACTIVE,
            BondStatus.LOCKED,
            BondStatus.SLASHED,
            BondStatus.PARTIALLY_RELEASED,
        }:
            raise BondError(f"cannot liquidate bond in status {self.status}")
        self.status = BondStatus.LIQUIDATED

    def mark_expired(self, now: datetime | None = None) -> None:
        """Mark an expired locked bond."""
        if now is None:
            now = datetime.now(UTC)
        if self.status == BondStatus.LOCKED and self.locked_until is not None:
            if self.locked_until <= now:
                self.status = BondStatus.EXPIRED


@dataclass
class StakeAccount:
    """Agent stake delegated to a validator."""

    stake_id: str
    agent_id: str
    validator: str
    amount: Decimal
    token: str
    chain_id: str = "ait-hub"
    status: StakeStatus | str = StakeStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    unstaked_at: datetime | None = None
    reward: Decimal = field(default_factory=lambda: Decimal("0"))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = StakeStatus(self.status)
        if self.amount <= 0:
            raise ValueError("stake amount must be positive")
        if not self.agent_id or not self.validator:
            raise ValueError("agent_id and validator are required")
        if self.reward < 0:
            raise ValueError("reward cannot be negative")

    def activate(self) -> None:
        """Move stake from pending to active."""
        if self.status != StakeStatus.PENDING:
            raise BondError(f"cannot activate stake in status {self.status}")
        self.status = StakeStatus.ACTIVE

    def start_unstaking(self) -> None:
        """Begin the unstaking process."""
        if self.status != StakeStatus.ACTIVE:
            raise BondError(f"cannot unstake from status {self.status}")
        self.status = StakeStatus.UNSTAKING

    def finalize_unstake(self) -> None:
        """Complete unstaking."""
        if self.status != StakeStatus.UNSTAKING:
            raise BondError(f"cannot finalize unstake from status {self.status}")
        self.status = StakeStatus.UNSTAKED
        self.unstaked_at = datetime.now(UTC)
