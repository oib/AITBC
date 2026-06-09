"""
Redis backend for AITBC caching system.
Consolidates AITBCCache and RedisCache implementations.
"""

import json
import logging
from typing import Any, Optional

from ..base import CacheBackend, CacheConfig

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis library not available. Redis caching will be disabled.")

logger = logging.getLogger(__name__)


class RedisCache(CacheBackend):
    """Redis-based cache backend."""
    
    def __init__(self, config: Optional[CacheConfig] = None, **kwargs):
        """
        Initialize Redis cache backend.
        
        Args:
            config: Cache configuration (optional for backward compatibility)
            **kwargs: Alternative configuration (redis_url, default_ttl, etc.)
        """
        # Support old interface: RedisCache(redis_url=..., default_ttl=...)
        if config is None:
            redis_url = kwargs.get("redis_url", "redis://localhost:6379/0")
            default_ttl = kwargs.get("default_ttl", 300)
            key_prefix = kwargs.get("key_prefix", "aitbc")
            
            # Parse redis_url
            if redis_url.startswith("redis://"):
                # Parse redis://host:port/db
                parts = redis_url.replace("redis://", "").split("/")
                host_port = parts[0]
                db = int(parts[1]) if len(parts) > 1 else 0
                if ":" in host_port:
                    host, port = host_port.split(":")
                    port = int(port)
                else:
                    host = host_port
                    port = 6379
                
                config = CacheConfig(
                    backend="redis",
                    host=host,
                    port=port,
                    db=db,
                    default_ttl=default_ttl,
                    key_prefix=key_prefix
                )
            else:
                config = CacheConfig(backend="redis", default_ttl=default_ttl, key_prefix=key_prefix)
        
        self.config = config
        self.client = None
        self._max_connections = kwargs.get("max_connections", 10)
        self._timeout = kwargs.get("timeout", 5)
        
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(
                    host=config.host,
                    port=config.port,
                    db=config.db,
                    password=config.password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self.client.ping()
                logger.info(f"Connected to Redis at {config.host}:{config.port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.client = None
        else:
            logger.warning("Redis not available, caching disabled")
    
    def _make_key(self, key: str) -> str:
        """Create full cache key with prefix."""
        return f"{self.config.key_prefix}:{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache."""
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
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store value in cache with optional TTL."""
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            
            # Serialize value if it's not a string
            if not isinstance(value, str):
                value = json.dumps(value)
            
            if ttl is None:
                ttl = self.config.default_ttl
            
            return self.client.setex(full_key, ttl, value)
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            return bool(self.client.delete(full_key))
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.client:
            return False
        
        try:
            full_key = self._make_key(key)
            return bool(self.client.exists(full_key))
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cached values with the configured prefix."""
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
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
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
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
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
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter in cache."""
        if not self.client:
            return None
        
        try:
            full_key = self._make_key(key)
            return self.client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"Error incrementing cache key {key}: {e}")
            return None
    
    def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            self.client.close()
            logger.info("Redis connection closed")
    
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self.client is not None
