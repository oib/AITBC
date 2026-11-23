"""AITBC wallet and escrow shared types (v0.12.0 §A1).

Provides:
- AgentWallet: agent-owned smart contract wallet abstraction
- Escrow, EscrowAllowance: escrow and allowance primitives for lease, storage,
  and compute payments
- Wallet and escrow domain exceptions
"""

from __future__ import annotations

from .agent_wallet import AgentWallet, WalletStatus
from .errors import (
    AgentWalletError,
    AllowanceExceededError,
    EscrowError,
    InsufficientBalanceError,
    WalletError,
)
from .escrow import Escrow, EscrowAllowance, EscrowStatus

__all__ = [
    "AgentWallet",
    "AgentWalletError",
    "AllowanceExceededError",
    "Escrow",
    "EscrowAllowance",
    "EscrowError",
    "EscrowStatus",
    "InsufficientBalanceError",
    "WalletError",
    "WalletStatus",
]
