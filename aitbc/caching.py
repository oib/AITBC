"""
Caching utilities for AITBC
Provides caching strategies for expensive operations including blockchain-specific caching
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
    created_at: datetime = None
    last_accessed: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_accessed is None:
            self.last_accessed = datetime.now()

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def update_access(self):
        """Update last access time"""
        self.last_accessed = datetime.now()


class BlockchainCache:
    """
    Specialized cache for blockchain operations with intelligent invalidation
    """
    
    # Cache key prefixes for different blockchain data types
    PREFIX_ACCOUNT_BALANCE = "account_balance"
    PREFIX_BLOCK = "block"
    PREFIX_TRANSACTION = "transaction"
    PREFIX_CONTRACT_STATE = "contract_state"
    PREFIX_CHAIN_STATE = "chain_state"
    PREFIX_MARKET_DATA = "market_data"
    
    # Default TTL for different data types (in seconds)
    TTL_ACCOUNT_BALANCE = 30  # Account balances change frequently
    TTL_BLOCK = 3600  # Block data is stable for longer
    TTL_TRANSACTION = 86400  # Transaction data is immutable
    TTL_CONTRACT_STATE = 60  # Contract state changes frequently
    TTL_CHAIN_STATE = 10  # Chain state changes very frequently
    TTL_MARKET_DATA = 300  # Market data changes moderately
    
    def __init__(self, redis_cache=None):
        """
        Initialize blockchain cache
        
        Args:
            redis_cache: Optional RedisCache instance for distributed caching
        """
        self.redis_cache = redis_cache
        self.invalidation_subscribers = []
        
    def generate_account_key(self, address: str, chain_id: int) -> str:
        """Generate cache key for account balance"""
        return f"{self.PREFIX_ACCOUNT_BALANCE}:{chain_id}:{address.lower()}"
    
    def generate_block_key(self, block_number: int, chain_id: int) -> str:
        """Generate cache key for block data"""
        return f"{self.PREFIX_BLOCK}:{chain_id}:{block_number}"
    
    def generate_transaction_key(self, tx_hash: str, chain_id: int) -> str:
        """Generate cache key for transaction"""
        return f"{self.PREFIX_TRANSACTION}:{chain_id}:{tx_hash.lower()}"
    
    def generate_contract_state_key(self, contract_address: str, chain_id: int, slot: str = "") -> str:
        """Generate cache key for contract state"""
        slot_suffix = f":{slot}" if slot else ""
        return f"{self.PREFIX_CONTRACT_STATE}:{chain_id}:{contract_address.lower()}{slot_suffix}"
    
    def generate_chain_state_key(self, chain_id: int, state_type: str) -> str:
        """Generate cache key for chain state"""
        return f"{self.PREFIX_CHAIN_STATE}:{chain_id}:{state_type}"
    
    def generate_market_data_key(self, market_type: str, asset_pair: str) -> str:
        """Generate cache key for market data"""
        return f"{self.PREFIX_MARKET_DATA}:{market_type}:{asset_pair}"
    
    def get_account_balance(self, address: str, chain_id: int) -> Any | None:
        """Get cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_account_balance(self, address: str, chain_id: int, balance: Any) -> bool:
        """Cache account balance with short TTL"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, balance, ttl=self.TTL_ACCOUNT_BALANCE)
        return False
    
    def get_block(self, block_number: int, chain_id: int) -> Any | None:
        """Get cached block data"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_block(self, block_number: int, chain_id: int, block_data: Any) -> bool:
        """Cache block data with long TTL"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, block_data, ttl=self.TTL_BLOCK)
        return False
    
    def get_transaction(self, tx_hash: str, chain_id: int) -> Any | None:
        """Get cached transaction data"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_transaction(self, tx_hash: str, chain_id: int, tx_data: Any) -> bool:
        """Cache transaction data with very long TTL"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, tx_data, ttl=self.TTL_TRANSACTION)
        return False
    
    def invalidate_account(self, address: str, chain_id: int) -> bool:
        """Invalidate cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("account", {"address": address, "chain_id": chain_id})
            return success
        return False
    
    def invalidate_block(self, block_number: int, chain_id: int) -> bool:
        """Invalidate cached block data"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("block", {"block_number": block_number, "chain_id": chain_id})
            return success
        return False
    
    def invalidate_contract_state(self, contract_address: str, chain_id: int, slot: str = "") -> bool:
        """Invalidate cached contract state"""
        key = self.generate_contract_state_key(contract_address, chain_id, slot)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("contract", {"address": contract_address, "chain_id": chain_id, "slot": slot})
            return success
        return False
    
    def invalidate_chain_state(self, chain_id: int, state_type: str | None = None) -> int:
        """Invalidate chain state cache entries"""
        if state_type:
            # Invalidate specific state type
            key = self.generate_chain_state_key(chain_id, state_type)
            if self.redis_cache:
                success = self.redis_cache.delete(key)
                if success:
                    self._notify_subscribers("chain_state", {"chain_id": chain_id, "state_type": state_type})
                return 1 if success else 0
            return 0
        else:
            # Invalidate all chain state for this chain
            pattern = f"{self.PREFIX_CHAIN_STATE}:{chain_id}:*"
            if self.redis_cache and self.redis_cache._client:
                try:
                    keys = self.redis_cache._client.keys(pattern)
                    if keys:
                        deleted = self.redis_cache._client.delete(*keys)
                        self._notify_subscribers("chain_state", {"chain_id": chain_id, "all": True})
                        return deleted
                except Exception as e:
                    logger.error(f"Error invalidating chain state: {e}")
            return 0
    
    def subscribe_to_invalidation(self, callback: Callable) -> None:
        """Subscribe to cache invalidation events"""
        self.invalidation_subscribers.append(callback)
    
    def _notify_subscribers(self, cache_type: str, data: dict[str, Any]) -> None:
        """Notify subscribers of cache invalidation"""
        for callback in self.invalidation_subscribers:
            try:
                callback(cache_type, data)
            except Exception as e:
                logger.error(f"Error in cache invalidation callback: {e}")
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get blockchain cache statistics"""
        stats = {
            "redis_available": self.redis_cache is not None and self.redis_cache.is_available(),
            "subscribers": len(self.invalidation_subscribers),
            "prefixes": {
                "account_balance": self.PREFIX_ACCOUNT_BALANCE,
                "block": self.PREFIX_BLOCK,
                "transaction": self.PREFIX_TRANSACTION,
                "contract_state": self.PREFIX_CONTRACT_STATE,
                "chain_state": self.PREFIX_CHAIN_STATE,
                "market_data": self.PREFIX_MARKET_DATA
            },
            "default_ttl": {
                "account_balance": self.TTL_ACCOUNT_BALANCE,
                "block": self.TTL_BLOCK,
                "transaction": self.TTL_TRANSACTION,
                "contract_state": self.TTL_CONTRACT_STATE,
                "chain_state": self.TTL_CHAIN_STATE,
                "market_data": self.TTL_MARKET_DATA
            }
        }
        return stats


