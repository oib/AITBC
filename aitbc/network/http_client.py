"""
DEPRECATED: AITBC HTTP Client
This module is deprecated. Use aitbc.network instead.

Base HTTP client with common utilities for AITBC applications
"""

import warnings

warnings.warn(
    "aitbc.network.http_client is deprecated, use aitbc.network instead",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new modules for backward compatibility
from .cache_layer import CacheLayer
from .circuit_breaker import CircuitBreaker
from .client import AITBCHTTPClient, AsyncAITBCHTTPClient
from .rate_limiter import RateLimiter
from .retry_policy import RetryPolicy

__all__ = [
    "AITBCHTTPClient",
    "AsyncAITBCHTTPClient",
    "CacheLayer",
    "CircuitBreaker",
    "RateLimiter",
    "RetryPolicy",
]
