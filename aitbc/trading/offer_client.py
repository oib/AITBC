"""Offer sync HTTP client (v0.8.1 §A2).

Async HTTP client that wraps the trading service offer sync endpoints.
Used by the CLI and other services to discover offers across chains,
trigger sync cycles, and query sync status.

The client is async-first (``httpx.AsyncClient``) and follows the same
pattern as ``TradingClient`` (v0.8.0 §A2) and ``BridgeClient`` (v0.7.0).

Endpoint mapping (Agent B B3-B4 will add these to main.py):
- POST /v1/trading/offers/discover      -> discover_offers
- POST /v1/trading/offers/sync          -> sync_offers
- GET  /v1/trading/offers/sync-status   -> get_sync_status
- GET  /v1/trading/offers/cache         -> get_cached_offers
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from .offer_types import (
    OfferDiscoveryRequest,
    OfferDiscoveryResult,
    OfferSyncStatusEntry,
    OfferSyncTrigger,
    SyncedOffer,
)

logger = logging.getLogger(__name__)


class OfferSyncClient:
    """HTTP client for the trading service offer sync endpoints.

    Wraps the offer discovery, sync, and status endpoints on the
    trading service (port 8104 by default). Used by the CLI
    ``aitbc trade discover/sync/sync-status`` commands.
    """

    def __init__(self, rpc_url: str = "http://localhost:8104", timeout: int = 30) -> None:
        self._rpc_url = rpc_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def rpc_url(self) -> str:
        """The base RPC URL for the trading service."""
        return self._rpc_url

    async def __aenter__(self) -> OfferSyncClient:
        self._client = httpx.AsyncClient(base_url=self._rpc_url, timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._rpc_url, timeout=self._timeout)
        return self._client

    async def discover_offers(self, request: OfferDiscoveryRequest) -> OfferDiscoveryResult:
        """Discover offers across chains with filters.

        Queries the offer cache on the trading service. If cached offers
        are stale, the service triggers an on-demand sync before
        returning results.
        """
        resp = await self._ensure_client().post("/v1/trading/offers/discover", json=request.to_params())
        resp.raise_for_status()
        data = cast(dict[str, Any], resp.json())
        offers = [SyncedOffer.from_dict(o) for o in data.get("offers", [])]
        return OfferDiscoveryResult(
            offers=offers,
            total_count=int(data.get("total_count", len(offers))),
            chains_searched=data.get("chains_searched", []),
            stale_count=int(data.get("stale_count", 0)),
            sync_triggered=bool(data.get("sync_triggered", False)),
        )

    async def sync_offers(self, trigger: OfferSyncTrigger) -> dict[str, Any]:
        """Trigger offer sync for specific chain or all chains.

        Returns a sync result dict with per-chain sync counts and status.
        """
        resp = await self._ensure_client().post("/v1/trading/offers/sync", json=trigger.to_dict())
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_sync_status(self) -> list[OfferSyncStatusEntry]:
        """Get offer sync status for all registered chains.

        Returns per-chain sync metadata: last_sync, offer_count,
        stale_count, error_count, is_syncing.
        """
        resp = await self._ensure_client().get("/v1/trading/offers/sync-status")
        resp.raise_for_status()
        data = resp.json()
        entries: list[dict[str, Any]] = []
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict) and isinstance(data.get("chains"), list):
            entries = data["chains"]
        return [
            OfferSyncStatusEntry(
                chain_id=e.get("chain_id", ""),
                last_sync=e.get("last_sync", ""),
                offer_count=int(e.get("offer_count", 0)),
                stale_count=int(e.get("stale_count", 0)),
                error_count=int(e.get("error_count", 0)),
                is_syncing=bool(e.get("is_syncing", False)),
                last_error=e.get("last_error", ""),
            )
            for e in entries
        ]

    async def get_cached_offers(
        self,
        chain_id: str | None = None,
        service_type: str | None = None,
        limit: int = 100,
    ) -> list[SyncedOffer]:
        """Get cached offers with optional filters.

        Returns offers from the local cache without triggering a sync.
        Useful for quick lookups when freshness is not critical.
        """
        params: dict[str, Any] = {"limit": limit}
        if chain_id:
            params["chain_id"] = chain_id
        if service_type:
            params["service_type"] = service_type
        resp = await self._ensure_client().get("/v1/trading/offers/cache", params=params)
        resp.raise_for_status()
        data = resp.json()
        offers: list[dict[str, Any]] = []
        if isinstance(data, list):
            offers = data
        elif isinstance(data, dict) and isinstance(data.get("offers"), list):
            offers = data["offers"]
        return [SyncedOffer.from_dict(o) for o in offers]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
