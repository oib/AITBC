"""
Blockchain-specific caching decorator
"""

import functools
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger
from .blockchain_cache import BlockchainCache
from .decorators import _generate_cache_key
from .metrics import get_cache_metrics
from .redis_cache import get_cache

logger = get_logger(__name__)


def _generate_blockchain_cache_key(operation: str, args: tuple, kwargs: dict) -> str:
    """
    Generate cache key for blockchain operations

    Args:
        operation: Type of blockchain operation
        args: Function positional arguments
        kwargs: Function keyword arguments

    Returns:
        Cache key string
    """
    key_parts = [f"bc:{operation}"]
    if "address" in kwargs:
        key_parts.append(f"addr:{kwargs['address'].lower()}")
    if "chain_id" in kwargs:
        key_parts.append(f"chain:{kwargs['chain_id']}")
    if "block_number" in kwargs:
        key_parts.append(f"block:{kwargs['block_number']}")
    if "tx_hash" in kwargs:
        key_parts.append(f"tx:{kwargs['tx_hash'].lower()}")
    if "contract_address" in kwargs:
        key_parts.append(f"contract:{kwargs['contract_address'].lower()}")
    other_args = str(args) + str(sorted(kwargs.items()))
    args_hash = hashlib.md5(other_args.encode()).hexdigest()[:8]
    key_parts.append(f"hash:{args_hash}")
    return ":".join(key_parts)


def cached_blockchain(operation: str, ttl: int | None = None):
    """
    Decorator for caching blockchain operations with automatic invalidation

    Args:
        operation: Type of blockchain operation (account_balance, block, transaction, etc.)
        ttl: Custom TTL in seconds, or None to use blockchain cache defaults

    Returns:
        Decorated function with blockchain caching
    """
    redis_cache = get_cache()
    blockchain_cache = BlockchainCache(redis_cache=redis_cache)
    if ttl is None:
        ttl_map = {
            "account_balance": BlockchainCache.TTL_ACCOUNT_BALANCE,
            "block": BlockchainCache.TTL_BLOCK,
            "transaction": BlockchainCache.TTL_TRANSACTION,
            "contract_state": BlockchainCache.TTL_CONTRACT_STATE,
            "chain_state": BlockchainCache.TTL_CHAIN_STATE,
            "market_data": BlockchainCache.TTL_MARKET_DATA,
        }
        ttl = ttl_map.get(operation, 300)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            metrics = get_cache_metrics()
            start_time = datetime.now(UTC)
            cache_key = _generate_blockchain_cache_key(operation, args, kwargs)
            if redis_cache:
                cached_value = redis_cache.get(cache_key)
                if cached_value is not None:
                    duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                    metrics.record_hit(f"blockchain_{operation}", duration_ms)
                    return cached_value
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                if redis_cache:
                    redis_cache.set(cache_key, result, ttl=ttl)
                metrics.record_miss(f"blockchain_{operation}", duration_ms)
                return result
            except Exception:
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                metrics.record_error(f"blockchain_{operation}", duration_ms)
                raise

        wrapper.blockchain_cache = blockchain_cache  # type: ignore[attr-defined]
        wrapper.cache_operation = operation  # type: ignore[attr-defined]
        return wrapper

    return decorator
