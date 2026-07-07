"""
Authentication module for Coordinator API.

Re-exports from the canonical ``aitbc.auth`` package. The former app-local
shim submodules (jwt_auth, dependencies, middleware, security_matrix) were
deleted in v0.10.9 — import from ``aitbc.auth`` directly in new code.
"""

import warnings

from aitbc.auth import (
    AdminDep,
    AuthDep,
    AuthLevel,
    AuthMiddleware,
    ClientDep,
    MinerDep,
    ROUTE_SECURITY_MATRIX,
    check_role_match,
    create_access_token,
    get_auth_level,
    get_jwt_auth,
    require_admin,
    require_auth,
    require_client,
    require_miner,
    verify_access_token,
)

# Global JWT auth instance (preserves the old ``app.auth.jwt_auth`` interface)
jwt_auth = get_jwt_auth()


def get_api_key() -> str:
    """
    DEPRECATED: Legacy auth function removed for security.

    The old hardcoded "test-key" fallback has been removed as a security measure.
    Use JWT-based authentication via ``aitbc.auth`` instead:

        from aitbc.auth import create_access_token, verify_access_token

    Raises:
        RuntimeError: Always, to prevent accidental use.
    """
    warnings.warn(
        "get_api_key() is deprecated and removed. Use JWT auth from aitbc.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise RuntimeError(
        "Hardcoded API keys are disabled. Migrate to JWT authentication: "
        "from aitbc.auth import create_access_token, verify_access_token"
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
