"""Decimal utilities for AITBC services (v0.10.7 §B7).

Provides ``to_decimal()`` for safe conversion of str/int/float to ``Decimal``,
avoiding the float-to-Decimal precision trap.
"""

from decimal import Decimal


def to_decimal(value) -> Decimal:
    """Convert a value to Decimal, handling str/int/float safely.

    Using ``str()`` first avoids the float-to-Decimal precision trap
    (e.g., ``Decimal(0.1)`` gives ``0.1000000000000000055511151231257827...``,
    but ``Decimal(str(0.1))`` gives ``0.1``).
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
