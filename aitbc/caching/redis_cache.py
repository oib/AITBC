"""
Redis cache wrapper for distributed caching
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Minimal Redis cache wrapper for backward compatibility."""

    def __init__(
        self, redis_url: str | None = None, max_connections: int = 10, timeout: int = 5, default_ttl: int = 3600
    ) -> None:
        self._url = redis_url
        self._default_ttl = default_ttl
        self._client: Any = None
        self._data: dict[str, Any] = {}
        try:
            import redis

            self._client = redis.from_url(redis_url or "redis://localhost:6379/0")
            self._client.ping()
        except Exception:
            self._client = None

    def get(self, key: str) -> Any | None:
        if self._client:
            try:
                return self._client.get(key)
            except Exception:
                pass
        return self._data.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if self._client:
            try:
                self._client.setex(key, ttl or self._default_ttl, value)
                return True
            except Exception:
                pass
        self._data[key] = value
        return True

    def delete(self, key: str) -> bool:
        if self._client:
            try:
                return bool(self._client.delete(key))
            except Exception:
                pass
        return key in self._data and (self._data.pop(key, None) is not None or True)

    def is_available(self) -> bool:
        return self._client is not None


_global_redis_cache: RedisCache | None = None


def get_cache(
    redis_url: str | None = None, max_connections: int = 10, timeout: int = 5, default_ttl: int = 3600
) -> RedisCache:
    """Get or create a Redis cache instance."""
    global _global_redis_cache
    if _global_redis_cache is None:
        _global_redis_cache = RedisCache(
            redis_url=redis_url, max_connections=max_connections, timeout=timeout, default_ttl=default_ttl
        )
    return _global_redis_cache
