"""
Network utilities for AITBC
Provides HTTP client and Web3 utilities
"""

from .client import AITBCHTTPClient, AsyncAITBCHTTPClient
from .compression import compress, compress_json, compression_ratio, decompress, decompress_json
from .http_pool import SharedHttpClient
from .island_registry import IslandRegistry, IslandRegistryEntry
from .subscription_manager import SubscriptionClientProtocol, SubscriptionEntry, SubscriptionManager
from .web3_utils import Web3Client, create_web3_client

__all__ = [
    "AITBCHTTPClient",
    "AsyncAITBCHTTPClient",
    "IslandRegistry",
    "IslandRegistryEntry",
    "SharedHttpClient",
    "SubscriptionClientProtocol",
    "SubscriptionEntry",
    "SubscriptionManager",
    "Web3Client",
    "compress",
    "compress_json",
    "compression_ratio",
    "create_web3_client",
    "decompress",
    "decompress_json",
]
