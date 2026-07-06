"""
Access Control Module for AITBC Services.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth``. Import from ``aitbc.auth`` directly in new code.

This shim preserves the original API surface (AccessController, APIKeyAuth,
SecureHeaders, etc.) for backward compatibility with existing tests and code.
"""

import warnings

from aitbc.auth.middleware import SecurityHeaders as _SecurityHeaders

# Re-export SecureHeaders under the old name
SecureHeaders = _SecurityHeaders

warnings.warn(
    "aitbc.access_control is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)


class AccessControlError(Exception):
    """Base exception for access control errors."""

    pass


class AuthenticationError(AccessControlError):
    """Authentication failed."""

    pass


class AuthorizationError(AccessControlError):
    """Authorization failed."""

    pass


class AccessController:
    """
    Centralized access control for AITBC services.

    .. deprecated::
        Use ``aitbc.auth.JWTAuth`` for JWT operations and
        ``aitbc.auth.PermissionManager`` for RBAC instead.
    """

    def __init__(self, secret_key: str | None = None, algorithm: str = "HS256", token_expiry: int = 3600):
        import os

        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", "default-secret-key-change-in-production")
        self.algorithm = algorithm
        self.token_expiry = token_expiry
        self.jwt_available = True

        # Role-based access control (simple string-based for backward compat)
        self.role_permissions: dict[str, list[str]] = {
            "admin": ["*"],
            "operator": ["read", "write", "execute"],
            "user": ["read"],
            "service": ["read", "write"],
            "guest": ["read"],
        }

    def create_token(self, user_id: str, roles: list[str], additional_claims: dict | None = None) -> str:
        """Create JWT token for user."""
        from datetime import UTC, datetime, timedelta

        import jwt

        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=self.token_expiry)
        claims = {"sub": user_id, "roles": roles, "iat": now.timestamp(), "exp": expiry.timestamp(), "iss": "aitbc"}
        if additional_claims:
            claims.update(additional_claims)
        return jwt.encode(claims, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> dict:
        """Verify and decode JWT token."""
        import jwt

        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired") from None
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e!s}") from e

    def check_permission(self, user_roles: list[str], required_permission: str) -> bool:
        """Check if user has required permission."""
        for role in user_roles:
            if role in self.role_permissions:
                permissions = self.role_permissions[role]
                if "*" in permissions or required_permission in permissions:
                    return True
        return False

    def require_role(self, *required_roles: str):
        """Decorator to require specific roles."""
        from functools import wraps

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                token = kwargs.get("token") or kwargs.get("auth_token")
                if not token:
                    raise AuthorizationError("Authentication required")
                try:
                    claims = self.verify_token(token)
                    user_roles = claims.get("roles", [])
                    if not any(role in user_roles for role in required_roles):
                        raise AuthorizationError(f"Insufficient permissions. Required: {required_roles}")
                    return func(*args, **kwargs)
                except AuthenticationError as e:
                    raise AuthorizationError(f"Authentication failed: {e!s}") from e

            return wrapper

        return decorator

    def require_permission(self, *required_permissions: str):
        """Decorator to require specific permissions."""
        from functools import wraps

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                token = kwargs.get("token") or kwargs.get("auth_token")
                if not token:
                    raise AuthorizationError("Authentication required")
                try:
                    claims = self.verify_token(token)
                    user_roles = claims.get("roles", [])
                    for permission in required_permissions:
                        if not self.check_permission(user_roles, permission):
                            raise AuthorizationError(f"Insufficient permissions. Required: {required_permissions}")
                    return func(*args, **kwargs)
                except AuthenticationError as e:
                    raise AuthorizationError(f"Authentication failed: {e!s}") from e

            return wrapper

        return decorator


class APIKeyAuth:
    """API Key authentication for service-to-service communication."""

    def __init__(self, valid_keys: list[str] | None = None):
        import os

        if valid_keys is None:
            keys_str = os.getenv("VALID_API_KEYS", "")
            self.valid_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            self.valid_keys = valid_keys

    def verify_key(self, api_key: str) -> bool:
        """Verify API key."""
        return api_key in self.valid_keys

    def require_api_key(self):
        """Decorator to require valid API key."""
        from functools import wraps

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                api_key = kwargs.get("api_key")
                if not api_key or not self.verify_key(api_key):
                    raise AuthenticationError("Invalid or missing API key")
                return func(*args, **kwargs)

            return wrapper

        return decorator


def get_access_controller() -> AccessController:
    """Get global access controller instance."""
    global _access_controller
    if _access_controller is None:
        _access_controller = AccessController()
    return _access_controller


def get_api_key_auth() -> APIKeyAuth:
    """Get global API key auth instance."""
    global _api_key_auth
    if _api_key_auth is None:
        _api_key_auth = APIKeyAuth()
    return _api_key_auth


_access_controller: AccessController | None = None
_api_key_auth: APIKeyAuth | None = None


__all__ = [
    "APIKeyAuth",
    "AccessControlError",
    "AccessController",
    "AuthenticationError",
    "AuthorizationError",
    "SecureHeaders",
    "get_access_controller",
    "get_api_key_auth",
]
