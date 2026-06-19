"""
TTL (Time-To-Live) cache implementation
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc.aitbc_logging import get_logger

from .cache_entry import CacheEntry

logger = get_logger(__name__)


class TTLCache:
    """
    Time-To-Live (TTL) cache implementation.
    Items expire after a specified time regardless of usage.
    """

    def __init__(self, default_ttl: int = 300):
        """
        Initialize TTL cache

        Args:
            default_ttl: Default time to live in seconds
        """
        self.default_ttl = default_ttl
        self.cache: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self.cache:
            self._misses += 1
            return None
        entry = self.cache[key]
        if entry.is_expired():
            self._misses += 1
            del self.cache[key]
            return None
        entry.hit_count += 1
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self.default_ttl
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        self.cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("TTL cache cleared")

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache

        Returns:
            Number of entries removed
        """
        expired_keys = [key for key, entry in self.cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self.cache[key]
        if expired_keys:
            logger.info("Removed %s expired cache entries", len(expired_keys))
        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0
        return {
            "size": len(self.cache),
            "default_ttl": self.default_ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
        }
