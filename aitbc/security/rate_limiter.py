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

# Upper bound on tracked keys. Keys are client IPs and one IPv6 /64 supplies
# unlimited distinct keys — without a cap the dict grows with attacker choice
# (RATELIMIT-KEY-RETENTION-1). At the cap the stalest entry is evicted; its
# owner just gets a fresh window, never a lockout.
_MAX_TRACKED_KEYS = 100_000


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
        self._last_sweep = time.time()

    def _sweep_stale_keys(self, now: float) -> None:
        """Drop keys whose newest request fell outside the window.

        Amortised: runs at most once per ``per`` seconds. The old code only
        pruned a key when that same key was queried again, so one-visit keys
        accumulated forever.
        """
        if now - self._last_sweep < self.per:
            return
        self._last_sweep = now
        window_start = now - self.per
        for key in [k for k, times in self._requests.items() if not times or times[-1] <= window_start]:
            del self._requests[key]

    def _evict_to_cap(self, now: float) -> None:
        """Enforce _MAX_TRACKED_KEYS when a new key arrives at a full table.

        Sweep first (cheap: stale keys leave for free), then evict the
        stalest entries until there is room. An evicted key is only reset,
        never refused.
        """
        self._last_sweep = now - self.per  # force the sweep branch
        self._sweep_stale_keys(now)
        while len(self._requests) >= _MAX_TRACKED_KEYS:
            stalest = min(self._requests, key=lambda k: self._requests[k][-1])
            del self._requests[stalest]

    def is_allowed(self, key: str) -> bool:
        """
        Check if request is allowed for given key

        Args:
            key: Identifier for the request (e.g., user ID, IP address)

        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        self._sweep_stale_keys(now)
        if key not in self._requests and len(self._requests) >= _MAX_TRACKED_KEYS:
            self._evict_to_cap(now)
        window_start = now - self.per

        # Get existing requests for this key
        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests outside the time window and drop empty keys
        self._requests[key] = [req_time for req_time in self._requests[key] if req_time > window_start]
        if not self._requests[key]:
            del self._requests[key]

        # Check if under rate limit
        if len(self._requests.get(key, [])) < self.rate:
            self._requests.setdefault(key, []).append(now)
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
        self._sweep_stale_keys(now)
        window_start = now - self.per

        if key not in self._requests:
            return self.rate

        # Remove old requests and drop empty keys
        self._requests[key] = [req_time for req_time in self._requests[key] if req_time > window_start]
        if not self._requests[key]:
            del self._requests[key]
            return self.rate

        return self.rate - len(self._requests[key])
