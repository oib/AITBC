"""
Caching utilities for AITBC
Provides caching strategies for expensive operations including blockchain-specific caching

This module consolidates caching functionality split into logical submodules.
"""

from .blockchain import BlockchainCache, get_blockchain_cache
from .decorators import (
    cached,
    cached_lru,
    cached_blockchain,
    get_global_lru_cache,
    get_global_ttl_cache,
    clear_global_caches,
)
from .invalidator import CacheInvalidator
from .lru import LRUCache
from .metrics import CacheMetrics, get_cache_metrics
from .ttl import TTLCache
from .utils import CacheEntry

__all__ = [
    "CacheEntry",
    "BlockchainCache",
    "get_blockchain_cache",
    "CacheMetrics",
    "get_cache_metrics",
    "LRUCache",
    "TTLCache",
    "cached",
    "cached_lru",
    "cached_blockchain",
    "get_global_lru_cache",
    "get_global_ttl_cache",
    "clear_global_caches",
    "CacheInvalidator",
]
