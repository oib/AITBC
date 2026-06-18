"""
Cache layer for HTTP client responses
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from ..aitbc_logging import get_logger


class CacheLayer:
    """HTTP response caching layer"""

    def __init__(self, enable: bool = False, ttl: int = 300, enable_logging: bool = False):
        """
        Initialize cache layer.

        Args:
            enable: Enable caching
            ttl: Cache time-to-live in seconds
            enable_logging: Enable logging of cache operations
        """
        self.enable = enable
        self.ttl = ttl
        self.enable_logging = enable_logging
        self.cache: dict[str, tuple[dict[str, Any], datetime]] = {}
        self.logger = get_logger(__name__)

    def get_cache_key(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key from URL and params."""
        if params:
            param_str = str(sorted(params.items()))
            return f"{url}:{hashlib.sha256(param_str.encode()).hexdigest()}"
        return url

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached response if available and not expired."""
        if not self.enable:
            return None
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if (datetime.now(UTC) - timestamp).total_seconds() < self.ttl:
                if self.enable_logging:
                    self.logger.info("Cache hit for %s", cache_key)
                return data
            else:
                del self.cache[cache_key]
                if self.enable_logging:
                    self.logger.info("Cache expired for %s", cache_key)
        return None

    def set(self, cache_key: str, data: dict[str, Any]) -> None:
        """Cache response data."""
        if self.enable:
            self.cache[cache_key] = (data, datetime.now(UTC))
            if self.enable_logging:
                self.logger.info("Cached response for %s", cache_key)

    def invalidate(self, cache_key: str) -> bool:
        """Invalidate a specific cache entry."""
        if cache_key in self.cache:
            del self.cache[cache_key]
            if self.enable_logging:
                self.logger.info("Cache invalidated for %s", cache_key)
            return True
        return False

    def clear(self) -> int:
        """Clear all cache entries."""
        count = len(self.cache)
        self.cache.clear()
        if self.enable_logging:
            self.logger.info("Cache cleared (%s entries)", count)
        return count

    def cleanup_expired(self) -> int:
        """Remove expired cache entries."""
        now = datetime.now()
        expired_keys = [key for key, (_, timestamp) in self.cache.items() if (now - timestamp).total_seconds() >= self.ttl]
        for key in expired_keys:
            del self.cache[key]
        if self.enable_logging and expired_keys:
            self.logger.info("Cleaned up %s expired cache entries", len(expired_keys))
        return len(expired_keys)

    def get_state(self) -> dict[str, Any]:
        """Get current cache state."""
        return {
            "enable": self.enable,
            "ttl": self.ttl,
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys()),
        }
