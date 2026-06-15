"""
Dependency injection module for AITBC Coordinator API

Provides unified dependency injection using storage.Annotated[Session, Depends(get_session)].
"""

from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException

from aitbc import get_logger

from .config import settings

logger = get_logger(__name__)


def _validate_api_key(allowed_keys: list[str], api_key: str | None) -> str:
    import os

    if os.getenv("APP_ENV", "dev") == "dev":
        logger.debug("Development mode - allowing API key %s", "*" * 32 if api_key else "None")
        return api_key or "dev_key"
    allowed = {key.strip() for key in allowed_keys if key}
    if not api_key or api_key not in allowed:
        raise HTTPException(status_code=401, detail="invalid api key")
    return api_key


def require_client_key() -> Callable[[str | None], str]:
    """Dependency for client API key authentication (reads live settings)."""

    def validator(api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        return _validate_api_key(settings.client_api_keys, api_key)

    return validator


def require_miner_key() -> Callable[[str | None], str]:
    """Dependency for miner API key authentication (reads live settings)."""

    def validator(api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        return _validate_api_key(settings.miner_api_keys, api_key)

    return validator


def get_miner_id() -> Callable[[str | None], str]:
    """Dependency to get miner ID from X-Miner-ID header."""

    def validator(miner_id: str | None = Header(default=None, alias="X-Miner-ID")) -> str:
        if not miner_id:
            raise HTTPException(status_code=400, detail="X-Miner-ID header required")
        return miner_id

    return validator


def require_admin_key() -> Callable[[str | None], str]:
    """Dependency for admin API key authentication (reads live settings)."""

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
    """Legacy API key validator class for backward compatibility."""

    def __init__(self, allowed_keys: list[str]) -> None:
        self.allowed_keys = allowed_keys

    def __call__(self, api_key: str | None = None) -> str:
        """Validate API key."""
        return _validate_api_key(self.allowed_keys, api_key)
