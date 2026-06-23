"""
Unit conversion utilities for AIT blockchain.

The blockchain uses compute-seconds as the base unit (1 AIT = 3600 seconds).
This module provides conversion functions between AIT and seconds for display
and transaction creation purposes.
"""

SECONDS_PER_AIT = 3600


def seconds_to_ait(seconds: int) -> float:
    """Convert compute-seconds to AIT."""
    return seconds / SECONDS_PER_AIT


def ait_to_seconds(ait: float) -> int:
    """Convert AIT to compute-seconds (for transaction creation)."""
    return int(ait * SECONDS_PER_AIT)


def format_ait(seconds: int) -> str:
    """Format compute-seconds as a human-readable AIT string."""
    ait = seconds_to_ait(seconds)
    if ait == int(ait):
        return f"{int(ait)} AIT"
    return f"{ait:.4f} AIT"
