"""AITBC shared models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class CoinRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass
class CoinRequest:
    """Stub coin request model."""

    id: str = ""
    wallet_address: str = ""
    amount: Decimal | None = None
    status: CoinRequestStatus = CoinRequestStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = ["CoinRequest", "CoinRequestStatus"]
