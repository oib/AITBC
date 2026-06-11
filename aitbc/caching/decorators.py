"""
Cache decorators for function result caching.
"""

import functools
from collections.abc import Callable
from datetime import datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

from .blockchain import BlockchainCache
from .lru import LRUCache
from .ttl import TTLCache
from .utils import _generate_blockchain_cache_key, _generate_cache_key

logger = get_logger(__name__)


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


# Blockchain-specific caching decorators

def cached_blockchain(operation: str, ttl: int | None = None):
    """
    Decorator for caching blockchain operations with automatic invalidation
    
    Args:
        operation: Type of blockchain operation (account_balance, block, transaction, etc.)
        ttl: Custom TTL in seconds, or None to use blockchain cache defaults
    
    Returns:
        Decorated function with blockchain caching
    """
    from aitbc.cache import get_cache as _get_cache

    # Get blockchain cache instance
    redis_cache = _get_cache()
    blockchain_cache = BlockchainCache(redis_cache=redis_cache)
    
    # Set default TTL based on operation type
    if ttl is None:
        ttl_map = {
            "account_balance": BlockchainCache.TTL_ACCOUNT_BALANCE,
            "block": BlockchainCache.TTL_BLOCK,
            "transaction": BlockchainCache.TTL_TRANSACTION,
            "contract_state": BlockchainCache.TTL_CONTRACT_STATE,
            "chain_state": BlockchainCache.TTL_CHAIN_STATE,
            "market_data": BlockchainCache.TTL_MARKET_DATA
        }
        ttl = ttl_map.get(operation, 300)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            metrics = get_cache_metrics()
            start_time = datetime.now()
            
            # Generate blockchain-specific cache key
            cache_key = _generate_blockchain_cache_key(operation, args, kwargs)
            
            # Try to get from cache
            cached_value = blockchain_cache.get(cache_key)
            if cached_value is not None:
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                metrics.record_hit(operation, duration_ms)
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            
            # Cache result
            if operation == "account_balance":
                chain_id = kwargs.get("chain_id", args[0] if args else "default")
                address = kwargs.get("address", args[1] if len(args) > 1 else "")
                blockchain_cache.set_account_balance(address, chain_id, result)
            elif operation == "block":
                chain_id = kwargs.get("chain_id", args[0] if args else "default")
                block_number = kwargs.get("block_number", args[1] if len(args) > 1 else "")
                blockchain_cache.set_block(block_number, chain_id, result)
            elif operation == "transaction":
                chain_id = kwargs.get("chain_id", args[0] if args else "default")
                tx_hash = kwargs.get("tx_hash", args[1] if len(args) > 1 else "")
                blockchain_cache.set_transaction(tx_hash, chain_id, result)
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_miss(operation, duration_ms)
            
            return result

        return wrapper
    return decorator
