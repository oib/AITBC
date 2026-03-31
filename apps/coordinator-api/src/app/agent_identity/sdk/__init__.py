"""
AITBC Agent Identity SDK
Python SDK for agent identity management and cross-chain operations
"""

from .client import AgentIdentityClient
from .exceptions import *
from .models import *

__version__ = "1.0.0"
__author__ = "AITBC Team"
__email__ = "dev@aitbc.io"

__all__ = [
    "AgentIdentityClient",
    "AgentIdentity",
    "CrossChainMapping",
    "AgentWallet",
    "IdentityStatus",
    "VerificationType",
    "ChainType",
    "AgentIdentityError",
    "VerificationError",
    "WalletError",
    "NetworkError",
]
