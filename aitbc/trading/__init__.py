"""AITBC inter-chain trading shared SDK (v0.8.0).

Provides:
- InterChainTradeStatus: enum for trade lifecycle status (pending → matched
  → locked → confirmed → completed)
- ChainStatus: enum for chain registry status (active, inactive, syncing, degraded)
- TradingConfig: trading client + bridge configuration
- InterChainTradeData: inter-chain trade payload dataclass
- ChainInfo: chain registry entry dataclass
- TradeMatchResult: matching result dataclass
- TradeHistoryEntry: trade history entry dataclass
- CreateTradeRequest: trade creation request dataclass
- RegisterChainRequest: chain registration request dataclass
- TradingClient: async HTTP client for the trading service REST API
- TradingBridgeClient: bridge client wrapper for inter-chain escrow operations
"""

from __future__ import annotations

from .bridge import TradingBridgeClient
from .client import TradingClient
from .types import (
    ChainInfo,
    ChainStatus,
    CreateTradeRequest,
    InterChainTradeData,
    InterChainTradeStatus,
    RegisterChainRequest,
    TradeHistoryEntry,
    TradeMatchResult,
    TradingConfig,
)

__all__ = [
    "ChainInfo",
    "ChainStatus",
    "CreateTradeRequest",
    "InterChainTradeData",
    "InterChainTradeStatus",
    "RegisterChainRequest",
    "TradeHistoryEntry",
    "TradeMatchResult",
    "TradingBridgeClient",
    "TradingClient",
    "TradingConfig",
]
