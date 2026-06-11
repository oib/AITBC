"""
AITBC Redis Caching Module (Legacy Shim)

DEPRECATED: This module is preserved for backward compatibility.
New code should import from ``aitbc.cache`` (the canonical caching package).

This shim delegates to ``aitbc.cache.backends.redis.RedisCache`` and
``aitbc.cache.decorators`` to ensure a single source of truth for caching
logic while keeping the old ``AITBCCache`` API intact.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.cache.backends.redis import RedisCache
from aitbc.cache.decorators import cache_with_ttl, cached
from aitbc.cache.utils import generate_cache_key

logger = logging.getLogger(__name__)


class AITBCCache:
    """Backward-compatible Redis cache wrapper.

    Internally delegates to :class:`aitbc.cache.backends.redis.RedisCache`.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        default_ttl: int = 300,
        key_prefix: str = "aitbc",
    ):
        from aitbc.cache.base import CacheConfig

        config = CacheConfig(
            backend="redis",
            host=host,
            port=port,
            db=db,
            password=password,
            default_ttl=default_ttl,
            key_prefix=key_prefix,
        )
        self._backend = RedisCache(config)
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        # Expose the raw redis client for code that checks ``cache.client``
        self.client = self._backend.client

    def _make_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def get(self, key: str) -> Any | None:
        return self._backend.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return self._backend.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        return self._backend.delete(key)

    def delete_pattern(self, pattern: str) -> int:
        return self._backend.delete_pattern(pattern)

    def clear(self) -> bool:
        return self._backend.clear()

    def exists(self, key: str) -> bool:
        return self._backend.exists(key)

    def get_stats(self) -> dict[str, Any]:
        return self._backend.get_stats()


# Global singleton – preserved for backward compatibility
_cache_instance: AITBCCache | None = None


def get_cache() -> AITBCCache:
    """Return the global :class:`AITBCCache` singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AITBCCache()
    return _cache_instance


def cache_result(key: str, ttl: int | None = None):
    """Backward-compatible decorator powered by ``aitbc.cache.decorators``."""
    return cache_with_ttl(ttl=ttl or 300, key_prefix=key)


class CacheKeys:
    """Predefined cache key templates."""

    BLOCK = "block:{height}"
    BLOCK_HEAD = "block:head"
    BLOCK_HEIGHT = "block:height"
    ACCOUNT = "account:{address}"
    ACCOUNT_BALANCE = "account:{address}:balance"
    GPU = "gpu:{gpu_id}"
    GPUS = "gpus:all"
    SERVICE = "service:{service_name}"
    SERVICES = "services:all"
    API_RESPONSE = "api:{endpoint}:{params_hash}"


__all__ = [
    "AITBCCache",
    "get_cache",
    "cache_result",
    "CacheKeys",
    "cache_with_ttl",
    "cached",
    "generate_cache_key",
]
