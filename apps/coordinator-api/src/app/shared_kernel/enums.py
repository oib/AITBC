"""Shared cross-context enumerations (value objects).

These enums represent shared vocabulary used by multiple bounded contexts.
They are value objects (no identity, no persistence) and are safe to share
via the shared kernel.
"""

from enum import StrEnum


class TransactionPriority(StrEnum):
    """Transaction priority levels — shared by cross_chain and marketplace contexts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"
