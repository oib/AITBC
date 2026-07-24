"""Slashing condition validators for AITBC (v0.12.0 §A2).

Provides primitives for validating slashing conditions and computing penalty
amounts applied to ``PerformanceBond`` and ``StakeAccount`` instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .bonds import BondStatus, PerformanceBond, StakeAccount, StakeStatus
from .errors import SlashError


class SlashReason(StrEnum):
    """Canonical slashing reasons."""

    DOWNTIME = "downtime"
    FRAUD = "fraud"
    DOUBLE_SIGN = "double_sign"
    MISCONFIGURATION = "misconfiguration"
    MISSED_PROOF = "missed_proof"


@dataclass
class SlashingCondition:
    """A rule that defines when and how much to slash."""

    condition_id: str
    reason: SlashReason | str
    penalty_percent: Decimal
    description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.reason, str):
            self.reason = SlashReason(self.reason)
        if not (Decimal("0") <= self.penalty_percent <= Decimal("100")):
            raise ValueError("penalty_percent must be between 0 and 100")


@dataclass
class SlashEvent:
    """A recorded slashing decision."""

    event_id: str
    bond_id: str
    reason: SlashReason | str
    penalty_percent: Decimal
    evidence: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.reason, str):
            self.reason = SlashReason(self.reason)
        if not (Decimal("0") <= self.penalty_percent <= Decimal("100")):
            raise ValueError("penalty_percent must be between 0 and 100")


def compute_slash_amount(amount: Decimal, penalty_percent: Decimal) -> Decimal:
    """Return the amount to slash given a principal and penalty percent."""
    if penalty_percent < 0 or penalty_percent > 100:
        raise SlashError("penalty_percent must be between 0 and 100")
    return (amount * penalty_percent) / Decimal("100")


def validate_slash_event(
    bond: PerformanceBond,
    event: SlashEvent,
    allowed_conditions: list[SlashingCondition] | None = None,
) -> None:
    """Validate that a slash event can be applied to a bond.

    Raises ``SlashError`` if the bond is not in a slashable state, the reason
    is unknown, or the penalty percent exceeds the configured maximum.
    """
    if bond.status not in {BondStatus.ACTIVE, BondStatus.LOCKED}:
        raise SlashError(f"bond status {bond.status} is not slashable")
    if bond.bond_id != event.bond_id:
        raise SlashError("slash event bond_id does not match bond")

    if allowed_conditions:
        matching = [c for c in allowed_conditions if c.reason == event.reason]
        if not matching:
            raise SlashError(f"reason {event.reason} is not in allowed conditions")
        max_penalty = max(c.penalty_percent for c in matching)
        if event.penalty_percent > max_penalty:
            raise SlashError(f"penalty {event.penalty_percent}% exceeds max {max_penalty}%")


def slash_bond(
    bond: PerformanceBond,
    event: SlashEvent,
    allowed_conditions: list[SlashingCondition] | None = None,
) -> Decimal:
    """Validate and apply a slash to a bond, returning the slashed amount."""
    validate_slash_event(bond, event, allowed_conditions)
    bond.slash()
    return compute_slash_amount(bond.amount, event.penalty_percent)


def slash_stake(
    stake: StakeAccount,
    event: SlashEvent,
    allowed_conditions: list[SlashingCondition] | None = None,
) -> Decimal:
    """Apply a slash to a stake account and return the slashed amount."""
    if stake.status != StakeStatus.ACTIVE:
        raise SlashError(f"stake status {stake.status} is not slashable")
    if allowed_conditions:
        matching = [c for c in allowed_conditions if c.reason == event.reason]
        if not matching:
            raise SlashError(f"reason {event.reason} is not in allowed conditions")
        max_penalty = max(c.penalty_percent for c in matching)
        if event.penalty_percent > max_penalty:
            raise SlashError(f"penalty {event.penalty_percent}% exceeds max {max_penalty}%")
    slashed = compute_slash_amount(stake.amount, event.penalty_percent)
    stake.amount -= slashed
    return slashed
