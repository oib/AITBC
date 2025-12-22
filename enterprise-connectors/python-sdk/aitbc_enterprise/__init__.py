"""
AITBC Enterprise Connectors SDK

Python SDK for integrating AITBC with enterprise systems including
payment processors, ERP systems, and other business applications.
"""

__version__ = "1.0.0"
__author__ = "AITBC Team"

from .core import AITBCClient, ConnectorConfig
from .base import BaseConnector
from .exceptions import (
    AITBCError,
    AuthenticationError,
    RateLimitError,
    APIError,
    ConfigurationError
)

__all__ = [
    "AITBCClient",
    "ConnectorConfig",
    "BaseConnector",
    "AITBCError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    "ConfigurationError",
]
