"""
Dependency injection module for AITBC Coordinator API

Provides unified dependency injection using storage.SessionDep.
"""

from typing import Callable
from fastapi import Depends, Header, HTTPException

from .config import settings
from .storage import SessionDep


class APIKeyValidator:
    """Validator for API key authentication."""
    
    def __init__(self, allowed_keys: list[str]):
        self.allowed_keys = {key.strip() for key in allowed_keys if key}

    def __call__(self, api_key: str | None = Header(default=None, alias="X-Api-Key")) -> str:
        if not api_key or api_key not in self.allowed_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return api_key


def require_client_key() -> Callable[[str | None], str]:
    """Dependency for client API key authentication."""
    return APIKeyValidator(settings.client_api_keys)


def require_miner_key() -> Callable[[str | None], str]:
    """Dependency for miner API key authentication."""
    return APIKeyValidator(settings.miner_api_keys)


def require_admin_key() -> Callable[[str | None], str]:
    """Dependency for admin API key authentication."""
    return APIKeyValidator(settings.admin_api_keys)


# Legacy aliases for backward compatibility
def get_session():
    """Legacy alias - use SessionDep instead."""
    from .storage import get_session
    return get_session()
