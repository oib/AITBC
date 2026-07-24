"""Domain exceptions for aitbc.wallet (v0.12.0 §A1)."""

from __future__ import annotations


class WalletError(Exception):
    """Base exception for wallet domain errors."""


class AgentWalletError(WalletError):
    """Agent wallet operation error."""


class InsufficientBalanceError(AgentWalletError):
    """Wallet does not hold enough funds for the requested operation."""


class EscrowError(WalletError):
    """Escrow operation error."""


class AllowanceExceededError(EscrowError):
    """Spending exceeds the approved escrow allowance."""
