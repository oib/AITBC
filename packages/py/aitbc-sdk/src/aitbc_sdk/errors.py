"""AITBC SDK exception types."""

from __future__ import annotations


class AITBCError(Exception):
    """Base exception for all AITBC SDK errors."""


class AITBCConnectionError(AITBCError):
    """Raised when the SDK cannot reach the coordinator API."""


class AITBCRateLimitError(AITBCError):
    """Raised when a request is rate limited by the coordinator API."""
