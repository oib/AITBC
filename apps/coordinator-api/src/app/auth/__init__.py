"""
Authentication module for Coordinator API
"""

import warnings

from .dependencies import (
    AdminDep,
    AuthDep,
    ClientDep,
    MinerDep,
    require_admin,
    require_auth,
    require_client,
    require_miner,
)
from .jwt_auth import create_access_token, jwt_auth, verify_access_token
from .middleware import AuthMiddleware
from .security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, check_role_match, get_auth_level


def get_api_key() -> str:
    """
    DEPRECATED: Legacy auth function removed for security.

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


__all__ = [
    "jwt_auth",
    "create_access_token",
    "verify_access_token",
    "require_auth",
    "require_admin",
    "require_client",
    "require_miner",
    "AuthDep",
    "AdminDep",
    "ClientDep",
    "MinerDep",
    "AuthLevel",
    "get_auth_level",
    "check_role_match",
    "ROUTE_SECURITY_MATRIX",
    "AuthMiddleware",
]
