"""
Access Control Module for AITBC Services
Provides authentication, authorization, and access control mechanisms
"""

import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

try:
    import jwt

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

from .aitbc_logging import get_logger

logger = get_logger(__name__)


class AccessControlError(Exception):
    """Base exception for access control errors"""

    pass


class AuthenticationError(AccessControlError):
    """Authentication failed"""

    pass


class AuthorizationError(AccessControlError):
    """Authorization failed"""

    pass


class AccessController:
    """
    Centralized access control for AITBC services
    Handles authentication, authorization, and access control
    """

    def __init__(self, secret_key: str | None = None, algorithm: str = "HS256", token_expiry: int = 3600):
        """
        Initialize access controller

        Args:
            secret_key: JWT secret key (from env if not provided)
            algorithm: JWT algorithm
            token_expiry: Token expiry time in seconds
        """
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", "default-secret-key-change-in-production")
        self.algorithm = algorithm
        self.token_expiry = token_expiry
        self.jwt_available = JWT_AVAILABLE

        # Role-based access control
        self.role_permissions = {
            "admin": ["*"],  # Full access
            "operator": ["read", "write", "execute"],
            "user": ["read"],
            "service": ["read", "write"],
            "guest": ["read"],
        }

        logger.info("Access controller initialized (JWT available: %s)", self.jwt_available)

    def create_token(self, user_id: str, roles: list[str], additional_claims: dict[str, Any] | None = None) -> str:
        """
        Create JWT token for user

        Args:
            user_id: User identifier
            roles: List of user roles
            additional_claims: Additional claims to include in token

        Returns:
            JWT token string
        """
        if not self.jwt_available:
            raise AccessControlError("JWT not available")

        now = datetime.utcnow()
        expiry = now + timedelta(seconds=self.token_expiry)

        claims = {"sub": user_id, "roles": roles, "iat": now.timestamp(), "exp": expiry.timestamp(), "iss": "aitbc"}

        if additional_claims:
            claims.update(additional_claims)

        token = jwt.encode(claims, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> dict[str, Any]:
        """
        Verify and decode JWT token

        Args:
            token: JWT token string

        Returns:
            Decoded token claims

        Raises:
            AuthenticationError: If token is invalid
        """
        if not self.jwt_available:
            raise AccessControlError("JWT not available")

        try:
            claims = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
            return claims
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired") from None
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}") from e

    def check_permission(self, user_roles: list[str], required_permission: str) -> bool:
        """
        Check if user has required permission

        Args:
            user_roles: List of user roles
            required_permission: Required permission

        Returns:
            True if user has permission, False otherwise
        """
        for role in user_roles:
            if role in self.role_permissions:
                permissions = self.role_permissions[role]
                if "*" in permissions or required_permission in permissions:
                    return True

        return False

    def require_role(self, *required_roles: str):
        """
        Decorator to require specific roles

        Args:
            *required_roles: Required roles (any one is sufficient)

        Example:
            @require_role("admin", "operator")
            def admin_function():
                return "admin data"
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract token from kwargs or context
                token = kwargs.get("token") or kwargs.get("auth_token")

                if not token:
                    raise AuthorizationError("Authentication required")

                try:
                    claims = self.verify_token(token)
                    user_roles = claims.get("roles", [])

                    # Check if user has any of the required roles
                    if not any(role in user_roles for role in required_roles):
                        raise AuthorizationError(f"Insufficient permissions. Required: {required_roles}")

                    return func(*args, **kwargs)
                except AuthenticationError as e:
                    raise AuthorizationError(f"Authentication failed: {str(e)}") from e

            return wrapper

        return decorator

    def require_permission(self, *required_permissions: str):
        """
        Decorator to require specific permissions

        Args:
            *required_permissions: Required permissions (all must be present)

        Example:
            @require_permission("read", "write")
            def modify_data():
                return "modified data"
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract token from kwargs or context
                token = kwargs.get("token") or kwargs.get("auth_token")

                if not token:
                    raise AuthorizationError("Authentication required")

                try:
                    claims = self.verify_token(token)
                    user_roles = claims.get("roles", [])

                    # Check if user has all required permissions
                    for permission in required_permissions:
                        if not self.check_permission(user_roles, permission):
                            raise AuthorizationError(f"Insufficient permissions. Required: {required_permissions}")

                    return func(*args, **kwargs)
                except AuthenticationError as e:
                    raise AuthorizationError(f"Authentication failed: {str(e)}") from e

            return wrapper

        return decorator


class APIKeyAuth:
    """
    API Key authentication for service-to-service communication
    """

    def __init__(self, valid_keys: list[str] | None = None):
        """
        Initialize API key authenticator

        Args:
            valid_keys: List of valid API keys (from env if not provided)
        """
        if valid_keys is None:
            # Load from environment
            keys_str = os.getenv("VALID_API_KEYS", "")
            self.valid_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            self.valid_keys = valid_keys

        logger.info("API Key auth initialized with %d valid keys", len(self.valid_keys))

    def verify_key(self, api_key: str) -> bool:
        """
        Verify API key

        Args:
            api_key: API key to verify

        Returns:
            True if key is valid, False otherwise
        """
        return api_key in self.valid_keys

    def require_api_key(self):
        """
        Decorator to require valid API key

        Example:
            @require_api_key()
            def protected_function():
                return "protected data"
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract API key from kwargs or headers
                api_key = kwargs.get("api_key") or kwargs.get("x_api_key")

                if not api_key:
                    raise AuthorizationError("API key required")

                if not self.verify_key(api_key):
                    raise AuthorizationError("Invalid API key")

                return func(*args, **kwargs)

            return wrapper

        return decorator


class SecureHeaders:
    """
    Security headers for HTTP responses
    """

    @staticmethod
    def get_security_headers() -> dict[str, str]:
        """
        Get standard security headers

        Returns:
            Dictionary of security headers
        """
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }


# Global access controller instance
_access_controller: AccessController | None = None


def get_access_controller() -> AccessController:
    """
    Get global access controller instance

    Returns:
        AccessController instance
    """
    global _access_controller
    if _access_controller is None:
        _access_controller = AccessController()
    return _access_controller


def get_api_key_auth() -> APIKeyAuth:
    """
    Get global API key authenticator instance

    Returns:
        APIKeyAuth instance
    """
    return APIKeyAuth()
