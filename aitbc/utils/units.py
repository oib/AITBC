"""
Unit conversion utilities for AIT blockchain.

The blockchain uses compute-units as the base unit (1 AIT = 36_000_000 units).
This module provides conversion functions between AIT and units for display
and transaction creation purposes.

Compute-units are an **integer** on the wire, so this is the boundary where a user's
``--amount`` becomes the number the chain settles. ``ait_to_units`` truncates the
Decimal product to an integer; callers that need a minimum positive value should
round up to 1 unit.
"""

from decimal import Decimal

UNITS_PER_AIT = 36_000_000

DEFAULT_TX_FEE_AIT = Decimal("0.01")
DEFAULT_TX_FEE_UNITS = int(Decimal(str(DEFAULT_TX_FEE_AIT)) * UNITS_PER_AIT)

LIQUIDITY_FEE_UNITS = UNITS_PER_AIT  # 1 AIT default for liquidity deposit/claim/withdraw

DEFAULT_FAUCET_AIT = Decimal("1_000_000")
DEFAULT_FAUCET_UNITS = int(Decimal(str(DEFAULT_FAUCET_AIT)) * UNITS_PER_AIT)

MAX_FAUCET_AIT = Decimal("10_000_000")
MAX_FAUCET_UNITS = int(Decimal(str(MAX_FAUCET_AIT)) * UNITS_PER_AIT)


def units_to_ait(units: Decimal | float | int | str) -> Decimal:
    """Convert compute-units to AIT."""
    return Decimal(str(units)) / UNITS_PER_AIT


def ait_to_units(ait: Decimal | float | int | str) -> int:
    """Convert AIT to compute-units (for transaction creation).

    Accepts a float for callers that still hold one -- ``str()`` first, so a float's
    shortest repr is what gets parsed rather than its full binary expansion.
    """
    return int(Decimal(str(ait)) * UNITS_PER_AIT)


def format_ait(units: Decimal | float | int | str) -> str:
    """Format compute-units as a human-readable AIT string.

    Whole AIT values are shown without decimals. Sub-AIT values are shown with up to
    8 decimal places and trailing zeros stripped so that very small amounts (e.g.
    a single compute-unit) remain visible.
    """
    ait = units_to_ait(units)
    if ait == int(ait):
        return f"{int(ait)} AIT"
    ait_str = f"{ait:.8f}".rstrip("0").rstrip(".")
    return f"{ait_str} AIT"
