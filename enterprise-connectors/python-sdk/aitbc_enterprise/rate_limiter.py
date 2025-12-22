"""
Rate limiting for AITBC Enterprise Connectors
"""

import asyncio
import time
from typing import Optional, Dict, Any
from collections import deque
from dataclasses import dataclass

from .core import ConnectorConfig
from .exceptions import RateLimitError


@dataclass
class RateLimitInfo:
    """Rate limit information"""
    limit: int
    remaining: int
    reset_time: float
    retry_after: Optional[int] = None


class TokenBucket:
    """Token bucket rate limiter"""
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # Tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from bucket"""
        async with self._lock:
            now = time.time()
            
            # Refill tokens
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            
            # Check if enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    async def wait_for_token(self, tokens: int = 1):
        """Wait until token is available"""
        while not await self.acquire(tokens):
            # Calculate wait time
            wait_time = (tokens - self.tokens) / self.rate
            await asyncio.sleep(wait_time)


class SlidingWindowCounter:
    """Sliding window rate limiter"""
    
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window  # Window size in seconds
        self.requests = deque()
        self._lock = asyncio.Lock()
    
    async def is_allowed(self) -> bool:
        """Check if request is allowed"""
        async with self._lock:
            now = time.time()
            
            # Remove old requests
            while self.requests and self.requests[0] <= now - self.window:
                self.requests.popleft()
            
            # Check if under limit
            if len(self.requests) < self.limit:
                self.requests.append(now)
                return True
            
            return False
    
    async def wait_for_slot(self):
        """Wait until request slot is available"""
        while not await self.is_allowed():
            # Calculate wait time until oldest request expires
            if self.requests:
                wait_time = self.requests[0] + self.window - time.time()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)


class RateLimiter:
    """Rate limiter with multiple strategies"""
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Initialize rate limiters
        self._token_bucket = None
        self._sliding_window = None
        self._strategy = "token_bucket"
        
        if config.rate_limit:
            # Default to token bucket with burst capacity
            burst = config.burst_limit or config.rate_limit * 2
            self._token_bucket = TokenBucket(
                rate=config.rate_limit,
                capacity=burst
            )
        
        # Track rate limit info from server
        self._server_limits: Dict[str, RateLimitInfo] = {}
    
    async def acquire(self, endpoint: str = None) -> None:
        """Acquire rate limit permit"""
        if self._strategy == "token_bucket" and self._token_bucket:
            await self._token_bucket.wait_for_token()
        elif self._strategy == "sliding_window" and self._sliding_window:
            await self._sliding_window.wait_for_slot()
        
        # Check server-side limits
        if endpoint and endpoint in self._server_limits:
            limit_info = self._server_limits[endpoint]
            
            if limit_info.remaining <= 0:
                wait_time = limit_info.reset_time - time.time()
                if wait_time > 0:
                    raise RateLimitError(
                        f"Rate limit exceeded for {endpoint}",
                        retry_after=int(wait_time) + 1
                    )
    
    def update_server_limit(self, endpoint: str, headers: Dict[str, str]):
        """Update rate limit info from server response"""
        # Parse common rate limit headers
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        retry_after = headers.get("Retry-After")
        
        if limit or remaining or reset:
            self._server_limits[endpoint] = RateLimitInfo(
                limit=int(limit) if limit else 0,
                remaining=int(remaining) if remaining else 0,
                reset_time=float(reset) if reset else time.time() + 3600,
                retry_after=int(retry_after) if retry_after else None
            )
            
            self.logger.debug(
                f"Updated rate limit for {endpoint}: "
                f"{remaining}/{limit} remaining"
            )
    
    def get_limit_info(self, endpoint: str = None) -> Optional[RateLimitInfo]:
        """Get current rate limit info"""
        if endpoint and endpoint in self._server_limits:
            return self._server_limits[endpoint]
        
        # Return configured limit if no server limit
        if self.config.rate_limit:
            return RateLimitInfo(
                limit=self.config.rate_limit,
                remaining=self.config.rate_limit,  # Approximate
                reset_time=time.time() + 3600
            )
        
        return None
    
    def set_strategy(self, strategy: str):
        """Set rate limiting strategy"""
        if strategy not in ["token_bucket", "sliding_window", "none"]:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        self._strategy = strategy
    
    def reset(self):
        """Reset rate limiter state"""
        if self._token_bucket:
            self._token_bucket.tokens = self._token_bucket.capacity
            self._token_bucket.last_refill = time.time()
        
        if self._sliding_window:
            self._sliding_window.requests.clear()
        
        self._server_limits.clear()
        self.logger.info("Rate limiter reset")
