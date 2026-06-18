"""
Cache entry dataclass with expiration tracking
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class CacheEntry:
    """Cache entry with value and expiration"""

    value: Any
    expires_at: datetime | None = None
    hit_count: int = 0
    created_at: datetime | None = None
    last_accessed: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.last_accessed is None:
            self.last_accessed = datetime.now(UTC)

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.expires_at is None:
            return False
        now = datetime.now(UTC)
        if self.expires_at.tzinfo is None:
            # Compare naive datetime by treating both as naive
            return now.replace(tzinfo=None) > self.expires_at
        return now > self.expires_at

    def update_access(self):
        """Update last access time"""
        self.last_accessed = datetime.now(UTC)
