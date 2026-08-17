"""
FastAPI authentication dependencies for AITBC services.

Extracted from ``apps/coordinator-api/src/app/auth/dependencies.py``.
Provides Bearer token extraction and role-based dependency injection.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Emit the miner-api-key fallback warning once per process. With `miner_api_keys` unset,
# the default uses COORDINATOR_API_KEY as a miner credential; the warning used to repeat
# on every request and filled the logs (V23-68).
_miner_fallback_warning_emitted: set[str] = set()


class APIKeyAuthenticator:
    """Shared service API-key dependency.

    Reads the configured header (default ``X-Api-Key``) and compares it against
    an expected key using constant-time comparison. When ``auth_enabled`` is
    false, the dependency always succeeds. This replaces the hand-rolled
    API-key checks in wallet, trading, and other services.
    """

    def __init__(
        self,
        expected_key: str | None,
        auth_enabled: bool = True,
        header_name: str = "X-Api-Key",
        success_role: str = "admin",
    ) -> None:
        self.expected_key = expected_key
        self.auth_enabled = auth_enabled
        self.header_name = header_name
        self.success_role = success_role

    async def __call__(self, request: Request) -> dict[str, Any]:
        if not self.auth_enabled:
            return {"sub": "api_key", "role": self.success_role, "auth_type": "api_key"}

        if not self.expected_key:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="API key not configured",
            )

        api_key = request.headers.get(self.header_name)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
            )

        if not hmac.compare_digest(str(api_key), str(self.expected_key)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return {"sub": "api_key", "role": self.success_role, "auth_type": "api_key"}


from .jwt import verify_access_token


def get_token(authorization: str | None = Header(default=None, alias="Authorization")) -> str:
    """Extract Bearer token from Authorization header.

    Args:
        authorization: Authorization header value.

    Returns:
        Token string.

    Raises:
        HTTPException: If header is missing or malformed.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:]  # Remove "Bearer " prefix


def require_auth(token: str = Depends(get_token)) -> dict[str, Any]:
    """Require valid JWT token (any role).

    Returns:
        Token payload.

    Raises:
        HTTPException: If token is invalid.
    """
    return verify_access_token(token)


def require_admin(token: str = Depends(get_token)) -> dict[str, Any]:
    """Require admin role.

    Returns:
        Token payload.

    Raises:
        HTTPException: If token is invalid or role is not admin.
    """
    return verify_access_token(token, required_role="admin")


def require_client(token: str = Depends(get_token)) -> dict[str, Any]:
    """Require client role.

    Returns:
        Token payload.

    Raises:
        HTTPException: If token is invalid or role is not client.
    """
    return verify_access_token(token, required_role="client")


def require_miner_jwt(token: str = Depends(get_token)) -> dict[str, Any]:
    """Require miner role via JWT.

    Returns:
        Token payload.

    Raises:
        HTTPException: If token is invalid or role is not miner.
    """
    return verify_access_token(token, required_role="miner")


def require_miner_api_key(request: Request) -> dict[str, Any]:
    """Authenticate miner via X-Api-Key header (legacy/internal service auth).

    Validates the API key against the ``miner_api_keys`` config setting.
    Falls back to ``COORDINATOR_API_KEY`` env var if miner_api_keys is empty.

    Returns:
        Dict with "sub" (miner_id) and "role" ("miner").

    Raises:
        HTTPException: If API key is missing or invalid.
    """
    api_key = request.headers.get("X-Api-Key")
    miner_id = request.headers.get("X-Miner-ID")

    allowed_keys: list[str] = []
    # Try to load from config settings (coordinator-api specific)
    try:
        from coordinator_api.config import settings as config_settings

        allowed_keys = config_settings.miner_api_keys
    except (ImportError, AttributeError):
        pass

    if not allowed_keys:
        coord_key = os.getenv("COORDINATOR_API_KEY", "")
        if coord_key:
            # This is why COORDINATOR_API_KEY must never be published (V23-68): with
            # `miner_api_keys` unset — the default — it silently becomes a miner credential
            # for every endpoint behind this dependency. Set MINER_API_KEYS to stop the
            # fallback. Warned once per process rather than removed because deployed miners
            # may rely on it; a silent promotion is the part worth ending.
            if "warned" not in _miner_fallback_warning_emitted:
                _miner_fallback_warning_emitted.add("warned")
                logger.warning(
                    "miner_api_keys is empty; accepting COORDINATOR_API_KEY as a miner credential. "
                    "Set MINER_API_KEYS to scope miner access properly."
                )
            allowed_keys = [coord_key]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    # ponytail: constant-time comparison across the configured key list; list
    # length is not secret, and this avoids a short-circuit timing leak.
    api_key_str = str(api_key)
    valid = False
    for allowed in allowed_keys:
        try:
            valid = valid | hmac.compare_digest(api_key_str, str(allowed))
        except TypeError:
            pass
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    sub = miner_id or api_key
    return {"sub": sub, "role": "miner"}


def require_miner(request: Request) -> dict[str, Any]:
    """Require miner authentication — tries JWT first, falls back to API key.

    This supports both JWT-based auth (Authorization: Bearer <token>)
    and legacy API key auth (X-Api-Key header) for internal services
    like the local GPU miner.

    Returns:
        Token payload dict with "sub" and "role".

    Raises:
        HTTPException: If neither auth method succeeds.
    """
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization[7:]
            return verify_access_token(token, required_role="miner")
        except HTTPException:
            pass

    return require_miner_api_key(request)


# Type aliases for dependency injection
AuthDep = Annotated[dict[str, Any], Depends(require_auth)]
AdminDep = Annotated[dict[str, Any], Depends(require_admin)]
ClientDep = Annotated[dict[str, Any], Depends(require_client)]
MinerDep = Annotated[dict[str, Any], Depends(require_miner)]
APIKeyAuth = Annotated[dict[str, Any], Depends(APIKeyAuthenticator)]


__all__ = [
    "AdminDep",
    "APIKeyAuth",
    "APIKeyAuthenticator",
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
]
