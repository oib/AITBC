"""
LRU (Least Recently Used) cache implementation
"""

from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc.aitbc_logging import get_logger
from .cache_entry import CacheEntry

logger = get_logger(__name__)


class LRUCache:
    """
    Least Recently Used (LRU) cache implementation.
    Automatically evicts least recently used items when capacity is reached.
    """

    def __init__(self, capacity: int = 128):
        """
        Initialize LRU cache

        Args:
            capacity: Maximum number of items in cache
        """
        self.capacity = capacity
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
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
        self.cache.move_to_end(key)
        entry.hit_count += 1
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None for no expiration)
        """
        expires_at = None
        if ttl is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        if key in self.cache:
            del self.cache[key]
        self.cache[key] = CacheEntry(value=value, expires_at=expires_at)
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("LRU cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0
        return {
            "capacity": self.capacity,
            "size": len(self.cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
        }

    def print_stats(self) -> None:
        """Print cache statistics"""
        stats = self.get_stats()
        logger.info("LRU Cache Statistics:")
        logger.info("  Capacity: %s", stats["capacity"])
        logger.info("  Size: %s", stats["size"])
        logger.info("  Hits: %s", stats["hits"])
        logger.info("  Misses: %s", stats["misses"])
        logger.info("  Hit rate: %s", stats["hit_rate"])
