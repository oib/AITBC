"""
Cache decorators for AITBC services (Legacy Shim)

DEPRECATED: This module is preserved for backward compatibility.
New code should import from ``aitbc.cache.decorators``.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from aitbc.cache import get_cache as _get_cache
from aitbc.cache.decorators import cache_with_ttl


def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
    parts = [func_name] + [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    return ":".join(parts)


def cache_blockchain_data(ttl: int = 60):
    """Cache blockchain data with short TTL."""
    return cache_with_ttl(ttl=ttl, key_prefix="blockchain")


def cache_account_data(ttl: int = 300):
    """Cache account data with medium TTL."""
    return cache_with_ttl(ttl=ttl, key_prefix="account")


def cache_service_discovery(ttl: int = 600):
    """Cache service discovery data with long TTL."""
    return cache_with_ttl(ttl=ttl, key_prefix="service_discovery")


def invalidate_on_change(cache_key_pattern: str):
    """Invalidate cache when data changes."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = _get_cache()
            result = func(*args, **kwargs)
            if cache.client:
                cache.delete_pattern(cache_key_pattern)
            return result
        return wrapper
    return decorator


__all__ = [
    "cache_blockchain_data",
    "cache_account_data",
    "cache_service_discovery",
    "invalidate_on_change",
]
