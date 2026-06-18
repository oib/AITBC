"""
Rate limiter implementation for HTTP client
"""

from datetime import UTC, datetime
from typing import Any

from ..aitbc_logging import get_logger
from ..exceptions import RateLimitError


class RateLimiter:
    """Token bucket rate limiter for controlling request rates"""

    def __init__(self, rate_limit: int | None = None, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            rate_limit: Maximum requests per window (None = no limit)
            window_seconds: Time window in seconds
        """
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.request_times: list[datetime] = []
        self.logger = get_logger(__name__)

    def check(self) -> None:
        """Check if rate limit is exceeded and raise exception if so."""
        if not self.rate_limit:
            return
        now = datetime.now(UTC)
        self.request_times = [t for t in self.request_times if (now - t).total_seconds() < self.window_seconds]
        if len(self.request_times) >= self.rate_limit:
            raise RateLimitError(f"Rate limit exceeded: {self.rate_limit} requests per {self.window_seconds} seconds")

    def record_request(self) -> None:
        """Record a request timestamp for rate limiting."""
        if self.rate_limit:
            self.request_times.append(datetime.now(UTC))

    def get_state(self) -> dict[str, Any]:
        """Get current rate limiter state."""
        now = datetime.now(UTC)
        recent_requests = [t for t in self.request_times if (now - t).total_seconds() < self.window_seconds]
        return {
            "rate_limit": self.rate_limit,
            "window_seconds": self.window_seconds,
            "current_requests": len(recent_requests),
            "request_times": [t.isoformat() for t in recent_requests],
        }
