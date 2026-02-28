"""
Caching strategy for expensive queries
"""

from datetime import datetime, timedelta
from typing import Any, Optional, Dict
from functools import wraps
import hashlib
import json
from aitbc.logging import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "evictions": 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self._cache:
            self._stats["misses"] += 1
            return None
        
        cache_entry = self._cache[key]
        
        # Check if expired
        if datetime.now() > cache_entry["expires_at"]:
            del self._cache[key]
            self._stats["evictions"] += 1
            self._stats["misses"] += 1
            return None
        
        self._stats["hits"] += 1
        logger.debug(f"Cache hit for key: {key}")
        return cache_entry["value"]
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL"""
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        
        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
            "created_at": datetime.now(),
            "ttl": ttl_seconds
        }
        
        self._stats["sets"] += 1
        logger.debug(f"Cache set for key: {key}, TTL: {ttl_seconds}s")
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed"""
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry["expires_at"]
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        self._stats["evictions"] += len(expired_keys)
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self._stats,
            "total_entries": len(self._cache),
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests
        }


# Global cache manager instance
cache_manager = CacheManager()


def cache_key_generator(*args, **kwargs) -> str:
    """Generate a cache key from function arguments"""
    # Create a deterministic string representation
    key_parts = []
    
    # Add function args
    for arg in args:
        if hasattr(arg, '__dict__'):
            # For objects, use their dict representation
            key_parts.append(str(sorted(arg.__dict__.items())))
        else:
            key_parts.append(str(arg))
    
    # Add function kwargs
    if kwargs:
        key_parts.append(str(sorted(kwargs.items())))
    
    # Create hash for consistent key length
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}{func.__name__}_{cache_key_generator(*args, **kwargs)}"
            
            # Try to get from cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}{func.__name__}_{cache_key_generator(*args, **kwargs)}"
            
            # Try to get from cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl_seconds)
            
            return result
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Cache configurations for different query types
CACHE_CONFIGS = {
    "marketplace_stats": {"ttl": 300, "prefix": "marketplace_"},  # 5 minutes
    "job_list": {"ttl": 60, "prefix": "jobs_"},                  # 1 minute
    "miner_list": {"ttl": 120, "prefix": "miners_"},               # 2 minutes
    "user_balance": {"ttl": 30, "prefix": "balance_"},             # 30 seconds
    "exchange_rates": {"ttl": 600, "prefix": "rates_"},            # 10 minutes
}


def get_cache_config(cache_type: str) -> Dict[str, Any]:
    """Get cache configuration for a specific type"""
    return CACHE_CONFIGS.get(cache_type, {"ttl": 300, "prefix": ""})


# Periodic cleanup task
async def cleanup_expired_cache():
    """Background task to clean up expired cache entries"""
    while True:
        try:
            removed_count = cache_manager.cleanup_expired()
            if removed_count > 0:
                logger.info(f"Background cleanup removed {removed_count} expired entries")
            
            # Run cleanup every 5 minutes
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute on error


# Cache warming utilities
class CacheWarmer:
    """Utility class for warming up cache with common queries"""
    
    def __init__(self, session):
        self.session = session
    
    async def warm_marketplace_stats(self):
        """Warm up marketplace statistics cache"""
        try:
            from ..services.marketplace import MarketplaceService
            service = MarketplaceService(self.session)
            
            # Cache common stats queries
            stats = await service.get_stats()
            cache_manager.set("marketplace_stats_overview", stats, ttl_seconds=300)
            
            logger.info("Marketplace stats cache warmed up")
            
        except Exception as e:
            logger.error(f"Failed to warm marketplace stats cache: {e}")
    
    async def warm_exchange_rates(self):
        """Warm up exchange rates cache"""
        try:
            # This would call an exchange rate API
            # For now, just set a placeholder
            rates = {"AITBC_BTC": 0.00001, "AITBC_USD": 0.10}
            cache_manager.set("exchange_rates_current", rates, ttl_seconds=600)
            
            logger.info("Exchange rates cache warmed up")
            
        except Exception as e:
            logger.error(f"Failed to warm exchange rates cache: {e}")


# Cache middleware for FastAPI
async def cache_middleware(request, call_next):
    """FastAPI middleware to add cache headers and track cache performance"""
    response = await call_next(request)
    
    # Add cache statistics to response headers (for debugging)
    stats = cache_manager.get_stats()
    response.headers["X-Cache-Hits"] = str(stats["hits"])
    response.headers["X-Cache-Misses"] = str(stats["misses"])
    response.headers["X-Cache-Hit-Rate"] = f"{stats['hit_rate_percent']}%"
    
    return response
