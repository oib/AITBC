"""
Base cache interface and abstract classes for AITBC caching system.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Union
from datetime import timedelta


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store value in cache with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cached values."""
        pass
    
    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        pass


class CacheConfig:
    """Configuration for cache backends."""
    
    def __init__(
        self,
        backend: str = "redis",
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        default_ttl: int = 300,
        key_prefix: str = "aitbc",
        max_size: Optional[int] = None,
        **kwargs
    ):
        self.backend = backend
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.max_size = max_size
        self.extra = kwargs
    
    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "backend": self.backend,
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": self.password,
            "default_ttl": self.default_ttl,
            "key_prefix": self.key_prefix,
            "max_size": self.max_size,
            **self.extra
        }
