"""AITBC Exception Hierarchy
Base exception classes for AITBC applications

The classes themselves now live in the dependency-free ``aitbc_errors`` leaf
package. This module re-exports the *same class objects*, so
``aitbc.exceptions.NetworkError is aitbc_errors.NetworkError`` and every
existing ``except`` / ``isinstance`` check is unaffected.

Application code can keep importing from here. Library code that should not
pay for ``aitbc/__init__``'s framework imports (fastapi, sqlalchemy,
prometheus_client) should import from ``aitbc_errors`` directly.
"""

from aitbc_errors import (
    AITBCError,
    ConfigurationError,
    NetworkError,
    AuthenticationError,
    EncryptionError,
    DatabaseError,
    ValidationError,
    BridgeError,
    RetryError,
    CircuitBreakerOpenError,
    RateLimitError,
)

__all__ = [
    "AITBCError",
    "ConfigurationError",
    "NetworkError",
    "AuthenticationError",
    "EncryptionError",
    "DatabaseError",
    "ValidationError",
    "BridgeError",
    "RetryError",
    "CircuitBreakerOpenError",
    "RateLimitError",
]
