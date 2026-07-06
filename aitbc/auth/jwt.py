"""
Unified JWT handler for AITBC services.

Consolidates the two previous implementations:
- ``apps/coordinator-api/src/app/auth/jwt_auth.py`` (HTTPException-raising, access-only)
- ``apps/agent-coordinator/src/app/auth/jwt_handler.py`` (dict-returning, access+refresh)

This module provides two usage styles:

1. **Exception style** (coordinator-api compatible):
   Raises ``HTTPException`` on invalid tokens. Use ``JWTAuth`` class or
   ``create_access_token`` / ``verify_access_token`` functions.

2. **Dict style** (agent-coordinator compatible):
   Returns ``{"status": "success"|"error", ...}`` dicts. Use ``JWTHandler`` class.

Both styles share the same underlying token encoding/decoding logic.
"""

from __future__ import annotations

import os
import secrets as _secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def _get_secret(default: str | None = None) -> str:
    """Get JWT secret from env or return default."""
    return os.getenv("JWT_SECRET", os.getenv("JWT_SECRET_KEY", default or _secrets.token_urlsafe(32)))


def _get_algorithm() -> str:
    """Get JWT algorithm from env or default."""
    return os.getenv("JWT_ALGORITHM", "HS256")


def _get_expiry_hours() -> int:
    """Get token expiry hours from env or default."""
    return int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


# ---------------------------------------------------------------------------
# Exception-style API (coordinator-api compatible)
# ---------------------------------------------------------------------------


class JWTAuth:
    """JWT authentication handler — exception style.

    Raises ``HTTPException`` on invalid tokens. Compatible with the
    coordinator-api's original ``JWTAuth`` class.
    """

    def __init__(
        self,
        secret: str | None = None,
        algorithm: str | None = None,
        expiration_hours: int | None = None,
    ) -> None:
        self.secret = secret or _get_secret()
        self.algorithm = algorithm or _get_algorithm()
        self.expiration_hours = expiration_hours or _get_expiry_hours()

    def create_token(self, payload: dict[str, Any]) -> str:
        """Create JWT token with expiration.

        Args:
            payload: Claims to include in token.

        Returns:
            Encoded JWT token string.
        """
        expire = datetime.now(UTC) + timedelta(hours=self.expiration_hours)
        to_encode = payload.copy()
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate JWT token.

        Args:
            token: JWT token string.

        Returns:
            Decoded token payload.

        Raises:
            HTTPException: If token is invalid.
        """
        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    def verify_token(self, token: str, required_role: str | None = None) -> dict[str, Any]:
        """Verify token and optionally check role.

        Args:
            token: JWT token string.
            required_role: Required role (optional).

        Returns:
            Decoded token payload.

        Raises:
            HTTPException: If token is invalid or role doesn't match.
        """
        payload = self.decode_token(token)
        if required_role and payload.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return payload


# Global instance (lazy-initialized for coordinator-api compatibility)
_jwt_auth: JWTAuth | None = None


def get_jwt_auth() -> JWTAuth:
    """Get or create the global JWTAuth instance."""
    global _jwt_auth
    if _jwt_auth is None:
        _jwt_auth = JWTAuth()
    return _jwt_auth


def create_access_token(user_id: str, role: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create access token for user (exception style).

    Args:
        user_id: User identifier.
        role: User role (admin, client, miner).
        extra_claims: Additional claims to include.

    Returns:
        Encoded JWT token string.
    """
    payload: dict[str, Any] = {"sub": user_id, "role": role}
    if extra_claims:
        payload.update(extra_claims)
    return get_jwt_auth().create_token(payload)


def verify_access_token(token: str, required_role: str | None = None) -> dict[str, Any]:
    """Verify access token and return payload (exception style).

    Args:
        token: JWT token string.
        required_role: Required role (optional).

    Returns:
        Decoded token payload.

    Raises:
        HTTPException: If token is invalid or role doesn't match.
    """
    return get_jwt_auth().verify_token(token, required_role)


# ---------------------------------------------------------------------------
# Dict-style API (agent-coordinator compatible)
# ---------------------------------------------------------------------------


class JWTHandler:
    """JWT token management — dict style.

    Returns ``{"status": "success"|"error", ...}`` dicts instead of raising
    exceptions. Compatible with the agent-coordinator's original ``JWTHandler``
    class. Supports access tokens, refresh tokens, and token refresh.
    """

    def __init__(self, secret_key: str | None = None) -> None:
        self.secret_key = secret_key or _get_secret()
        self.algorithm = _get_algorithm()
        self.token_expiry = timedelta(hours=_get_expiry_hours())
        self.refresh_expiry = timedelta(days=7)

    def generate_token(self, payload: dict[str, Any], expires_delta: timedelta | None = None) -> dict[str, Any]:
        """Generate JWT token with specified payload."""
        try:
            if expires_delta:
                expire = datetime.now(UTC) + expires_delta
            else:
                expire = datetime.now(UTC) + self.token_expiry
            token_payload = {**payload, "exp": expire, "iat": datetime.now(UTC), "type": "access"}
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "token": token, "expires_at": expire.isoformat(), "token_type": "Bearer"}
        except Exception as e:
            logger.error("Error generating JWT token: %s", e)
            return {"status": "error", "message": str(e)}

    def generate_refresh_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate refresh token for token renewal."""
        try:
            expire = datetime.now(UTC) + self.refresh_expiry
            token_payload = {**payload, "exp": expire, "iat": datetime.now(UTC), "type": "refresh"}
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "refresh_token": token, "expires_at": expire.isoformat()}
        except Exception as e:
            logger.error("Error generating refresh token: %s", e)
            return {"status": "error", "message": str(e)}

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return payload."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
            return {"status": "success", "valid": True, "payload": payload}
        except jwt.ExpiredSignatureError:
            return {"status": "error", "valid": False, "message": "Token has expired"}
        except jwt.InvalidTokenError as e:
            return {"status": "error", "valid": False, "message": f"Invalid token: {e!s}"}
        except Exception as e:
            logger.error("Error validating token: %s", e)
            return {"status": "error", "valid": False, "message": f"Token validation error: {e!s}"}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Generate new access token from refresh token."""
        try:
            validation = self.validate_token(refresh_token)
            if not validation["valid"] or validation["payload"].get("type") != "refresh":
                return {"status": "error", "message": "Invalid or expired refresh token"}
            payload = validation["payload"]
            user_payload = {
                "user_id": payload.get("user_id"),
                "username": payload.get("username"),
                "role": payload.get("role"),
                "permissions": payload.get("permissions", []),
            }
            return self.generate_token(user_payload)
        except Exception as e:
            logger.error("Error refreshing token: %s", e)
            return {"status": "error", "message": str(e)}

    def decode_token_without_validation(self, token: str) -> dict[str, Any]:
        """Decode token without expiration validation (for debugging)."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": False})
            return {"status": "success", "payload": payload}
        except Exception as e:
            return {"status": "error", "message": f"Error decoding token: {e!s}"}


# ---------------------------------------------------------------------------
# Global instances (agent-coordinator compatibility)
# ---------------------------------------------------------------------------

_jwt_handler: JWTHandler | None = None


def get_jwt_handler() -> JWTHandler:
    """Get or create the global JWTHandler instance."""
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler()
    return _jwt_handler


__all__ = [
    "JWTAuth",
    "JWTHandler",
    "create_access_token",
    "get_jwt_auth",
    "get_jwt_handler",
    "verify_access_token",
]
