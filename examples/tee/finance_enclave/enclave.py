"""Minimal finance enclave example for unit-test compatibility."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class Token:
    last_four: str
    bin_range: str
    encrypted_pan: bytes


class FinanceEnclave:
    def __init__(self, enclave_id: str) -> None:
        self.enclave_id = enclave_id
        self._started = False

    def start(self) -> None:
        self._started = True

    def tokenize(self, pan: str) -> Token:
        return Token(
            last_four=pan[-4:],
            bin_range=pan[:6],
            encrypted_pan=pan.encode(),
        )

    def authorize(self, token: Token, amount: Decimal, **kwargs: Any) -> dict[str, Any]:
        return {"approved": True, "amount": str(amount), "token_last_four": token.last_four}
