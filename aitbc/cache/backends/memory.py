"""
In-memory cache backends for AITBC caching system.
Provides LRU and TTL cache implementations for testing and fallback.
"""

import logging
import time
from collections import OrderedDict
from typing import Any, Optional

from ..base import CacheBackend, CacheConfig

logger = logging.getLogger(__name__)


class LRUCache(CacheBackend):
    """In-memory LRU (Least Recently Used) cache."""
    
    def __init__(self, config: CacheConfig):
        """
        Initialize LRU cache.
        
        Args:
            config: Cache configuration (max_size used for LRU limit)
        """
        self.config = config
        self.max_size = config.max_size or 1000
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache."""
        try:
            value, expiry = self.cache[key]
            # Check if expired
            if expiry and time.time() > expiry:
                del self.cache[key]
                self.misses += 1
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return value
        except KeyError:
            self.misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store value in cache with optional TTL."""
        try:
            expiry = time.time() + ttl if ttl else None
            
            # Remove oldest if at capacity
            if len(self.cache) >= self.max_size and key not in self.cache:
                self.cache.popitem(last=False)
            
            self.cache[key] = (value, expiry)
            self.cache.move_to_end(key)
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            del self.cache[key]
            return True
        except KeyError:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            value, expiry = self.cache[key]
            # Check if expired
            if expiry and time.time() > expiry:
                del self.cache[key]
                return False
            return True
        except KeyError:
            return False
    
    def clear(self) -> bool:
        """Clear all cached values."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        return True
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "status": "enabled",
            "connected": True,
            "total_keys": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate
        }


class TTLCache(CacheBackend):
    """In-memory TTL (Time-To-Live) cache."""
    
    def __init__(self, config: CacheConfig):
        """
        Initialize TTL cache.
        
        Args:
            config: Cache configuration
        """
        self.config = config
        self.default_ttl = config.default_ttl
        self.cache: dict[str, tuple[Any, float]] = {}
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache."""
        try:
            value, expiry = self.cache[key]
            # Check if expired
            if time.time() > expiry:
                del self.cache[key]
                self.misses += 1
                return None
            
            self.hits += 1
            return value
        except KeyError:
            self.misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store value in cache with optional TTL."""
        try:
            if ttl is None:
                ttl = self.default_ttl
            expiry = time.time() + ttl
            self.cache[key] = (value, expiry)
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        try:
            del self.cache[key]
            return True
        except KeyError:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            value, expiry = self.cache[key]
            # Check if expired
            if time.time() > expiry:
                del self.cache[key]
                return False
            return True
        except KeyError:
            return False
    
    def clear(self) -> bool:
        """Clear all cached values."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        return True
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "status": "enabled",
            "connected": True,
            "total_keys": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate
        }
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed."""
        current_time = time.time()
        expired_keys = [k for k, (_, expiry) in self.cache.items() if expiry < current_time]
        
        for key in expired_keys:
            del self.cache[key]
        
        return len(expired_keys)
