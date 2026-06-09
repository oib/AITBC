"""
No-op cache backend for testing and fallback.
"""

import logging
from typing import Any, Optional

from ..base import CacheBackend, CacheConfig

logger = logging.getLogger(__name__)


class NullCache(CacheBackend):
    """No-op cache backend that does nothing (for testing)."""
    
    def __init__(self, config: CacheConfig):
        """Initialize null cache."""
        self.config = config
        logger.warning("Using null cache backend - caching disabled")
    
    def get(self, key: str) -> Optional[Any]:
        """Always return None."""
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Always return True (no-op)."""
        return True
    
    def delete(self, key: str) -> bool:
        """Always return True (no-op)."""
        return True
    
    def exists(self, key: str) -> bool:
        """Always return False."""
        return False
    
    def clear(self) -> bool:
        """Always return True (no-op)."""
        return True
    
    def get_stats(self) -> dict[str, Any]:
        """Return disabled status."""
        return {"status": "disabled", "backend": "null"}
