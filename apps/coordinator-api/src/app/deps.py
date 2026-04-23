

"""
Dependency injection module for AITBC Coordinator API

Provides unified dependency injection using storage.Annotated[Session, Depends(get_session)].
"""

from collections.abc import Callable

from fastapi import Header, HTTPException

from .config import settings


def _validate_api_key(allowed_keys: list[str], api_key: str | None) -> str:
    # In development mode, allow any API key for testing
    import os

    if os.getenv("APP_ENV", "dev") == "dev":
        print(f"DEBUG: Development mode - allowing API key {'*' * 32 if api_key else 'None'}")  # Mask API key
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
        print(f"DEBUG: Received API key: {'*' * 32 if api_key else 'None'}")  # Mask API key
        print(f"DEBUG: Allowed admin keys: {'*' * 32 if settings.admin_api_keys else 'None'}")  # Mask keys
        result = _validate_api_key(settings.admin_api_keys, api_key)
        print(f"DEBUG: Validation result: {'*' * 32 if result else 'None'}")  # Mask result
        return result

    return validator


# Legacy aliases for backward compatibility
def get_session():
    """Legacy alias - use Annotated[Session, Depends(get_session)] instead."""
    from .storage import get_session

    return get_session()
