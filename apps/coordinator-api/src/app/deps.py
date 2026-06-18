"""
Dependency injection module for AITBC Coordinator API

DEPRECATED: This module is deprecated. Use apps/coordinator-api/src/app/auth/ instead.
Provides unified dependency injection using storage.Annotated[Session, Depends(get_session)].
"""

import warnings
from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException

from aitbc.aitbc_logging import get_logger

from .config import settings

logger = get_logger(__name__)


def _validate_api_key(allowed_keys: list[str], api_key: str | None) -> str:
    warnings.warn(
        "API key auth is deprecated. Use JWT auth from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Only bypass in explicit dev/test, not production
    if settings.environment in ("development", "dev", "testing", "test"):
        logger.debug("Development mode - allowing API key %s", "*" * 32 if api_key else "None")
        return api_key or "dev_key"
    allowed = {key.strip() for key in allowed_keys if key}
    if not api_key or api_key not in allowed:
        raise HTTPException(status_code=401, detail="invalid api key")
    return api_key


def require_client_key() -> Callable[[str | None], str]:
    """Dependency for client API key authentication (reads live settings).

    DEPRECATED: Use ClientDep from app.auth.dependencies instead.
    """
    warnings.warn(
        "require_client_key() is deprecated. Use ClientDep from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def validator(api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        return _validate_api_key(settings.client_api_keys, api_key)

    return validator


def require_miner_key() -> Callable[[str | None], str]:
    """Dependency for miner API key authentication (reads live settings).

    DEPRECATED: Use MinerDep from app.auth.dependencies instead.
    """
    warnings.warn(
        "require_miner_key() is deprecated. Use MinerDep from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def validator(api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        return _validate_api_key(settings.miner_api_keys, api_key)

    return validator


def get_miner_id() -> Callable[[str | None], str]:
    """Dependency to get miner ID from X-Miner-ID header.

    DEPRECATED: Use MinerDep from app.auth.dependencies instead.
    The miner ID is now extracted from the JWT token (user['sub']).
    """
    warnings.warn(
        "get_miner_id() is deprecated. Use MinerDep from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def validator(miner_id: str | None = Header(default=None, alias="X-Miner-ID")) -> str:
        if not miner_id:
            raise HTTPException(status_code=400, detail="X-Miner-ID header required")
        return miner_id

    return validator


def require_admin_key() -> Callable[[str | None], str]:
    """Dependency for admin API key authentication (reads live settings).

    DEPRECATED: Use AdminDep from app.auth.dependencies instead.
    """
    warnings.warn(
        "require_admin_key() is deprecated. Use AdminDep from app.auth instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def validator(api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        logger.debug("Received API key: %s", "*" * 32 if api_key else "None")
        logger.debug("Allowed admin keys: %s", "*" * 32 if settings.admin_api_keys else "None")
        result = _validate_api_key(settings.admin_api_keys, api_key)
        logger.debug("Validation result: %s", "*" * 32 if result else "None")
        return result

    return validator


def get_session() -> Any:
    """Legacy alias - use Annotated[Session, Depends(get_session)] instead."""
    from .storage import get_session

    return get_session()


class APIKeyValidator:
    """Legacy API key validator class for backward compatibility.

    DEPRECATED: Use role-based dependencies from app.auth instead.
    """

    def __init__(self, allowed_keys: list[str]) -> None:
        self.allowed_keys = allowed_keys

    def __call__(self, api_key: str | None = None) -> str:
        """Validate API key."""
        warnings.warn(
            "APIKeyValidator is deprecated. Use role-based dependencies from app.auth instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _validate_api_key(self.allowed_keys, api_key)
