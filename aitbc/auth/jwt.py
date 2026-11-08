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


def _extra_verify_secrets() -> list[str]:
    """Additional secrets accepted for verification only, never for signing.

    ``rotate_jwt_secret.sh`` performs a dual-secret overlap rotation:

    * ``JWT_SECRET_NEW`` — set alongside the still-active ``JWT_SECRET`` while a
      rotation is in flight (before the primary is flipped);
    * ``JWT_SECRET_PREVIOUS`` — comma-separated retired secrets kept so tokens
      minted under an older secret stay valid until they expire.

    Signing always uses the primary ``JWT_SECRET``; these extras only widen the
    verification set.
    """
    extras: list[str] = []
    new = (os.getenv("JWT_SECRET_NEW") or "").strip()
    if new:
        extras.append(new)
    previous = os.getenv("JWT_SECRET_PREVIOUS") or ""
    extras.extend(part.strip() for part in previous.split(",") if part.strip())
    return extras


def _validate_secret(value: str) -> None:
    """Validate a supplied JWT secret meets minimum strength requirements."""
    if value.lower() in _KNOWN_JWT_DEFAULTS:
        raise ValueError("JWT secret must be changed from the default value")
    if len(value) < 32:
        raise ValueError("JWT secret must be at least 32 characters long")


def _get_algorithm() -> str:
    """Get JWT algorithm from env or default."""
    return os.getenv("JWT_ALGORITHM", "HS256")


def _is_no_expiration() -> bool:
    """Return whether non-expiring tokens are explicitly requested."""
    return os.getenv("JWT_NO_EXPIRATION", "").lower() in ("1", "true", "yes")


def _require_exp() -> bool:
    """Whether exp-less tokens are rejected at verify time (#1185).

    ``jwt.decode`` only validates ``exp`` when the claim is present, so
    tokens minted under ``JWT_NO_EXPIRATION=1`` stay valid forever after
    the mint-side flag flips. This verify-side gate is what actually gives
    legacy tokens a death date. Arm it only together with expiry-enabled
    minting — armed while ``JWT_NO_EXPIRATION`` is still set, every new
    token lacks ``exp`` and is refused.
    """
    return os.getenv("JWT_REQUIRE_EXP", "").lower() in ("1", "true", "yes")


def _get_expiry_hours() -> int:
    """Get token expiry hours from env or default (0 means no expiry)."""
    if _is_no_expiration():
        logger.warning("JWT_NO_EXPIRATION is set; access tokens will not expire")
        return 0
    raw = os.getenv("JWT_EXPIRATION_HOURS", "24")
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid JWT_EXPIRATION_HOURS %r; using default 24", raw)
        return 24
    if value < 0:
        logger.warning("JWT_EXPIRATION_HOURS %r is negative; using default 24", raw)
        return 24
    if value == 0:
        logger.warning("JWT_EXPIRATION_HOURS is 0; access tokens will not expire")
    return value


def _get_refresh_expiry_days() -> int:
    """Get refresh-token expiry days from env or default (0 means no expiry)."""
    if _is_no_expiration():
        logger.warning("JWT_NO_EXPIRATION is set; refresh tokens will not expire")
        return 0
    raw = os.getenv("JWT_REFRESH_EXPIRY_DAYS", "7")
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid JWT_REFRESH_EXPIRY_DAYS %r; using default 7", raw)
        return 7
    if value < 0:
        logger.warning("JWT_REFRESH_EXPIRY_DAYS %r is negative; using default 7", raw)
        return 7
    if value == 0:
        logger.warning("JWT_REFRESH_EXPIRY_DAYS is 0; refresh tokens will not expire")
    return value


def _jwt_issuer() -> str:
    """Issuer claim written at mint time (R12-HARDEN-1/#1233).

    ``JWT_ISSUER`` wins; otherwise the service's own name
    (``SERVICE_NAME``/``APP_NAME``); ``"aitbc"`` is the shared fallback so
    deployments that do not set per-service names keep a stable value.
    """
    return os.getenv("JWT_ISSUER") or os.getenv("SERVICE_NAME") or os.getenv("APP_NAME") or "aitbc"


def _jwt_audience() -> str:
    """Audience claim written at mint time; ``JWT_AUDIENCE`` or ``"aitbc"``."""
    return os.getenv("JWT_AUDIENCE") or "aitbc"


def _jwt_expected_issuer() -> str:
    """Issuer value enforcement requires; defaults to the local issuer."""
    return os.getenv("JWT_EXPECTED_ISSUER") or _jwt_issuer()


def _jwt_enforce_iss_aud() -> bool:
    """Whether iss/aud binding is enforced at verify time (default OFF).

    Ships dormant: enforcement flips only after #1185 gives exp-less
    tokens a death date and a re-auth path exists for live sessions.
    """
    return os.getenv("JWT_ENFORCE_ISS_AUD", "").lower() in ("1", "true", "yes")


def _apply_iss_aud(claims: dict[str, Any]) -> None:
    """Add iss/aud claims at mint time without overriding explicit values."""
    claims.setdefault("iss", _jwt_issuer())
    claims.setdefault("aud", _jwt_audience())


