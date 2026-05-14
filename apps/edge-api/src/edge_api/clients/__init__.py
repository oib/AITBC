"""Clients for Edge API Service"""

from .blockchain_rpc import BlockchainRPCClient
from .gpu_service import GPUServiceClient

__all__ = [
    "BlockchainRPCClient",
    "GPUServiceClient",
]
