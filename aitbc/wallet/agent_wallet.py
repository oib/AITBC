"""Agent wallet abstraction for AITBC (v0.12.0 §A1).

Defines an agent-owned smart contract wallet with per-token balances. The
wallet is dependency-free and intended for use by the OpenClaw agent runtime,
``apps/coordinator-api`` economic domains, and the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .errors import InsufficientBalanceError


class WalletStatus(StrEnum):
    """Lifecycle status of an agent wallet."""

    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


@dataclass
class AgentWallet:
    """Agent-owned smart contract wallet abstraction.

    Tracks balances per token and exposes validated debit/credit operations.
    On-chain address and nonce fields are placeholders for the contract-backed
    implementation that Agent B will wire.
    """

    wallet_id: str
    agent_id: str
    chain_id: str
    address: str = ""
    status: WalletStatus | str = WalletStatus.ACTIVE
    nonce: int = 0
    balances: dict[str, Decimal] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = WalletStatus(self.status)
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if not self.chain_id:
            raise ValueError("chain_id is required")

    def balance(self, token: str) -> Decimal:
        """Return the wallet balance for a token."""
        return self.balances.get(token, Decimal("0"))

    def deposit(self, token: str, amount: Decimal) -> None:
        """Credit the wallet with ``amount`` of ``token``."""
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        self.balances[token] = self.balance(token) + amount

    def withdraw(self, token: str, amount: Decimal) -> None:
        """Debit the wallet by ``amount`` of ``token``."""
        if amount <= 0:
            raise ValueError("withdraw amount must be positive")
        if self.status != WalletStatus.ACTIVE:
            raise ValueError(f"wallet status is {self.status}, cannot withdraw")
        if amount > self.balance(token):
            raise InsufficientBalanceError(f"insufficient {token} balance: {self.balance(token)} < {amount}")
        self.balances[token] = self.balance(token) - amount

    def transfer(self, token: str, amount: Decimal, counterparty: AgentWallet) -> None:
        """Atomically move ``amount`` of ``token`` to another wallet."""
        self.withdraw(token, amount)
        counterparty.deposit(token, amount)
