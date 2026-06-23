"""
Route security matrix - defines auth requirements for all routes
"""

from enum import Enum


class AuthLevel(Enum):
    """Authentication levels"""

    NONE = "none"  # No authentication required
    ANY = "any"  # Any valid JWT token
    ADMIN = "admin"  # Admin role required
    CLIENT = "client"  # Client role required
    MINER = "miner"  # Miner role required
    ADMIN_OR_CLIENT = "admin_or_client"  # Admin or client role


# Route security matrix
# Format: {"router:path": AuthLevel}
ROUTE_SECURITY_MATRIX = {
    # Public routes
    "/health": AuthLevel.NONE,
    "/docs": AuthLevel.NONE,
    "/openapi.json": AuthLevel.NONE,
    "/redoc": AuthLevel.NONE,
    # Admin routes
    "/admin": AuthLevel.ADMIN,
    "/routers/admin": AuthLevel.ADMIN,
    "/contexts/admin/*": AuthLevel.ADMIN,
    # Client routes
    "/routers/client": AuthLevel.CLIENT,
    "/contexts/certification/*": AuthLevel.CLIENT,
    "/contexts/trading/*": AuthLevel.CLIENT,
    "/contexts/payments/*": AuthLevel.CLIENT,
    # Miner routes
    "/routers/miner": AuthLevel.MINER,
    "/contexts/marketplace/*": AuthLevel.MINER,
    "/contexts/settlement/*": AuthLevel.MINER,
    # Mixed auth routes (any valid token)
    "/contexts/agent_coordination/*": AuthLevel.ANY,
    "/contexts/agent_identity/*": AuthLevel.ANY,
    "/contexts/infrastructure/*": AuthLevel.ANY,
    "/contexts/monitoring/*": AuthLevel.ANY,
    # Analytics (admin or client)
    "/contexts/analytics/*": AuthLevel.ADMIN_OR_CLIENT,
    "/contexts/ai_analytics/*": AuthLevel.ADMIN_OR_CLIENT,
    # Security (admin only)
    "/contexts/security/*": AuthLevel.ADMIN,
    # Governance (admin or client)
    "/contexts/governance/*": AuthLevel.ADMIN_OR_CLIENT,
    # Staking (admin or client)
    "/contexts/staking/*": AuthLevel.ADMIN_OR_CLIENT,
    # Rewards (admin or client)
    "/contexts/rewards/*": AuthLevel.ADMIN_OR_CLIENT,
    # Reputation (any)
    "/contexts/reputation/*": AuthLevel.ANY,
    # Bounty (any)
    "/contexts/bounty/*": AuthLevel.ANY,
    # Knowledge (any)
    "/contexts/knowledge/*": AuthLevel.ANY,
    # Developer platform (admin or client)
    "/contexts/developer_platform/*": AuthLevel.ADMIN_OR_CLIENT,
    # Ecosystem (any)
    "/contexts/ecosystem/*": AuthLevel.ANY,
    # Community (any)
    "/contexts/community/*": AuthLevel.ANY,
    # Confidential (admin only)
    "/contexts/confidential/*": AuthLevel.ADMIN,
    # Advanced RL (any)
    "/contexts/advanced_rl/*": AuthLevel.ANY,
    # Multimodal (any)
    "/contexts/multimodal/*": AuthLevel.ANY,
    # Cross-chain (any)
    "/contexts/cross_chain/*": AuthLevel.ANY,
    # Blockchain (any)
    "/contexts/blockchain/*": AuthLevel.ANY,
    # IPFS (any)
    "/contexts/ipfs/*": AuthLevel.ANY,
    # Portfolio (admin or client)
    "/contexts/portfolio/*": AuthLevel.ADMIN_OR_CLIENT,
    # Exchange (any)
    "/contexts/exchange/*": AuthLevel.ANY,
    # Explorer (any)
    "/contexts/explorer/*": AuthLevel.ANY,
    # Services (admin only)
    "/routers/services": AuthLevel.ADMIN,
    # Cache management (admin only)
    "/routers/cache_management": AuthLevel.ADMIN,
    # Dynamic pricing (admin or client)
    "/routers/dynamic_pricing": AuthLevel.ADMIN_OR_CLIENT,
    # Marketplace enhanced (any)
    "/routers/marketplace_enhanced": AuthLevel.ANY,
    "/routers/marketplace_enhanced_simple": AuthLevel.ANY,
    "/routers/marketplace_enhanced_health": AuthLevel.NONE,
    # Agent management (admin only)
    "/routers/agent-management": AuthLevel.ADMIN,
}


def get_auth_level(path: str) -> AuthLevel:
    """
    Get required auth level for a given path

    Args:
        path: Request path

    Returns:
        Required auth level
    """
    # Check exact match first
    if path in ROUTE_SECURITY_MATRIX:
        return ROUTE_SECURITY_MATRIX[path]

    # Check prefix matches
    for pattern, level in ROUTE_SECURITY_MATRIX.items():
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return level

    # Default to requiring auth
    return AuthLevel.ANY


def check_role_match(required_level: AuthLevel, user_role: str | None) -> bool:
    """
    Check if user role matches required auth level

    Args:
        required_level: Required auth level
        user_role: User's role from token

    Returns:
        True if role matches, False otherwise
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
    return False
