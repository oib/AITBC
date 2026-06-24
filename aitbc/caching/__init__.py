"""
Caching utilities for AITBC
Provides caching strategies for expensive operations including blockchain-specific caching
"""

from aitbc.aitbc_logging import get_logger

from .blockchain_cache import BlockchainCache
from .blockchain_decorator import cached_blockchain
from .cache_entry import CacheEntry
from .decorators import _generate_cache_key, cached, cached_lru, generate_cache_key
from .invalidator import CacheInvalidator
from .lru_cache import LRUCache
from .metrics import CacheMetrics, get_cache_metrics
from .redis_cache import RedisCache, get_cache
from .ttl_cache import TTLCache

logger = get_logger(__name__)

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


def get_blockchain_cache(redis_url: str | None = None) -> BlockchainCache:
    """
    Get or create global blockchain cache instance

    Args:
        redis_url: Redis connection URL

    Returns:
        BlockchainCache instance
    """
    redis_cache = get_cache(redis_url=redis_url)
    return BlockchainCache(redis_cache=redis_cache)


__all__ = [
    "BlockchainCache",
    "CacheEntry",
    "CacheInvalidator",
    "CacheMetrics",
    "LRUCache",
    "RedisCache",
    "TTLCache",
    "_generate_cache_key",  # Internal utility, tests depend on it
    "cached",
    "cached_blockchain",
    "cached_lru",
    "clear_global_caches",
    "generate_cache_key",
    "get_blockchain_cache",
    "get_cache",
    "get_cache_metrics",
    "get_global_lru_cache",
    "get_global_ttl_cache",
]
