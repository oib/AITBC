"""
Redis cache wrapper for distributed caching
"""

import json
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
        except Exception as e:
            logger.warning("Redis connection failed, falling back to in-memory cache: %s", e)
            self._client = None

    def get(self, key: str) -> Any | None:
        if self._client:
            try:
                raw = self._client.get(key)
            except Exception as e:
                logger.warning("Redis GET failed for key %s: %s", key, e)
            else:
                if raw is None:
                    return None
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # ponytail: legacy primitive stored without JSON encoding
                    return raw
                except Exception as e:
                    logger.warning("Redis GET decode failed for key %s: %s", key, e)
                    return raw
        return self._data.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if self._client:
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError) as e:
                logger.warning("Redis cache value for key %s is not JSON serializable: %s", key, e)
                return False
            try:
                self._client.setex(key, ttl or self._default_ttl, serialized)
                return True
            except Exception as e:
                logger.warning("Redis SET failed for key %s, falling back to in-memory: %s", key, e)
        self._data[key] = value
        return True

    def delete(self, key: str) -> bool:
        if self._client:
            try:
                return bool(self._client.delete(key))
            except Exception as e:
                logger.warning("Redis DELETE failed for key %s: %s", key, e)
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
