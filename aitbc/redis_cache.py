"""
DEPRECATED: Use ``aitbc.caching`` instead.

This module is a backward-compatibility shim.
"""

from aitbc.caching import (
    BlockchainCache,
    CacheEntry,
    CacheInvalidator,
    CacheMetrics,
    LRUCache,
    RedisCache,
    TTLCache,
    cached,
    cached_blockchain,
    cached_lru,
    clear_global_caches,
    generate_cache_key,
    get_blockchain_cache,
    get_cache,
    get_cache_metrics,
    get_global_lru_cache,
    get_global_ttl_cache,
)


def cache_key(*parts: str, prefix: str = "aitbc") -> str:
    """Generate a cache key from parts."""
    key_string = ":".join(str(part) for part in parts)
    full_key = f"{prefix}:{key_string}"
    if len(full_key) > 250:
        hash_value = __import__("hashlib").sha256(full_key.encode()).hexdigest()[:16]
        return f"{prefix}:hashed:{hash_value}"
    return full_key


__all__ = [
    "BlockchainCache",
    "CacheEntry",
    "CacheInvalidator",
    "CacheMetrics",
    "LRUCache",
    "RedisCache",
    "TTLCache",
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
    "cache_key",
]
