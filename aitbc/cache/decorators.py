"""
Cache decorators for function result caching.
"""

import functools
import logging
from typing import Any, Callable, Optional

from .backends import NullCache, RedisCache
from .base import CacheBackend, CacheConfig
from .utils import generate_cache_key

logger = logging.getLogger(__name__)

# Global cache instance
_cache_instance: Optional[CacheBackend] = None


def get_cache(backend: str = "redis", **kwargs) -> CacheBackend:
    """
    Get cache instance with specified backend.
    
    Args:
        backend: Backend type ("redis", "lru", "ttl", "null")
        **kwargs: Additional configuration
        
    Returns:
        Cache backend instance
    """
    config = CacheConfig(backend=backend, **kwargs)
    
    if backend == "redis":
        return RedisCache(config)
    elif backend == "lru":
        from .backends.memory import LRUCache
        return LRUCache(config)
    elif backend == "ttl":
        from .backends.memory import TTLCache
        return TTLCache(config)
    else:
        return NullCache(config)


def cache_with_ttl(ttl: int = 300, key_prefix: str = ""):
    """
    Parameterized cache decorator with TTL.
    
    Args:
        ttl: Time-to-live in seconds
        key_prefix: Prefix for cache keys
        
    Example:
        @cache_with_ttl(ttl=600, key_prefix="blockchain")
        def get_block(height: int) -> Block:
            return blockchain.get_block(height)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_cache()
            
            # Generate cache key
            cache_key = generate_cache_key(key_prefix or func.__name__, *args, **kwargs)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def cached(ttl: int = 300, key: Optional[str] = None):
    """
    Simple cache decorator (legacy compatibility).
    
    Args:
        ttl: Time-to-live in seconds
        key: Optional custom cache key
        
    Example:
        @cached(ttl=3600)
        def get_user(user_id: int) -> User:
            return database.get_user(user_id)
    """
    return cache_with_ttl(ttl=ttl, key_prefix=key or "")
