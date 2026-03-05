"""
Dependency injection module for AITBC Coordinator API

Provides unified dependency injection using storage.SessionDep.
"""

from typing import Callable
from fastapi import Depends, Header, HTTPException

from .config import settings
from .storage import SessionDep


def _validate_api_key(allowed_keys: list[str], api_key: str | None) -> str:
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


# Legacy aliases for backward compatibility
def get_session():
    """Legacy alias - use SessionDep instead."""
    from .storage import get_session
    return get_session()
