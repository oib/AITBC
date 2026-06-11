"""
Redis caching utilities for AITBC applications (Legacy Shim)

DEPRECATED: This module is preserved for backward compatibility.
New code should import from ``aitbc.cache`` (the canonical caching package).

This shim delegates to :class:`aitbc.cache.backends.redis.RedisCache` while
keeping the old ``RedisCache``, ``get_cache``, and ``cache_key`` APIs intact.
"""

from __future__ import annotations

import hashlib
from typing import Any

from aitbc.cache.backends.redis import RedisCache as _RedisCache
from aitbc.cache.utils import generate_cache_key


class RedisCache(_RedisCache):
    """Backward-compatible Redis cache.

    Inherits from :class:`aitbc.cache.backends.redis.RedisCache` so all
    behaviour is provided by the canonical backend.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_connections: int = 10,
        timeout: int = 5,
        default_ttl: int = 3600,
    ):
        # The canonical RedisCache already accepts ``redis_url``,
        # ``default_ttl``, ``max_connections``, and ``timeout`` via **kwargs.
        super().__init__(
            redis_url=redis_url,
            max_connections=max_connections,
            timeout=timeout,
            default_ttl=default_ttl,
        )


# Global singleton – preserved for backward compatibility
_global_cache: RedisCache | None = None


def get_cache(
    redis_url: str | None = None,
    max_connections: int = 10,
    timeout: int = 5,
    default_ttl: int = 3600,
) -> RedisCache:
    """Return the global :class:`RedisCache` singleton (or a disabled one)."""
    global _global_cache

    if _global_cache is None and redis_url:
        _global_cache = RedisCache(
            redis_url=redis_url,
            max_connections=max_connections,
            timeout=timeout,
            default_ttl=default_ttl,
        )

    return _global_cache or RedisCache()  # Return disabled cache if no URL


def cache_key(*parts: str, prefix: str = "aitbc") -> str:
    """Generate a cache key from parts."""
    key_string = ":".join(str(part) for part in parts)
    full_key = f"{prefix}:{key_string}"
    if len(full_key) > 250:
        hash_value = hashlib.sha256(full_key.encode()).hexdigest()[:16]
        return f"{prefix}:hashed:{hash_value}"
    return full_key


__all__ = ["RedisCache", "get_cache", "cache_key"]
