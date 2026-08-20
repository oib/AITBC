"""Confidential wallet helpers."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class ConfidentialWallet:
    """Stub confidential wallet."""

    address: str = ""
    balance: Decimal = Decimal("0")

    def deposit(self, amount: Decimal) -> dict[str, Any]:
        return {"status": "deposited", "amount": str(amount)}

    def withdraw(self, amount: Decimal) -> dict[str, Any]:
        return {"status": "withdrawn", "amount": str(amount)}


__all__ = ["ConfidentialWallet"]
