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
from .client import AITBCHTTPClient, AsyncAITBCHTTPClient

__all__ = ["AITBCHTTPClient", "AsyncAITBCHTTPClient"]
