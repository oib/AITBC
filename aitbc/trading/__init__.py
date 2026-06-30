"""AITBC inter-chain trading shared SDK (v0.8.0 + v0.8.1 + v0.8.2).

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

v0.8.1 additions (offer sync):
- OfferSyncStatus: enum for offer sync cache status (fresh, stale, syncing, error)
- OfferSyncConfig: per-chain offer sync configuration
- SyncedOffer: cached offer with sync metadata
- OfferDiscoveryRequest: cross-chain offer discovery query
- OfferDiscoveryResult: ranked, deduplicated discovery result
- OfferSyncStatusEntry: per-chain sync status
- OfferSyncTrigger: request to trigger offer sync
- OfferSyncClient: async HTTP client for offer sync endpoints
- OfferCache: Redis-backed offer cache with staleness tracking

v0.8.2 additions (advanced offer sync):
- OfferEventType: enum for offer change events (created, updated, deleted)
- OfferEvent: offer change event for gossip/WebSocket transport
- OfferSubscription: saved-query filter set for offer streaming
- SubscriptionStatus: enum for WebSocket subscription lifecycle
- OfferNotification: debounced batch notification of offer changes
- OfferSubscriptionClient: WebSocket client for real-time offer streaming

v0.9.0 additions (atomic settlement):
- SettlementPhase: enum for settlement lifecycle (none → escrow_created →
  escrow_locked → lock_verified → trade_executed → settled/refunded)
- InterChainTradeData extended with escrow_id, settlement_phase,
  secret_hash, source_timelock, dest_timelock fields
"""

from __future__ import annotations

from .bridge import TradingBridgeClient
from .client import TradingClient
from .offer_cache import OfferCache
from .offer_client import OfferSyncClient
from .offer_types import (
    OfferDiscoveryRequest,
    OfferDiscoveryResult,
    OfferEventType,
    OfferSyncConfig,
    OfferSyncStatus,
    OfferSyncStatusEntry,
    OfferSyncTrigger,
    SyncedOffer,
)
from .subscription_client import OfferSubscriptionClient
from .subscription_types import (
    OfferEvent,
    OfferNotification,
    OfferSubscription,
    SubscriptionStatus,
)
from .types import (
    ChainInfo,
    ChainStatus,
    CreateTradeRequest,
    InterChainTradeData,
    InterChainTradeStatus,
    RegisterChainRequest,
    SettlementPhase,
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
    "OfferCache",
    "OfferDiscoveryRequest",
    "OfferDiscoveryResult",
    "OfferEvent",
    "OfferEventType",
    "OfferNotification",
    "OfferSubscription",
    "OfferSubscriptionClient",
    "OfferSyncClient",
    "OfferSyncConfig",
    "OfferSyncStatus",
    "OfferSyncStatusEntry",
    "OfferSyncTrigger",
    "RegisterChainRequest",
    "SettlementPhase",
    "SubscriptionStatus",
    "SyncedOffer",
    "TradeHistoryEntry",
    "TradeMatchResult",
    "TradingBridgeClient",
    "TradingClient",
    "TradingConfig",
]
