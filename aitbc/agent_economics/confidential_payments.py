"""Confidential payment helpers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class ConfidentialPayment:
    """Stub confidential payment."""

    id: str = ""
    amount: Decimal = Decimal("0")
    sender: str = ""
    recipient: str = ""
    status: str = "pending"


def validate_payment(payment: Any) -> bool:
    """Validate a confidential payment."""
    return isinstance(payment, ConfidentialPayment)


def settle_payment(payment: ConfidentialPayment) -> dict[str, Any]:
    """Settle a confidential payment."""
    return {"status": "settled", "payment_id": payment.id}


__all__ = ["ConfidentialPayment", "settle_payment", "validate_payment"]
