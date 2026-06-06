"""
Redis caching utilities for AITBC applications
Provides distributed caching with Redis backend
"""

import hashlib
import json
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis package not installed. Caching will be disabled.")


class RedisCache:
    """
    Redis cache implementation for distributed caching
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_connections: int = 10,
        timeout: int = 5,
        default_ttl: int = 3600
    ):
        """
        Initialize Redis cache
        
        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            max_connections: Maximum number of connections
            timeout: Connection timeout in seconds
            default_ttl: Default time-to-live for cached items in seconds
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.timeout = timeout
        self.default_ttl = default_ttl
        self._client = None

        if REDIS_AVAILABLE and redis_url:
            try:
                self._client = redis.Redis.from_url(
                    redis_url,
                    max_connections=max_connections,
                    socket_timeout=timeout,
                    socket_connect_timeout=timeout,
                    decode_responses=True
                )
                # Test connection
                self._client.ping()
                logger.info(f"Connected to Redis at {redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._client = None
        else:
            logger.info("Redis caching disabled (Redis not available or no URL provided)")

    def is_available(self) -> bool:
        """Check if Redis cache is available"""
        return self._client is not None

    def get(self, key: str) -> Any | None:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.is_available():
            return None

        try:
            value = self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time-to-live in seconds (uses default_ttl if not provided)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            serialized = json.dumps(value)
            expiry = ttl if ttl is not None else self.default_ttl
            self._client.setex(key, expiry, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.is_available():
            return False

        try:
            return self._client.exists(key) == 1
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False

    def clear(self) -> bool:
        """
        Clear all cached values
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            self._client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Redis clear error: {e}")
            return False

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """
        Get multiple values from cache
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dictionary mapping keys to cached values
        """
        if not self.is_available():
            return {}

        try:
            values = self._client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    result[key] = json.loads(value)
            return result
        except Exception as e:
            logger.error(f"Redis get_many error: {e}")
            return {}

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """
        Set multiple values in cache
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time-to-live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            pipe = self._client.pipeline()
            expiry = ttl if ttl is not None else self.default_ttl
            for key, value in mapping.items():
                serialized = json.dumps(value)
                pipe.setex(key, expiry, serialized)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis set_many error: {e}")
            return False

    def delete_many(self, keys: list[str]) -> bool:
        """
        Delete multiple values from cache
        
        Args:
            keys: List of cache keys
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            if keys:
                self._client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Redis delete_many error: {e}")
            return False

    def increment(self, key: str, amount: int = 1) -> int | None:
        """
        Increment a counter in cache
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            New value or None if failed
        """
        if not self.is_available():
            return None

        try:
            return self._client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis increment error: {e}")
            return None

    def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            self._client.close()
            logger.info("Redis connection closed")


# Global cache instance
_global_cache: RedisCache | None = None


def get_cache(
    redis_url: str | None = None,
    max_connections: int = 10,
    timeout: int = 5,
    default_ttl: int = 3600
) -> RedisCache:
    """
    Get or create global Redis cache instance
    
    Args:
        redis_url: Redis connection URL
        max_connections: Maximum number of connections
        timeout: Connection timeout in seconds
        default_ttl: Default time-to-live for cached items
        
    Returns:
        RedisCache instance
    """
    global _global_cache

    if _global_cache is None and redis_url:
        _global_cache = RedisCache(
            redis_url=redis_url,
            max_connections=max_connections,
            timeout=timeout,
            default_ttl=default_ttl
        )

    return _global_cache or RedisCache()  # Return disabled cache if no URL


def cache_key(*parts: str, prefix: str = "aitbc") -> str:
    """
    Generate a cache key from parts
    
    Args:
        *parts: Parts to include in the key
        prefix: Key prefix
        
    Returns:
        Cache key string
    """
    key_string = ":".join(str(part) for part in parts)
    full_key = f"{prefix}:{key_string}"
    # Hash if too long
    if len(full_key) > 250:
        hash_value = hashlib.sha256(full_key.encode()).hexdigest()[:16]
        return f"{prefix}:hashed:{hash_value}"
    return full_key
