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

Both styles share the same underlying token encoding/decoding logic and a single
set of identity claims: ``sub`` (subject), ``role``, ``type`` (access/refresh),
``iat``, and ``exp``.  The legacy ``user_id`` claim is preserved as an alias for
backward compatibility.
"""

from __future__ import annotations

import os
import secrets as _secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import ConfigurationError
from aitbc.utils.env import is_production

logger = get_logger(__name__)


_KNOWN_JWT_DEFAULTS = frozenset(
    {
        "change-me-in-production",
        "change-this-secret-key-in-production",
        "your_secret_here",
        "your-secret-key-change-in-production",
    }
)


class AuthenticationError(Exception):
    """Generic authentication failure."""

    pass


def _resolve_secret() -> str:
    """Resolve JWT secret from environment.

    Production services must supply ``JWT_SECRET`` or ``JWT_SECRET_KEY``.
    Non-production/test environments may fall back to an ephemeral secret, but a
    warning is logged because tokens produced with it are not stable across
    restarts.
    """
    value = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or ""
    value = value.strip()

    if not value:
        if is_production():
            raise ConfigurationError("JWT_SECRET environment variable is required in production")
        value = _secrets.token_urlsafe(32)
        logger.warning(
            "JWT_SECRET not configured; using an ephemeral test secret. "
            "Set JWT_SECRET to a value with at least 32 characters for stable tokens."
        )
        return value

    _validate_secret(value)
    return value


def _validate_secret(value: str) -> None:
    """Validate a supplied JWT secret meets minimum strength requirements."""
    if value.lower() in _KNOWN_JWT_DEFAULTS:
        raise ValueError("JWT secret must be changed from the default value")
    if len(value) < 32:
        raise ValueError("JWT secret must be at least 32 characters long")


def _get_algorithm() -> str:
    """Get JWT algorithm from env or default."""
    return os.getenv("JWT_ALGORITHM", "HS256")


def _get_expiry_hours() -> int:
    """Get token expiry hours from env or default."""
    return int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


def _identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize identity claims and add token metadata.

    Ensures the canonical ``sub`` claim is present and mirrors it as ``user_id``
    for consumers that expect the legacy claim name. Adds ``iat`` and ``type``
    unless the caller already supplied them.
    """
    normalized = payload.copy()
    sub = normalized.get("sub") or normalized.get("user_id")
    if sub is not None:
        normalized.setdefault("sub", sub)
        normalized.setdefault("user_id", sub)
    normalized.setdefault("iat", datetime.now(UTC))
    return normalized


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
        self.secret = secret or _resolve_secret()
        if secret:
            _validate_secret(self.secret)
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
        to_encode = _identity_payload(payload)
        to_encode.setdefault("exp", expire)
        to_encode.setdefault("type", "access")
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
                detail="Role required",
                headers={"WWW-Authenticate": "Bearer"},
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
    payload: dict[str, Any] = {"sub": user_id, "role": role, "type": "access"}
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
        self.secret_key = secret_key or _resolve_secret()
        if secret_key:
            _validate_secret(self.secret_key)
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
            token_payload = _identity_payload(payload)
            token_payload.setdefault("exp", expire)
            token_payload.setdefault("type", "access")
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "token": token, "expires_at": expire.isoformat(), "token_type": "Bearer"}
        except Exception as e:
            logger.error("Error generating JWT token: %s", e)
            return {"status": "error", "message": "Token generation failed"}

    def generate_refresh_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate refresh token for token renewal."""
        try:
            expire = datetime.now(UTC) + self.refresh_expiry
            token_payload = _identity_payload(payload)
            token_payload.setdefault("exp", expire)
            token_payload.setdefault("type", "refresh")
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "refresh_token": token, "expires_at": expire.isoformat()}
        except Exception as e:
            logger.error("Error generating refresh token: %s", e)
            return {"status": "error", "message": "Token generation failed"}

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return payload."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
            return {"status": "success", "valid": True, "payload": payload}
        except jwt.ExpiredSignatureError:
            return {"status": "error", "valid": False, "message": "Token has expired"}
        except jwt.InvalidTokenError:
            return {"status": "error", "valid": False, "message": "Invalid token"}
        except Exception as e:
            logger.error("Error validating token: %s", e)
            return {"status": "error", "valid": False, "message": "Token validation failed"}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Generate new access token from refresh token."""
        try:
            validation = self.validate_token(refresh_token)
            if not validation["valid"] or validation["payload"].get("type") != "refresh":
                return {"status": "error", "message": "Invalid or expired refresh token"}
            payload = validation["payload"]
            user_payload = {
                "sub": payload.get("sub") or payload.get("user_id"),
                "user_id": payload.get("user_id") or payload.get("sub"),
                "username": payload.get("username"),
                "role": payload.get("role"),
                "permissions": payload.get("permissions", []),
            }
            return self.generate_token(user_payload)
        except Exception as e:
            logger.error("Error refreshing token: %s", e)
            return {"status": "error", "message": "Token refresh failed"}

    def decode_token_without_validation(self, token: str) -> dict[str, Any]:
        """Decode token without expiration validation (for debugging)."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": False})
            return {"status": "success", "payload": payload}
        except Exception:
            return {"status": "error", "message": "Error decoding token"}


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
    "AuthenticationError",
    "JWTAuth",
    "JWTHandler",
    "create_access_token",
    "get_jwt_auth",
    "get_jwt_handler",
    "verify_access_token",
]
