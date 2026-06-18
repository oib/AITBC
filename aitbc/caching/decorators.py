"""
Caching decorators for function memoization
"""

import functools
import hashlib
import json
from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger
from .lru_cache import LRUCache
from .metrics import get_cache_metrics
from .ttl_cache import TTLCache

logger = get_logger(__name__)


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
    key_parts = [func_name]
    for arg in args:
        if isinstance(arg, str | int | float | bool | type(None)):
            key_parts.append(str(arg))
        else:
            key_parts.append(hashlib.sha256(json.dumps(arg, sort_keys=True).encode()).hexdigest())
    for key in sorted(kwargs.keys()):
        value = kwargs[key]
        if isinstance(value, str | int | float | bool | type(None)):
            key_parts.append(f"{key}={value}")
        else:
            key_parts.append(f"{key}={hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()}")
    return ":".join(key_parts)


def generate_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a consistent cache key from arguments.

    Public alias of ``_generate_cache_key`` with a signature matching the
    legacy ``aitbc.cache.utils.generate_cache_key`` API.
    """
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    for k in sorted(kwargs.keys()):
        key_parts.append(f"{k}={kwargs[k]}")
    key_string = ":".join(key_parts)
    if len(key_string) > 200:
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"{prefix}:{key_hash}"
    return key_string


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
            cache_key = _generate_cache_key(func.__name__, args, kwargs)
            cached_value = cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value
            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl=ttl)
            return result

        wrapper.cache = cache_instance  # type: ignore[attr-defined]
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

        wrapper.cache = cache_instance  # type: ignore[attr-defined]
        return wrapper

    return decorator
