"""
DEPRECATED: Use ``aitbc.caching`` instead.

This module is a backward-compatibility shim. All symbols are re-exported
from :mod:`aitbc.caching`.
"""

from aitbc.caching import (
    BlockchainCache,
    CacheEntry,
    CacheInvalidator,
    CacheMetrics,
    LRUCache,
    TTLCache,
    cached,
    cached_blockchain,
    cached_lru,
    clear_global_caches,
    generate_cache_key,
    get_blockchain_cache,
    get_cache_metrics,
    get_global_lru_cache,
    get_global_ttl_cache,
)

__all__ = [
    "BlockchainCache",
    "CacheEntry",
    "CacheInvalidator",
    "CacheMetrics",
    "LRUCache",
    "TTLCache",
    "cached",
    "cached_blockchain",
    "cached_lru",
    "clear_global_caches",
    "generate_cache_key",
    "get_blockchain_cache",
    "get_cache_metrics",
    "get_global_lru_cache",
    "get_global_ttl_cache",
]
