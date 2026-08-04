"""
Route security matrix — defines auth requirements for all routes.

Extracted from ``apps/coordinator-api/src/app/auth/security_matrix.py``.
Services can use this directly or define their own matrix.
"""

from __future__ import annotations

import fnmatch
from enum import Enum


class AuthLevel(Enum):
    """Authentication levels."""

    NONE = "none"  # No authentication required
    ANY = "any"  # Any valid JWT token
    ADMIN = "admin"  # Admin role required
    CLIENT = "client"  # Client role required
    MINER = "miner"  # Miner role required
    ADMIN_OR_CLIENT = "admin_or_client"  # Admin or client role
    DENY = "deny"  # Default-deny for unregistered routes


# Default route security matrix (coordinator-api routes).
# Services can override with their own matrix by passing it to get_auth_level.
# Patterns are Unix-shell style wildcards (``*`` matches any path segment).
# More specific patterns should be listed before broader wildcard patterns.
ROUTE_SECURITY_MATRIX: dict[str, AuthLevel] = {
    # Public infrastructure routes
    "/health": AuthLevel.NONE,
    "/docs": AuthLevel.NONE,
    "/openapi.json": AuthLevel.NONE,
    "/redoc": AuthLevel.NONE,
    "/v1/health": AuthLevel.NONE,
    "/v1/health/live": AuthLevel.NONE,
    "/v1/health/ready": AuthLevel.NONE,
    "/v1/status": AuthLevel.NONE,
    "/v1/sync-status": AuthLevel.NONE,
    # Public authentication routes
    "/v1/register": AuthLevel.NONE,
    "/v1/login": AuthLevel.NONE,
    "/v1/auth/nonce": AuthLevel.NONE,
    # Public read-only market data
    "/v1/exchange/rates": AuthLevel.NONE,
    "/v1/exchange/market-stats": AuthLevel.NONE,
    # Public blockchain explorer data
    "/v1/explorer/*": AuthLevel.NONE,
    "/v1/blocks/*": AuthLevel.NONE,
    "/v1/transactions/*": AuthLevel.NONE,
    "/v1/accounts/*": AuthLevel.NONE,
    "/v1/validators": AuthLevel.NONE,
    "/v1/supply": AuthLevel.NONE,
    # Public marketplace listings
    "/v1/marketplace/offers": AuthLevel.NONE,
    "/v1/marketplace/stats": AuthLevel.NONE,
    "/v1/marketplace/plugins": AuthLevel.NONE,
    "/v1/marketplace/gpu/list": AuthLevel.NONE,
    "/v1/marketplace/orders": AuthLevel.NONE,
    "/v1/marketplace/pricing/*": AuthLevel.NONE,
    "/v1/marketplace/miner-offers": AuthLevel.NONE,
    "/v1/offers": AuthLevel.NONE,
    # Admin routes
    "/v1/admin/*": AuthLevel.ADMIN,
    # Miner routes
    "/v1/miners/*": AuthLevel.MINER,
    "/v1/marketplace/gpu/register": AuthLevel.MINER,
    "/v1/marketplace/gpu/sell": AuthLevel.MINER,
    "/v1/marketplace/gpu/*/release": AuthLevel.MINER,
    "/v1/marketplace/gpu/*/confirm": AuthLevel.MINER,
    "/v1/marketplace/gpu/*/delete": AuthLevel.MINER,
    "/v1/marketplace/gpu/sync-offers": AuthLevel.MINER,
    # Client routes
    "/v1/marketplace/gpu/purchase": AuthLevel.CLIENT,
    "/v1/marketplace/gpu/*/book": AuthLevel.CLIENT,
    "/v1/marketplace/gpu/bid": AuthLevel.CLIENT,
    "/v1/payments/send": AuthLevel.CLIENT,
    "/v1/payments/*": AuthLevel.CLIENT,
    "/v1/exchange/*": AuthLevel.CLIENT,
    # Admin or client routes
    "/v1/governance*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/staking*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/stake*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/rewards*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/developer-platform*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/portfolio*": AuthLevel.ADMIN_OR_CLIENT,
    "/v1/trading*": AuthLevel.ADMIN_OR_CLIENT,
    # Any authenticated token
    "/v1/cross-chain*": AuthLevel.ANY,
    "/v1/agent-identity*": AuthLevel.ANY,
    "/v1/ipfs*": AuthLevel.ANY,
    "/v1/inference*": AuthLevel.ANY,
    "/v1/agents*": AuthLevel.ANY,
    "/v1/agent-performance*": AuthLevel.ANY,
    "/v1/multi-modal-rl*": AuthLevel.ANY,
    "/v1/edge-gpu*": AuthLevel.ANY,
    "/v1/bounty*": AuthLevel.ANY,
    "/v1/reputation*": AuthLevel.ANY,
    "/v1/knowledge*": AuthLevel.ANY,
    "/v1/services*": AuthLevel.ANY,
    "/v1/disputes*": AuthLevel.ANY,
    "/v1/zk*": AuthLevel.ANY,
    "/v1/fhe*": AuthLevel.ANY,
    "/v1/ml-zk*": AuthLevel.ANY,
    "/v1/confidential*": AuthLevel.ANY,
    "/v1/security*": AuthLevel.ANY,
    "/v1/blockchain*": AuthLevel.ANY,
    "/v1/islands*": AuthLevel.ANY,
    "/v1/web-vitals*": AuthLevel.ANY,
    "/v1/monitoring*": AuthLevel.ANY,
    "/v1/users/me": AuthLevel.ANY,
    "/v1/users/*/transactions": AuthLevel.ANY,
    "/v1/users/*/balance": AuthLevel.ANY,
}


def get_auth_level(path: str, matrix: dict[str, AuthLevel] | None = None) -> AuthLevel:
    """Get required auth level for a given path.

    Args:
        path: Request path.
        matrix: Optional custom security matrix. Defaults to ROUTE_SECURITY_MATRIX.

    Returns:
        Required auth level.
    """
    route_matrix = matrix or ROUTE_SECURITY_MATRIX

    # Check exact match first
    if path in route_matrix:
        return route_matrix[path]

    # Check wildcard patterns in order
    for pattern, level in route_matrix.items():
        if "*" in pattern and fnmatch.fnmatch(path, pattern):
            return level

    # Unregistered routes default to deny (CORE-03)
    return AuthLevel.DENY


def check_role_match(required_level: AuthLevel, user_role: str | None) -> bool:
    """Check if user role matches required auth level.

    Args:
        required_level: Required auth level.
        user_role: User's role from token.

    Returns:
        True if role matches, False otherwise.
    """
    if required_level == AuthLevel.NONE:
        return True
    if required_level == AuthLevel.ANY:
        return user_role is not None
    if required_level == AuthLevel.ADMIN:
        return user_role == "admin"
    if required_level == AuthLevel.CLIENT:
        return user_role == "client"
    if required_level == AuthLevel.MINER:
        return user_role == "miner"
    if required_level == AuthLevel.ADMIN_OR_CLIENT:
        return user_role in ("admin", "client")
    if required_level == AuthLevel.DENY:
        return False
    return False  # type: ignore[unreachable]


__all__ = ["AuthLevel", "ROUTE_SECURITY_MATRIX", "check_role_match", "get_auth_level"]
