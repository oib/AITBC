"""
DEPRECATED: Legacy auth module

This module is deprecated. Use `app.auth` (JWT-based) instead.
The old `get_api_key()` has been removed to prevent accidental use of hardcoded credentials.
"""

import warnings


def get_api_key() -> str:
    """
    DEPRECATED: This function is no longer supported.

    The old hardcoded "test-key" fallback has been removed as a security measure.
    Use JWT-based authentication via `app.auth` instead:

        from app.auth import create_access_token, verify_access_token

    Raises:
        RuntimeError: Always, to prevent accidental use.
    """
    warnings.warn(
        "get_api_key() is deprecated and removed. Use JWT auth from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise RuntimeError(
        "Hardcoded API keys are disabled. Migrate to JWT authentication: "
        "from app.auth import create_access_token, verify_access_token"
    )
