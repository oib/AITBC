"""
Authentication module for Coordinator API
"""

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
from .security_matrix import AuthLevel, check_role_match, get_auth_level, ROUTE_SECURITY_MATRIX

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
