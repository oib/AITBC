"""
Cache decorators for AITBC services
Provides easy-to-use caching decorators for common patterns
"""

from functools import wraps
from typing import Any, Callable

from .cache import get_cache


def cache_blockchain_data(ttl: int = 60):
    """
    Cache blockchain data with short TTL
    
    Args:
        ttl: Time-to-live in seconds (default: 60s for blockchain data)
        
    Example:
        @cache_blockchain_data(ttl=30)
        def get_block(height):
            return blockchain.get_block(height)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_cache()
            if not cache.client:
                return func(*args, **kwargs)
            
            # Generate cache key
            key_parts = [func.__name__] + [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = ":".join(key_parts)
            
            # Try cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def cache_account_data(ttl: int = 300):
    """
    Cache account data with medium TTL
    
    Args:
        ttl: Time-to-live in seconds (default: 300s for account data)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_cache()
            if not cache.client:
                return func(*args, **kwargs)
            
            # Generate cache key
            key_parts = [func.__name__] + [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = ":".join(key_parts)
            
            # Try cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def cache_service_discovery(ttl: int = 600):
    """
    Cache service discovery data with long TTL
    
    Args:
        ttl: Time-to-live in seconds (default: 600s for service discovery)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_cache()
            if not cache.client:
                return func(*args, **kwargs)
            
            # Generate cache key
            key_parts = [func.__name__] + [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = ":".join(key_parts)
            
            # Try cache
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def invalidate_on_change(cache_key_pattern: str):
    """
    Invalidate cache when data changes
    
    Args:
        cache_key_pattern: Pattern of keys to invalidate
        
    Example:
        @invalidate_on_change("account:*")
        def update_account(address, data):
            return database.update_account(address, data)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            cache = get_cache()
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Invalidate cache
            if cache.client:
                cache.delete_pattern(cache_key_pattern)
            
            return result
        return wrapper
    return decorator
