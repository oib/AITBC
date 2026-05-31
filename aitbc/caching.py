"""
Caching utilities for AITBC
Provides caching strategies for expensive operations
"""

import functools
import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with value and expiration"""
    value: Any
    expires_at: datetime | None = None
    hit_count: int = 0

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


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

        # Check expiration
        if entry.is_expired():
            self._misses += 1
            del self.cache[key]
            return None

        # Move to end (most recently used)
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
            expires_at = datetime.now() + timedelta(seconds=ttl)

        # Remove existing entry if present
        if key in self.cache:
            del self.cache[key]

        # Add new entry
        self.cache[key] = CacheEntry(value=value, expires_at=expires_at)
        self.cache.move_to_end(key)

        # Evict least recently used if over capacity
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
            "total_requests": total_requests
        }

    def print_stats(self) -> None:
        """Print cache statistics"""
        stats = self.get_stats()
        logger.info("LRU Cache Statistics:")
        logger.info(f"  Capacity: {stats['capacity']}")
        logger.info(f"  Size: {stats['size']}")
        logger.info(f"  Hits: {stats['hits']}")
        logger.info(f"  Misses: {stats['misses']}")
        logger.info(f"  Hit rate: {stats['hit_rate']:.2%}")


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

        # Check expiration
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

        expires_at = datetime.now() + timedelta(seconds=ttl)
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
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.info(f"Removed {len(expired_keys)} expired cache entries")

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
            "total_requests": total_requests
        }


def cached(ttl: int = 300, cache_instance: LRUCache | TTLCache | None = None):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds
        cache_instance: Custom cache instance, or None to use default TTL cache
        
    Returns:
        Decorated function with caching
    """
    if cache_instance is None:
        cache_instance = TTLCache(default_ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Generate cache key from function name and arguments
            cache_key = _generate_cache_key(func.__name__, args, kwargs)

            # Try to get from cache
            cached_value = cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl=ttl)

            return result

        wrapper.cache = cache_instance  # Attach cache to function
        return wrapper

    return decorator


def cached_lru(capacity: int = 128, ttl: int | None = None):
    """
    Decorator to cache function results with LRU eviction
    
    Args:
        capacity: Maximum cache size
        ttl: Time to live in seconds (None for no expiration)
        
    Returns:
        Decorated function with LRU caching
    """
    cache_instance = LRUCache(capacity=capacity)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache_key = _generate_cache_key(func.__name__, args, kwargs)

            cached_value = cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl=ttl)

            return result

        wrapper.cache = cache_instance
        return wrapper

    return decorator


def _generate_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """
    Generate a cache key from function name and arguments
    
    Args:
        func_name: Function name
        args: Function positional arguments
        kwargs: Function keyword arguments
        
    Returns:
        Cache key string
    """
    # Convert arguments to hashable representation
    key_parts = [func_name]

    # Add positional arguments
    for arg in args:
        if isinstance(arg, (str, int, float, bool, type(None))):
            key_parts.append(str(arg))
        else:
            key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest())

    # Add keyword arguments (sorted for consistency)
    for key in sorted(kwargs.keys()):
        value = kwargs[key]
        if isinstance(value, (str, int, float, bool, type(None))):
            key_parts.append(f"{key}={value}")
        else:
            key_parts.append(f"{key}={hashlib.md5(json.dumps(value, sort_keys=True).encode()).hexdigest()}")

    return ":".join(key_parts)


# Global cache instances
_global_lru_cache = LRUCache(capacity=256)
_global_ttl_cache = TTLCache(default_ttl=300)


def get_global_lru_cache() -> LRUCache:
    """Get global LRU cache instance"""
    return _global_lru_cache


def get_global_ttl_cache() -> TTLCache:
    """Get global TTL cache instance"""
    return _global_ttl_cache


def clear_global_caches() -> None:
    """Clear all global caches"""
    _global_lru_cache.clear()
    _global_ttl_cache.clear()
    logger.info("All global caches cleared")
