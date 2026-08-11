"""
Unit conversion utilities for AIT blockchain.

The blockchain uses compute-seconds as the base unit (1 AIT = 3600 seconds).
This module provides conversion functions between AIT and seconds for display
and transaction creation purposes.

Compute-seconds are an **integer** on the wire, so this is the boundary where a user's
``--amount`` becomes the number the chain settles. ``ait_to_seconds`` used to compute it as
``int(ait * 3600)`` on a float, which truncates on the low side whenever the product lands
just under an integer:

    ait_to_seconds(0.5025)   ->  1808   (float: 0.5025 * 3600 == 1808.9999999999998)
                             ->  1809   exact

1402 of the million four-decimal inputs between 0.0001 and 100.0000 lose a compute-second
that way -- always in the same direction, always the sender's. The conversion is done in
``Decimal`` now, so the truncation only ever discards a genuine fraction of a second.
"""

from decimal import Decimal

SECONDS_PER_AIT = 3600


def seconds_to_ait(seconds: Decimal | float | int | str) -> Decimal:
    """Convert compute-seconds to AIT."""
    return Decimal(str(seconds)) / SECONDS_PER_AIT


def ait_to_seconds(ait: Decimal | float | int | str) -> int:
    """Convert AIT to compute-seconds (for transaction creation).

    Accepts a float for callers that still hold one -- ``str()`` first, so a float's
    shortest repr is what gets parsed rather than its full binary expansion.
    """
    return int(Decimal(str(ait)) * SECONDS_PER_AIT)


def format_ait(seconds: Decimal | float | int | str) -> str:
    """Format compute-seconds as a human-readable AIT string."""
    ait = seconds_to_ait(seconds)
    if ait == int(ait):
        return f"{int(ait)} AIT"
    return f"{ait:.4f} AIT"
