"""Escrow and allowance primitives for AITBC (v0.12.0 §A1).

Supports lease, storage, and compute payments between agents and providers.
Escrows are held off-chain in these shared types and settled on-chain by
Agent B services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import AllowanceExceededError, EscrowError


class EscrowStatus(StrEnum):
    """Lifecycle status of an escrow."""

    PENDING = "pending"
    FUNDED = "funded"
    RELEASED = "released"
    REFUNDED = "refunded"
    DISPUTED = "disputed"
    EXPIRED = "expired"


@dataclass
class Escrow:
    """Escrow record for a single payment between payer and payee."""

    escrow_id: str
    payer_id: str
    payee_id: str
    token: str
    amount: Decimal
    chain_id: str = "ait-hub"
    status: EscrowStatus | str = EscrowStatus.PENDING
    purpose: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(days=1))
    released_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = EscrowStatus(self.status)
        if self.amount <= 0:
            raise ValueError("escrow amount must be positive")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if the escrow has passed its expiration time."""
        if now is None:
            now = datetime.utcnow()
        return (
            self.status
            not in {
                EscrowStatus.RELEASED,
                EscrowStatus.REFUNDED,
                EscrowStatus.DISPUTED,
            }
            and self.expires_at <= now
        )

    def release(self, now: datetime | None = None) -> None:
        """Release escrow funds to the payee."""
        if now is None:
            now = datetime.utcnow()
        if self.status == EscrowStatus.RELEASED:
            raise EscrowError("escrow already released")
        if self.is_expired(now):
            raise EscrowError("escrow has expired")
        self.status = EscrowStatus.RELEASED
        self.released_at = now

    def refund(self, now: datetime | None = None) -> None:
        """Return escrow funds to the payer."""
        if now is None:
            now = datetime.utcnow()
        if self.status in {EscrowStatus.RELEASED, EscrowStatus.REFUNDED}:
            raise EscrowError(f"escrow already {self.status}")
        self.status = EscrowStatus.REFUNDED
        self.released_at = now


@dataclass
class EscrowAllowance:
    """Approved spending allowance from an owner to a spender."""

    allowance_id: str
    owner_id: str
    spender_id: str
    token: str
    amount: Decimal
    used: Decimal = field(default_factory=lambda: Decimal("0"))
    chain_id: str = "ait-hub"
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.amount < 0 or self.used < 0:
            raise ValueError("amount and used cannot be negative")
        if self.used > self.amount:
            raise ValueError("used cannot exceed amount")

    @property
    def remaining(self) -> Decimal:
        """Amount still available to spend."""
        return self.amount - self.used

    def spend(self, amount: Decimal) -> None:
        """Record a spend against the allowance."""
        if amount <= 0:
            raise ValueError("spend amount must be positive")
        if amount > self.remaining:
            raise AllowanceExceededError(f"allowance exceeded: remaining {self.remaining} < {amount}")
        self.used += amount
