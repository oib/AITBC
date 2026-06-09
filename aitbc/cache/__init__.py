"""
AITBC Caching Module
Unified caching system with pluggable backends.
"""

from .base import CacheBackend, CacheConfig
from .backends import RedisCache, LRUCache, TTLCache, NullCache
from .decorators import get_cache, cache_with_ttl, cached
from .utils import generate_cache_key, serialize_value, deserialize_value

# Predefined cache keys for common AITBC data
class CacheKeys:
    """Predefined cache key templates."""
    
    # Blockchain data
    BLOCK = "block:{height}"
    BLOCK_HEAD = "block:head"
    BLOCK_HEIGHT = "block:height"
    ACCOUNT = "account:{address}"
    BALANCE = "balance:{address}"
    
    # Coordinator data
    JOB = "job:{job_id}"
    AGENT = "agent:{agent_id}"
    MARKETPLACE_OFFER = "offer:{offer_id}"
    
    # Translation data
    TRANSLATION = "translation:{source_lang}:{target_lang}:{text_hash}"
    
    # General
    HEALTH_CHECK = "health:{service}"

__all__ = [
    "CacheBackend",
    "CacheConfig",
    "RedisCache",
    "LRUCache",
    "TTLCache",
    "NullCache",
    "get_cache",
    "cache_with_ttl",
    "cached",
    "generate_cache_key",
    "serialize_value",
    "deserialize_value",
    "CacheKeys",
]
