"""Shared exceptions for the ``aitbc`` package."""


class AITBCError(Exception):
    """Base exception for AITBC packages."""


class NetworkError(AITBCError):
    """Raised when an HTTP/network call fails."""


class ValidationError(AITBCError):
    """Raised when input validation fails."""
