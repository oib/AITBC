"""
Redis cache wrapper for distributed caching
"""

import os
import time
from collections import OrderedDict
from typing import Any

import orjson

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Hosts that cannot reach the configured Redis only need to hear about it
# once — callers that re-instantiate the cache on a timer would otherwise
# spam the journal every tick.
_warned_urls: set[str] = set()

# #1755: bound on the in-memory fallback so a dead Redis cannot grow it
# without limit. 10k entries is far above any legitimate working set here
# (offer sync metadata, account balance/details keys).
_DEFAULT_FALLBACK_MAX_ENTRIES = 10_000


class RedisCache:
    """Minimal Redis cache wrapper for backward compatibility.

    When Redis is unreachable the cache degrades to a bounded in-process
    fallback. The fallback honors the same TTL semantics as the Redis path
    (``ttl or default_ttl`` seconds) and evicts least-recently-used entries
    past ``fallback_max_entries``. ``is_available()`` still reports only
    Redis reachability — callers that gate *invalidation deletes* on it are
    therefore Redis-only by design; in fallback mode staleness is instead
    bounded by the entry TTL.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_connections: int = 10,
        timeout: int = 5,
        default_ttl: int = 3600,
        fallback_max_entries: int = _DEFAULT_FALLBACK_MAX_ENTRIES,
    ) -> None:
        # Callers that pass nothing still reach the fleet-configured Redis:
        # service env files carry a credentialed REDIS_URL.
        url = redis_url or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
        self._url = url
        self._default_ttl = default_ttl
        self._fallback_max_entries = max(1, int(fallback_max_entries))
        self._client: Any = None
        # key -> (value, expires_at) where expires_at is a time.monotonic()
        # deadline or None for no expiry. OrderedDict gives LRU eviction.
        self._data: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        try:
            import redis

            self._client = redis.from_url(url)
            self._client.ping()
        except Exception as e:
            if url not in _warned_urls:
                _warned_urls.add(url)
                logger.warning("Redis connection failed, falling back to in-memory cache: %s", e)
            self._client = None

    def get(self, key: str) -> Any | None:
        if self._client:
            try:
                raw = self._client.get(key)
            except Exception as e:
                logger.warning("Redis GET failed for key %s: %s", key, e)
                return None
            if raw is None:
                return None
            try:
                return orjson.loads(raw)
            except Exception as e:
                logger.warning("Redis GET decode failed for key %s: %s", key, e)
                return None
        entry = self._data.get(key)
        if entry is None:
            return None
        # LRU touch: a hit makes this the most-recently-used entry.
        self._data.move_to_end(key)
        value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    def _fallback_expiry(self, ttl: int | None) -> float | None:
        """Monotonic deadline for a fallback entry, mirroring setex semantics."""
        effective_ttl = ttl or self._default_ttl
        if not effective_ttl or effective_ttl <= 0:
            return None
        return time.monotonic() + effective_ttl

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if self._client:
            try:
                serialized = orjson.dumps(value, default=str)
            except (TypeError, ValueError, orjson.JSONEncodeError) as e:
                logger.warning("Redis cache value for key %s is not JSON serializable: %s", key, e)
                return False
            try:
                self._client.setex(key, ttl or self._default_ttl, serialized)
                return True
            except Exception as e:
                logger.warning("Redis SET failed for key %s, falling back to in-memory: %s", key, e)
        if key not in self._data and len(self._data) >= self._fallback_max_entries:
            # Evict the least-recently-used entry to keep the fallback bounded.
            self._data.popitem(last=False)
        self._data[key] = (value, self._fallback_expiry(ttl))
        self._data.move_to_end(key)
        return True

    def delete(self, key: str) -> bool:
        if self._client:
            try:
                return bool(self._client.delete(key))
            except Exception as e:
                logger.warning("Redis DELETE failed for key %s: %s", key, e)
        existed = key in self._data
        self._data.pop(key, None)
        return existed

    def is_available(self) -> bool:
        """True only when the Redis backend is reachable.

        In fallback mode get/set/delete still work against the bounded
        in-memory map, but callers that gate invalidation deletes on this
        (e.g. account-cache invalidation in blockchain-node) deliberately
        stay Redis-only; fallback staleness is bounded by entry TTL (#1755).
        """
        return self._client is not None


_global_redis_cache: RedisCache | None = None


def get_cache(
    redis_url: str | None = None,
    max_connections: int = 10,
    timeout: int = 5,
    default_ttl: int = 3600,
    fallback_max_entries: int = _DEFAULT_FALLBACK_MAX_ENTRIES,
) -> RedisCache:
    """Get or create a Redis cache instance."""
    global _global_redis_cache
    if _global_redis_cache is None:
        _global_redis_cache = RedisCache(
            redis_url=redis_url,
            max_connections=max_connections,
            timeout=timeout,
            default_ttl=default_ttl,
            fallback_max_entries=fallback_max_entries,
        )
    return _global_redis_cache
