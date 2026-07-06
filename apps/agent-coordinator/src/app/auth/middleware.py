"""
Authentication Middleware for AITBC Agent Coordinator.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.middleware``. Import from ``aitbc.auth`` directly
    in new code.
"""

import warnings

from aitbc.auth.middleware import (
    AuthenticationError,
    InputValidator,
    RateLimiter,
    SecurityHeaders,
    get_current_user,
    input_validator,
    rate_limiter,
    require_permissions,
    require_role,
    security_headers,
)

warnings.warn(
    "app.auth.middleware is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AuthenticationError",
    "InputValidator",
    "RateLimiter",
    "SecurityHeaders",
    "get_current_user",
    "input_validator",
    "rate_limiter",
    "require_permissions",
    "require_role",
    "security_headers",
]
