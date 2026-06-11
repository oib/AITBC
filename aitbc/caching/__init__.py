"""
Caching utilities for AITBC (Legacy Module)

.. deprecated::
    Use ``aitbc.cache`` (the canonical caching package) for new code.
    This module is kept for backward compatibility with existing tests
    and blockchain-specific decorators.
"""

from aitbc.aitbc_logging import get_logger

from .blockchain import BlockchainCache, get_blockchain_cache
from .decorators import (
    cached,
    cached_blockchain,
    cached_lru,
    clear_global_caches,
    get_global_lru_cache,
    get_global_ttl_cache,
)
from .invalidator import CacheInvalidator
from .lru import LRUCache
from .metrics import CacheMetrics, get_cache_metrics
from .ttl import TTLCache
from .utils import CacheEntry, _generate_cache_key

logger = get_logger(__name__)

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
    "_generate_cache_key",
    "logger",
]
