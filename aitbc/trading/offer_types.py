"""Cross-chain offer synchronization types (v0.8.1 §A1).

Defines the canonical types for offer synchronization across AITBC
chains (islands). These types are used by the offer sync service
(``apps/trading/``), the OfferSyncClient, and the OfferCache to
discover, cache, and track the freshness of offers from multiple chains.

The offer schema mirrors the existing ``MarketplaceOffer`` model
(``packages/aitbc-shared/aitbc_shared/models/marketplace.py``) which is
already chain-aware (has ``chain_id`` field from v0.6.6). The
``OfferFSM`` (``aitbc/marketplace/offer_fsm.py``) defines the offer
lifecycle states (AVAILABLE, RESERVED, IN_USE, DELISTED, EXPIRED).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OfferSyncStatus(StrEnum):
    """Status of an offer in the sync cache.

    - ``fresh``: recently synced, within staleness threshold
    - ``stale``: exceeded staleness threshold, needs refresh
    - ``syncing``: currently being synced from source chain
    - ``error``: sync failed (source chain unreachable or returned error)
    """

    FRESH = "fresh"
    STALE = "stale"
    SYNCING = "syncing"
    ERROR = "error"


class OfferEventType(StrEnum):
    """Type of offer change event (v0.8.2).

    Published to the ``offers.{chain_id}`` gossip topic and streamed to
    WebSocket subscribers. ``offer`` field semantics:

    - ``CREATED``: full ``SyncedOffer`` (new listing confirmed on-chain)
    - ``UPDATED``: full ``SyncedOffer`` with new status/price
    - ``DELETED``: ``None`` (only ``offer_id`` + ``chain_id`` needed)

    Defined here (in ``offer_types``) rather than ``subscription_types``
    so that ``subscription_types`` can import it without a circular
    dependency, and so callers importing from ``offer_types`` get the
    full offer type surface in one place.
    """

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class OfferSyncConfig:
    """Configuration for offer synchronization.

    Controls the polling-based sync loop that runs in the trading service.
    Per-chain staleness overrides allow slower chains to have longer
    freshness windows.
    """

    sync_enabled: bool = True
    sync_interval_seconds: int = 60
    staleness_threshold_seconds: int = 300  # 5 min default for fast chains
    max_bandwidth_kbps: int = 100
    cache_ttl_seconds: int = 300
    # Per-chain staleness overrides: {chain_id: threshold_seconds}
    # Example: {"ait-hub": 300, "ait-island1": 1800}
    per_chain_staleness: dict[str, int] = field(default_factory=dict)

    def get_staleness_for_chain(self, chain_id: str) -> int:
        """Get the staleness threshold for a specific chain.

        Falls back to the default if no per-chain override is set.
        """
        return self.per_chain_staleness.get(chain_id, self.staleness_threshold_seconds)


@dataclass
class SyncedOffer:
    """A cached offer with sync metadata.

    Mirrors the ``MarketplaceOffer`` model fields plus sync metadata
    (last_synced, sync_status, sync_confidence) used for staleness
    tracking and discovery ranking.
    """

    offer_id: str
    chain_id: str
    provider: str
    service_type: str  # "gpu_marketplace", "compute", etc.
    price: float
    quantity: int
    status: str  # OfferFSM status: available, reserved, in_use, delisted, expired
    attributes: dict[str, Any] = field(default_factory=dict)
    last_synced: str = ""  # ISO timestamp
    sync_status: str = "fresh"  # OfferSyncStatus value
    sync_confidence: float = 1.0  # 1.0 = fresh, 0.5 = stale, 0.0 = error

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON transport or cache storage."""
        return {
            "offer_id": self.offer_id,
            "chain_id": self.chain_id,
            "provider": self.provider,
            "service_type": self.service_type,
            "price": self.price,
            "quantity": self.quantity,
            "status": self.status,
            "attributes": self.attributes,
            "last_synced": self.last_synced,
            "sync_status": self.sync_status,
            "sync_confidence": self.sync_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncedOffer:
        """Deserialize from a dict (cache storage or RPC response)."""
        return cls(
            offer_id=data.get("offer_id", ""),
            chain_id=data.get("chain_id", ""),
            provider=data.get("provider", ""),
            service_type=data.get("service_type", ""),
            price=float(data.get("price", 0.0)),
            quantity=int(data.get("quantity", 0)),
            status=data.get("status", "available"),
            attributes=data.get("attributes", {}),
            last_synced=data.get("last_synced", ""),
            sync_status=data.get("sync_status", "fresh"),
            sync_confidence=float(data.get("sync_confidence", 1.0)),
        )


@dataclass
class OfferDiscoveryRequest:
    """Request to discover offers across chains.

    Used by the CLI and OfferSyncClient to query the offer cache with
    filters. If cached offers are stale, the trading service triggers
    an on-demand sync before returning results.
    """

    source_chain: str | None = None
    dest_chain: str | None = None
    service_type: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    region: str | None = None
    gpu_model: str | None = None
    limit: int = 100
    offset: int = 0

    def to_params(self) -> dict[str, Any]:
        """Serialize to query params for HTTP transport."""
        params: dict[str, Any] = {"limit": self.limit, "offset": self.offset}
        if self.source_chain:
            params["source_chain"] = self.source_chain
        if self.dest_chain:
            params["dest_chain"] = self.dest_chain
        if self.service_type:
            params["service_type"] = self.service_type
        if self.min_price is not None:
            params["min_price"] = self.min_price
        if self.max_price is not None:
            params["max_price"] = self.max_price
        if self.region:
            params["region"] = self.region
        if self.gpu_model:
            params["gpu_model"] = self.gpu_model
        return params


@dataclass
class OfferDiscoveryResult:
    """Result of offer discovery across chains.

    Returned by the trading service discovery endpoint after querying
    the OfferCache. Includes sync metadata so the caller knows whether
    a fresh sync was triggered and how many offers are stale.
    """

    offers: list[SyncedOffer] = field(default_factory=list)
    total_count: int = 0
    chains_searched: list[str] = field(default_factory=list)
    stale_count: int = 0
    sync_triggered: bool = False


@dataclass
class OfferSyncStatusEntry:
    """Sync status for a single chain.

    Part of the sync status response returned by
    ``GET /v1/trading/offers/sync-status``.
    """

    chain_id: str
    last_sync: str = ""  # ISO timestamp
    offer_count: int = 0
    stale_count: int = 0
    error_count: int = 0
    is_syncing: bool = False
    last_error: str = ""


@dataclass
class OfferSyncTrigger:
    """Request to trigger offer sync for specific chains.

    Used by the CLI ``aitbc trade sync`` command and the OfferSyncClient.
    """

    chain_id: str | None = None  # None = sync all chains
    service_type: str | None = None  # None = sync all service types
    force: bool = False  # Force sync even if offers are fresh

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON transport."""
        result: dict[str, Any] = {"force": self.force}
        if self.chain_id:
            result["chain_id"] = self.chain_id
        if self.service_type:
            result["service_type"] = self.service_type
        return result
