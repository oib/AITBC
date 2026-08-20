"""AITBC shared utilities."""

from decimal import Decimal

AIT_PER_SECOND = Decimal("0.00000001")  # 1e-8 AIT per compute-second
SECONDS_PER_AIT = Decimal("100000000")  # 1 AIT = 100,000,000 compute-seconds


def format_ait(value: int | float | Decimal | None) -> str:
    """Convert compute-seconds into a human-readable AIT string."""
    if value is None:
        return "N/A"
    if isinstance(value, Decimal):
        seconds = value
    else:
        seconds = Decimal(str(value))
    return f"{seconds / SECONDS_PER_AIT:.8f} AIT"


def ait_to_seconds(amount: int | float | str | Decimal) -> int:
    """Convert an AIT amount (float or string) into compute-seconds."""
    if isinstance(amount, int):
        return int(Decimal(amount) * SECONDS_PER_AIT)
    if isinstance(amount, float):
        return int(Decimal(str(amount)) * SECONDS_PER_AIT)
    if isinstance(amount, str):
        return int(Decimal(amount) * SECONDS_PER_AIT)
    if isinstance(amount, Decimal):
        return int(amount * SECONDS_PER_AIT)
    raise TypeError(f"Cannot convert {type(amount)} to compute-seconds")


__all__ = ["format_ait", "ait_to_seconds", "AIT_PER_SECOND", "SECONDS_PER_AIT"]