class CacheMetrics:
    """Track cache performance metrics"""
    
    def __init__(self):
        self.total_requests = 0
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.operation_times = []
        self.cache_operations = {}
    
    def record_hit(self, operation: str, duration_ms: float) -> None:
        """Record a cache hit"""
        self.total_requests += 1
        self.total_hits += 1
        self._record_operation(operation, duration_ms, "hit")
    
    def record_miss(self, operation: str, duration_ms: float) -> None:
        """Record a cache miss"""
        self.total_requests += 1
        self.total_misses += 1
        self._record_operation(operation, duration_ms, "miss")
    
    def record_error(self, operation: str, duration_ms: float) -> None:
        """Record a cache error"""
        self.total_requests += 1
        self.total_errors += 1
        self._record_operation(operation, duration_ms, "error")
    
    def _record_operation(self, operation: str, duration_ms: float, result: str) -> None:
        """Record individual operation details"""
        if operation not in self.cache_operations:
            self.cache_operations[operation] = {
                "hits": 0,
                "misses": 0,
                "errors": 0,
                "total": 0,
                "avg_duration_ms": []
            }
        
        op_stats = self.cache_operations[operation]
        op_stats["total"] += 1
        # Use the correct field name based on result
        if result == "hit":
            op_stats["hits"] += 1
        elif result == "miss":
            op_stats["misses"] += 1
        elif result == "error":
            op_stats["errors"] += 1
        op_stats["avg_duration_ms"].append(duration_ms)
        
        # Keep only last 100 duration measurements
        if len(op_stats["avg_duration_ms"]) > 100:
            op_stats["avg_duration_ms"] = op_stats["avg_duration_ms"][-100:]
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache performance statistics"""
        hit_rate = self.total_hits / self.total_requests if self.total_requests > 0 else 0
        miss_rate = self.total_misses / self.total_requests if self.total_requests > 0 else 0
        error_rate = self.total_errors / self.total_requests if self.total_requests > 0 else 0
        
        # Calculate average durations per operation
        operation_stats = {}
        for op, stats in self.cache_operations.items():
            avg_duration = sum(stats["avg_duration_ms"]) / len(stats["avg_duration_ms"]) if stats["avg_duration_ms"] else 0
            operation_stats[op] = {
                "hits": stats["hits"],
                "misses": stats["misses"],
                "errors": stats["errors"],
                "total": stats["total"],
                "hit_rate": stats["hits"] / stats["total"] if stats["total"] > 0 else 0,
                "avg_duration_ms": avg_duration
            }
        
        return {
            "total_requests": self.total_requests,
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "total_errors": self.total_errors,
            "hit_rate": hit_rate,
            "miss_rate": miss_rate,
            "error_rate": error_rate,
            "operation_stats": operation_stats
        }
    
    def reset(self) -> None:
        """Reset all metrics"""
        self.total_requests = 0
        self.total_hits = 0
        self.total_misses = 0
        self.total_errors = 0
        self.operation_times = []
        self.cache_operations = {}


# Global cache metrics instance
_global_metrics: CacheMetrics | None = None


def get_cache_metrics() -> CacheMetrics:
    """Get global cache metrics instance"""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = CacheMetrics()
    return _global_metrics


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
    from .redis_cache import get_cache
    
    # Get blockchain cache instance
    redis_cache = get_cache()
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
            
            # Generate cache key based on operation type and arguments
            cache_key = _generate_blockchain_cache_key(operation, args, kwargs)
            
            # Try to get from cache
            if redis_cache:
                cached_value = redis_cache.get(cache_key)
                if cached_value is not None:
                    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                    metrics.record_hit(f"blockchain_{operation}", duration_ms)
                    return cached_value
            
            # Execute function
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # Cache result
                if redis_cache:
                    redis_cache.set(cache_key, result, ttl=ttl)
                
                metrics.record_miss(f"blockchain_{operation}", duration_ms)
                return result
            except Exception as e:
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                metrics.record_error(f"blockchain_{operation}", duration_ms)
                raise
        
        wrapper.blockchain_cache = blockchain_cache
        wrapper.cache_operation = operation
        return wrapper
    
    return decorator


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
    # Start with operation prefix
    key_parts = [f"bc:{operation}"]
    
    # Add common blockchain parameters from kwargs
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
    
    # Add hash of other arguments for uniqueness
    other_args = str(args) + str(sorted(kwargs.items()))
    args_hash = hashlib.md5(other_args.encode()).hexdigest()[:8]
    key_parts.append(f"hash:{args_hash}")
    
    return ":".join(key_parts)


class CacheInvalidator:
    """
    Automatic cache invalidation based on blockchain events
    """
    
    def __init__(self, blockchain_cache: BlockchainCache):
        """
        Initialize cache invalidator
        
        Args:
            blockchain_cache: BlockchainCache instance to manage invalidation
        """
        self.blockchain_cache = blockchain_cache
        self.invalidation_rules = {
            "new_block": self._on_new_block,
            "new_transaction": self._on_new_transaction,
            "contract_state_changed": self._on_contract_state_changed,
            "account_balance_changed": self._on_account_balance_changed
        }
    
    def handle_event(self, event_type: str, event_data: dict[str, Any]) -> int:
        """
        Handle blockchain event and invalidate appropriate cache entries
        
        Args:
            event_type: Type of blockchain event
            event_data: Event data with relevant information
            
        Returns:
            Number of cache entries invalidated
        """
        handler = self.invalidation_rules.get(event_type)
        if handler:
            try:
                return handler(event_data)
            except Exception as e:
                logger.error(f"Error in cache invalidation handler for {event_type}: {e}")
                return 0
        return 0
    
    def _on_new_block(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new block is mined"""
        chain_id = event_data.get("chain_id")
        block_number = event_data.get("block_number")
        
        invalidated = 0
        
        # Invalidate the new block itself (will be cached with fresh data)
        if chain_id and block_number:
            if self.blockchain_cache.invalidate_block(block_number, chain_id):
                invalidated += 1
        
        # Invalidate chain state (block number, gas price, etc.)
        if chain_id:
            invalidated += self.blockchain_cache.invalidate_chain_state(chain_id)
        
        # Invalidate account balances that might have changed
        # This is a conservative approach - in production, you might be more selective
        if chain_id:
            invalidated += self._invalidate_all_account_balances(chain_id)
        
        logger.info(f"Invalidated {invalidated} cache entries for new block {block_number} on chain {chain_id}")
        return invalidated
    
    def _on_new_transaction(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new transaction is processed"""
        chain_id = event_data.get("chain_id")
        from_address = event_data.get("from_address")
        to_address = event_data.get("to_address")
        contract_address = event_data.get("contract_address")
        
        invalidated = 0
        
        # Invalidate account balances for sender and receiver
        if chain_id and from_address:
            if self.blockchain_cache.invalidate_account(from_address, chain_id):
                invalidated += 1
        
        if chain_id and to_address:
            if self.blockchain_cache.invalidate_account(to_address, chain_id):
                invalidated += 1
        
        # Invalidate contract state if relevant
        if chain_id and contract_address:
            if self.blockchain_cache.invalidate_contract_state(contract_address, chain_id):
                invalidated += 1
        
        logger.info(f"Invalidated {invalidated} cache entries for new transaction on chain {chain_id}")
        return invalidated
    
    def _on_contract_state_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when contract state changes"""
        chain_id = event_data.get("chain_id")
        contract_address = event_data.get("contract_address")
        slot = event_data.get("slot")
        
        if chain_id and contract_address:
            # Invalidate specific contract state
            invalidated = self.blockchain_cache.invalidate_contract_state(
                contract_address, chain_id, slot
            )
            
            # Also invalidate all contract state for this contract if this is a major change
            if not slot:  # No specific slot means broad state change
                invalidated += self.blockchain_cache.invalidate_contract_state(
                    contract_address, chain_id
                )
            
            logger.info(f"Invalidated {invalidated} contract cache entries for {contract_address}")
            return invalidated
        
        return 0
    
    def _on_account_balance_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when account balance changes"""
        chain_id = event_data.get("chain_id")
        address = event_data.get("address")
        
        if chain_id and address:
            if self.blockchain_cache.invalidate_account(address, chain_id):
                logger.info(f"Invalidated account cache for {address} on chain {chain_id}")
                return 1
        
        return 0
    
    def _invalidate_all_account_balances(self, chain_id: int) -> int:
        """Invalidate all account balances for a chain (conservative approach)"""
        # In a real implementation, you might track which accounts are affected
        # For now, this is a placeholder that would need Redis pattern matching
        if self.blockchain_cache.redis_cache and self.blockchain_cache.redis_cache._client:
            try:
                pattern = f"{BlockchainCache.PREFIX_ACCOUNT_BALANCE}:{chain_id}:*"
                keys = self.blockchain_cache.redis_cache._client.keys(pattern)
                if keys:
                    deleted = self.blockchain_cache.redis_cache._client.delete(*keys)
                    return deleted
            except Exception as e:
                logger.error(f"Error invalidating all account balances: {e}")
        return 0


def get_blockchain_cache(redis_url: str | None = None) -> BlockchainCache:
    """
    Get or create global blockchain cache instance
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        BlockchainCache instance
    """
    from .redis_cache import get_cache
    
    redis_cache = get_cache(redis_url=redis_url)
    return BlockchainCache(redis_cache=redis_cache)
