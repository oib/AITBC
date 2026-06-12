"""
DEPRECATED: Use ``aitbc.caching`` instead.

This module is a backward-compatibility shim. All symbols are re-exported
from :mod:`aitbc.caching`.
"""

from aitbc.caching import (
    cached,
    cached_blockchain,
    cached_lru,
    clear_global_caches,
    generate_cache_key,
    get_global_lru_cache,
    get_global_ttl_cache,
)

__all__ = [
    "cached",
    "cached_blockchain",
    "cached_lru",
    "clear_global_caches",
    "generate_cache_key",
    "get_global_lru_cache",
    "get_global_ttl_cache",
]
