"""Dependency injection module for AITBC Agent Management Service

Provides unified dependency injection using ServiceSettings.
"""

from collections.abc import Callable

from fastapi import Header, HTTPException

from .core.config import settings  # We'll create this file


def _validate_api_key(allowed_keys: list[str], api_key: str | None) -> str:
    # In development mode, allow any API key for testing
    import os

    if os.getenv("APP_ENV", "dev") == "dev":
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
        return _validate_api_key(settings.admin_api_keys, api_key)

    return validator


# Legacy APIKeyValidator class for backward compatibility with tests
class APIKeyValidator:
    """Legacy API key validator class for backward compatibility."""

    def __init__(self, allowed_keys: list[str]):
        self.allowed_keys = allowed_keys

    def __call__(self, api_key: str | None = None) -> str:
        """Validate API key."""
        return _validate_api_key(self.allowed_keys, api_key)