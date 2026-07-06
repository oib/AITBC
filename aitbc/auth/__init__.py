"""
AITBC Authentication & Authorization Module

Consolidates JWT, password hashing, API keys, RBAC, FastAPI dependencies,
middleware, and route security matrix into a single shared package.

Usage examples::

    # Exception-style JWT (coordinator-api compatible)
    from aitbc.auth import create_access_token, verify_access_token

    # Dict-style JWT (agent-coordinator compatible)
    from aitbc.auth import JWTHandler, get_jwt_handler

    # FastAPI dependencies
    from aitbc.auth import AuthDep, AdminDep, ClientDep, MinerDep

    # RBAC
    from aitbc.auth import Permission, Role, permission_manager

    # Password hashing
    from aitbc.auth import PasswordManager, password_manager
"""

from .api_key import APIKeyManager, api_key_manager
from .dependencies import (
    AdminDep,
    AuthDep,
    ClientDep,
    MinerDep,
    get_token,
    require_admin,
    require_auth,
    require_client,
    require_miner,
    require_miner_api_key,
    require_miner_jwt,
)
from .jwt import (
    JWTAuth,
    JWTHandler,
    create_access_token,
    get_jwt_auth,
    get_jwt_handler,
    verify_access_token,
)
from .middleware import (
    AuthMiddleware,
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
from .password import (
    PasswordManager,
    hash_password_pbkdf2,
    password_manager,
    verify_password_pbkdf2,
)
from .permissions import (
    Permission,
    PermissionManager,
    Role,
    RolePermission,
    permission_manager,
)
from .security_matrix import (
    AuthLevel,
    ROUTE_SECURITY_MATRIX,
    check_role_match,
    get_auth_level,
)

__all__ = [
    # JWT
    "JWTAuth",
    "JWTHandler",
    "create_access_token",
    "get_jwt_auth",
    "get_jwt_handler",
    "verify_access_token",
    # Password
    "PasswordManager",
    "hash_password_pbkdf2",
    "password_manager",
    "verify_password_pbkdf2",
    # API Keys
    "APIKeyManager",
    "api_key_manager",
    # RBAC
    "Permission",
    "PermissionManager",
    "Role",
    "RolePermission",
    "permission_manager",
    # FastAPI Dependencies
    "AdminDep",
    "AuthDep",
    "ClientDep",
    "MinerDep",
    "get_token",
    "require_admin",
    "require_auth",
    "require_client",
    "require_miner",
    "require_miner_api_key",
    "require_miner_jwt",
    # Middleware
    "AuthMiddleware",
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
    # Security Matrix
    "AuthLevel",
    "ROUTE_SECURITY_MATRIX",
    "check_role_match",
    "get_auth_level",
]
