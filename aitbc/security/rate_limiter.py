"""
Rate limiter for inbound HTTP API rate limiting.

This is the per-key (per-IP) rate limiter used by the @rate_limit
decorator (aitbc/rate_limiting.py) and RateLimitMiddleware to protect
HTTP endpoints from abuse. Uses a sliding-window algorithm with
is_allowed(key) -> bool semantics.

The outbound HTTP client rate limiter in aitbc/network/rate_limiter.py
is a separate class with a different API (check()/record_request() ->
raises RateLimitError) for controlling outbound request rates. Both
implement the same sliding-window algorithm but serve different
purposes and are intentionally kept separate.
"""

import time

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter
    Limits the number of requests per time window
    """

    def __init__(self, rate: int, per: int):
        """
        Initialize rate limiter

        Args:
            rate: Number of requests allowed per time period
            per: Time period in seconds
        """
        self.rate = rate
        self.per = per
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """
        Check if request is allowed for given key

        Args:
            key: Identifier for the request (e.g., user ID, IP address)

        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        window_start = now - self.per

        # Get existing requests for this key
        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests outside the time window
        self._requests[key] = [req_time for req_time in self._requests[key] if req_time > window_start]

        # Check if under rate limit
        if len(self._requests[key]) < self.rate:
            self._requests[key].append(now)
            return True
        else:
            logger.warning("Rate limit exceeded for %s", key)
            return False

    def reset(self, key: str) -> None:
        """
        Reset rate limit for a specific key

        Args:
            key: Identifier to reset
        """
        if key in self._requests:
            del self._requests[key]

    def get_remaining(self, key: str) -> int:
        """
        Get remaining requests for a key

        Args:
            key: Identifier to check

        Returns:
            Number of remaining requests
        """
        now = time.time()
        window_start = now - self.per

        if key not in self._requests:
            return self.rate

        # Remove old requests
        self._requests[key] = [req_time for req_time in self._requests[key] if req_time > window_start]

        return self.rate - len(self._requests[key])
