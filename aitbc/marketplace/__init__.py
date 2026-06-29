"""AITBC marketplace shared utilities (v0.6.6).

Provides:
- OfferFSM: formal offer state machine with validated transitions
- OfferStatus: offer lifecycle status enum
- BlockchainRPCClient: chain-aware blockchain RPC client for marketplace operations
"""

from __future__ import annotations

from .blockchain_rpc import BlockchainRPCClient
from .offer_fsm import OfferFSM, OfferStatus

__all__ = [
    "BlockchainRPCClient",
    "OfferFSM",
    "OfferStatus",
]
