"""
AITBC Redis Caching Module
Provides caching functionality for frequently accessed data
"""

import json
import logging
from typing import Any, Optional, Union
from datetime import timedelta

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis library not available. Caching will be disabled.")

logger = logging.getLogger(__name__)


class AITBCCache:
    """Redis-based caching for AITBC services"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        default_ttl: int = 300,  # 5 minutes default
        key_prefix: str = "aitbc"
    ):
        """
        Initialize Redis cache connection
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
            default_ttl: Default time-to-live in seconds
            key_prefix: Prefix for all cache keys
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.client = None
        
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self.client.ping()
                logger.info(f"Connected to Redis at {host}:{port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.client = None
        else:
            logger.warning("Redis not available, caching disabled")
    
    def _make_key(self, key: str) -> str:
        """Create full cache key with prefix"""
        return f"{self.key_prefix}:{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            Cached value or None if not found
        """
        if not self.client:
            return None
        
        try:
            full_key = self._make_key(key)
            value = self.client.get(full_key)
            if value is not None:
                # Try to deserialize JSON
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key (without prefix)
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not specified)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            
            # Serialize value if it's not a string
            if not isinstance(value, str):
                value = json.dumps(value)
            
            if ttl is None:
                ttl = self.default_ttl
            
            return self.client.setex(full_key, ttl, value)
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            return bool(self.client.delete(full_key))
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        
        Args:
            pattern: Key pattern (without prefix)
            
        Returns:
            Number of keys deleted
        """
        if not self.client:
            return 0
        
        try:
            full_pattern = self._make_key(pattern)
            keys = self.client.keys(full_pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {e}")
            return 0
    
    def clear(self) -> bool:
        """
        Clear all AITBC cache keys
        
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            return False
        
        try:
            pattern = self._make_key("*")
            keys = self.client.keys(pattern)
            if keys:
                return bool(self.client.delete(*keys))
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            return bool(self.client.exists(full_key))
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.client:
            return {"status": "disabled"}
        
        try:
            info = self.client.info()
            pattern = self._make_key("*")
            keys = self.client.keys(pattern)
            
            return {
                "status": "enabled",
                "connected": True,
                "total_keys": len(keys),
                "memory_used": info.get("used_memory_human", "unknown"),
                "hit_rate": info.get("keyspace_hits", 0) / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"status": "error", "error": str(e)}


# Global cache instance
_cache_instance: Optional[AITBCCache] = None


def get_cache() -> AITBCCache:
    """
    Get global cache instance
    
    Returns:
        AITBCCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AITBCCache()
    return _cache_instance


def cache_result(
    key: str,
    ttl: Optional[int] = None
):
    """
    Decorator for caching function results
    
    Args:
        key: Cache key template (can use function args)
        ttl: Time-to-live in seconds
        
    Example:
        @cache_result("user:{user_id}", ttl=3600)
        def get_user(user_id):
            return database.get_user(user_id)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Generate cache key
            cache_key = key.format(*args, **kwargs)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


# Predefined cache keys for common AITBC data
class CacheKeys:
    """Predefined cache key templates"""
    
    # Blockchain data
    BLOCK = "block:{height}"
    BLOCK_HEAD = "block:head"
    BLOCK_HEIGHT = "block:height"
    
    # Account data
    ACCOUNT = "account:{address}"
    ACCOUNT_BALANCE = "account:{address}:balance"
    
    # GPU data
    GPU = "gpu:{gpu_id}"
    GPUS = "gpus:all"
    
    # Service discovery
    SERVICE = "service:{service_name}"
    SERVICES = "services:all"
    
    # API responses
    API_RESPONSE = "api:{endpoint}:{params_hash}"