def _iss_aud_rejection(payload: dict[str, Any]) -> str | None:
    """Return a rejection reason when iss/aud binding fails, else None.

    Only consulted when ``JWT_ENFORCE_ISS_AUD`` is set; callers decide
    how to surface the failure (HTTPException vs error dict).
    """
    if not _jwt_enforce_iss_aud():
        return None
    if payload.get("iss") != _jwt_expected_issuer():
        return "issuer mismatch"
    aud = payload.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if _jwt_audience() not in audiences:
        return "audience mismatch"
    return None


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
        self.extra_secrets = _extra_verify_secrets()
        self.algorithm = algorithm or _get_algorithm()
        self.expiration_hours = max(0, _get_expiry_hours() if expiration_hours is None else expiration_hours)

    def create_token(self, payload: dict[str, Any]) -> str:
        """Create JWT token with optional expiration.

        Args:
            payload: Claims to include in token.

        Returns:
            Encoded JWT token string.
        """
        to_encode = _identity_payload(payload)
        to_encode.setdefault("type", "access")
        _apply_iss_aud(to_encode)
        if self.expiration_hours > 0:
            to_encode.setdefault("exp", datetime.now(UTC) + timedelta(hours=self.expiration_hours))
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
        payload: dict[str, Any] | None = None
        last_error: jwt.PyJWTError | None = None
        for candidate in [self.secret, *self.extra_secrets]:
            try:
                payload = jwt.decode(
                    token,
                    candidate,
                    algorithms=[self.algorithm],
                    options={"verify_aud": False},
                )
                break
            except jwt.PyJWTError as e:
                last_error = e
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from last_error
        # Fail closed on the `type` claim: this class only issues access
        # tokens, and a 7-day refresh token must not authenticate where an
        # access token is required (AUTH-JWT-TYPE-CONFUSION-1). A token with
        # no type claim is refused — JWTAuth/JWTHandler have always written
        # one, so its absence means a foreign/forged token.
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if _iss_aud_rejection(payload) is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if _require_exp() and "exp" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

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
        self.extra_secrets = _extra_verify_secrets()
        self.algorithm = _get_algorithm()
        self.token_expiry = timedelta(hours=_get_expiry_hours())
        self.refresh_expiry = timedelta(days=_get_refresh_expiry_days())

    def generate_token(self, payload: dict[str, Any], expires_delta: timedelta | None = None) -> dict[str, Any]:
        """Generate JWT token with specified payload."""
        try:
            effective_expiry = expires_delta if expires_delta is not None else self.token_expiry
            token_payload = _identity_payload(payload)
            token_payload.setdefault("type", "access")
            _apply_iss_aud(token_payload)
            expire: datetime | None = None
            if effective_expiry.total_seconds() != 0:
                expire = datetime.now(UTC) + effective_expiry
                token_payload.setdefault("exp", expire)
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {
                "status": "success",
                "token": token,
                "expires_at": expire.isoformat() if expire else None,
                "token_type": "Bearer",  # nosec
            }
        except Exception as e:
            logger.error("Error generating JWT token: %s", e)
            return {"status": "error", "message": "Token generation failed"}

    def generate_refresh_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate refresh token for token renewal."""
        try:
            token_payload = _identity_payload(payload)
            token_payload.setdefault("type", "refresh")
            _apply_iss_aud(token_payload)
            expire: datetime | None = None
            if self.refresh_expiry.total_seconds() > 0:
                expire = datetime.now(UTC) + self.refresh_expiry
                token_payload.setdefault("exp", expire)
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            return {"status": "success", "refresh_token": token, "expires_at": expire.isoformat() if expire else None}
        except Exception as e:
            logger.error("Error generating refresh token: %s", e)
            return {"status": "error", "message": "Token generation failed"}

    def validate_token(self, token: str, expected_type: str | None = "access") -> dict[str, Any]:
        """Validate JWT token and return payload.

        Fail closed on the ``type`` claim: every caller except the refresh
        path wants an access token, so the default is ``"access"`` and a
        token with no type claim is refused (JWTAuth/JWTHandler have always
        written one — its absence means a foreign or forged token).
        ``refresh_access_token`` passes ``expected_type="refresh"``;
        ``None`` disables the check for a caller that genuinely wants any
        type.
        """
        payload: dict[str, Any] | None = None
        expired = False
        try:
            for candidate in [self.secret_key, *self.extra_secrets]:
                try:
                    payload = jwt.decode(
                        token,
                        candidate,
                        algorithms=[self.algorithm],
                        options={"verify_exp": True, "verify_aud": False},
                    )
                    break
                except jwt.ExpiredSignatureError:
                    # The signature was valid under this secret; the token is
                    # genuinely expired regardless of which secret signed it.
                    expired = True
                except jwt.InvalidTokenError:
                    continue
        except Exception as e:
            logger.error("Error validating token: %s", e)
            return {"status": "error", "valid": False, "message": "Token validation failed"}
        if payload is None:
            if expired:
                return {"status": "error", "valid": False, "message": "Token has expired"}
            return {"status": "error", "valid": False, "message": "Invalid token"}
        if expected_type is not None and payload.get("type") != expected_type:
            return {"status": "error", "valid": False, "message": "Invalid token type"}
        if _iss_aud_rejection(payload) is not None:
            return {"status": "error", "valid": False, "message": "Invalid token issuer or audience"}
        if _require_exp() and "exp" not in payload:
            return {"status": "error", "valid": False, "message": "Invalid token"}
        return {"status": "success", "valid": True, "payload": payload}

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Generate new access token from refresh token."""
        try:
            validation = self.validate_token(refresh_token, expected_type="refresh")
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
        for candidate in [self.secret_key, *self.extra_secrets]:
            try:
                payload = jwt.decode(
                    token,
                    candidate,
                    algorithms=[self.algorithm],
                    options={"verify_exp": False, "verify_aud": False},
                )
                return {"status": "success", "payload": payload}
            except Exception:
                continue
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
