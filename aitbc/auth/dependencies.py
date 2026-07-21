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


__all__ = [
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
]
