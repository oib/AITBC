"""Exact monetary helpers for wallet and cross-chain operations (B4)."""

from decimal import Decimal, InvalidOperation
from typing import Any


def parse_decimal(value: Decimal | float | int | str | Any, name: str = "amount") -> Decimal:
    """Parse a monetary value into a Decimal without intermediate float loss.

    Float inputs are rejected because binary floats cannot represent decimal
    fractions exactly.  Use ``Decimal``/``str``/``int`` at API boundaries.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid {name}: {value!r}") from exc
    if isinstance(value, float):
        raise TypeError(f"Float {name} is not accepted; pass a Decimal or string")
    raise TypeError(f"Unsupported {name} type: {type(value).__name__}")


def to_atomic_units(amount: Decimal | float | int | str, decimals: int = 18) -> int:
    """Convert a human-readable decimal amount to integer atomic units.

    Args:
        amount: The amount in whole units (e.g., ETH, AITBC).
        decimals: Number of decimal places the chain uses (18 for most EVM chains).

    Returns:
        Integer atomic units (e.g., wei).

    Raises:
        ValueError: If the amount is not positive or overflows a 128-bit integer.
    """
    amount_dec = parse_decimal(amount)
    if amount_dec.is_nan() or amount_dec.is_infinite():
        raise ValueError("Amount must be a finite number")
    if amount_dec <= 0:
        raise ValueError("Amount must be positive")
    factor = Decimal(10) ** decimals
    atomic = (amount_dec * factor).to_integral_value()
    if atomic >= Decimal(2) ** 128:
        raise ValueError("Amount overflows 128-bit unsigned integer")
    return int(atomic)


def from_atomic_units(amount: int | str, decimals: int = 18) -> Decimal:
    """Convert integer atomic units to a human-readable Decimal."""
    atomic = parse_decimal(amount, name="atomic amount").to_integral_value()
    if atomic < 0:
        raise ValueError("Atomic amount cannot be negative")
    return atomic / (Decimal(10) ** decimals)


def validate_positive_amount(amount: Decimal | float | int | str, max_value: Decimal | None = None) -> Decimal:
    """Validate and return a positive, bounded Decimal amount."""
    amount_dec = parse_decimal(amount)
    if amount_dec <= 0:
        raise ValueError("Amount must be positive")
    if max_value is not None and amount_dec > max_value:
        raise ValueError(f"Amount exceeds maximum {max_value}")
    return amount_dec
