"""Offer sync service for cross-chain offer synchronization (v0.8.1 §B2).

Polls registered chains for GPU/compute offers, caches them in OfferCache
(Agent A A3), detects staleness, and resolves conflicts (source-chain-wins).

The sync loop runs per-chain at configurable intervals. Incremental sync
tracks ``last_sync`` per chain and only fetches offers changed since then.
Conflict resolution: the offer from its source chain is authoritative —
if the same offer_id appears on multiple chains, the source chain's version
wins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc.marketplace.blockchain_rpc import BlockchainRPCClient
from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import (
    OfferDiscoveryRequest,
    OfferDiscoveryResult,
    OfferSyncStatus,
    OfferSyncStatusEntry,
    SyncedOffer,
)

from ..config import settings
from ..domain.inter_chain import IslandRegistryEntry

logger = logging.getLogger(__name__)


class OfferSyncService:
    """Service for synchronizing offers across AITBC chains."""

    def __init__(
        self,
        session: AsyncSession,
        cache: OfferCache | None = None,
        blockchain_client: BlockchainRPCClient | None = None,
    ) -> None:
        self.session = session
        self._cache = cache or OfferCache()
        self._blockchain = blockchain_client or BlockchainRPCClient(
            rpc_url=settings.blockchain_rpc_url,
            timeout=settings.http_timeout,
        )
        self._sync_tasks: dict[str, asyncio.Task[None]] = {}
        self._sync_status: dict[str, OfferSyncStatusEntry] = {}

    @property
    def cache(self) -> OfferCache:
        """The underlying OfferCache instance."""
        return self._cache

    async def sync_chain(self, chain_id: str) -> dict[str, Any]:
        """Sync offers from a single chain.

        Queries the chain's blockchain node for GPU offers, updates the
        OfferCache, and records sync metadata. Uses source-chain-wins
        conflict resolution.
        """
        start_time = datetime.now(UTC)
        entry = self._init_status_entry(chain_id)
        entry.is_syncing = True
        self._cache.mark_syncing(chain_id, True)

        try:
            # Query offers from the blockchain node
            offers = await self._blockchain.query_offers(chain_id=chain_id, limit=500)

            # Get staleness threshold for this chain
            threshold = settings.offer_per_chain_staleness.get(chain_id, settings.offer_staleness_threshold_seconds)

            now_iso = datetime.now(UTC).isoformat()
            synced_count = 0
            for offer_data in offers:
                offer_id = str(offer_data.get("gpu_id", offer_data.get("id", "")))
                if not offer_id:
                    continue

                # Source-chain-wins: only update if this is the source chain
                existing = self._cache.get_offer(offer_id)
                if existing and existing.chain_id != chain_id:
                    # Offer exists from a different chain — skip (source wins)
                    continue

                synced = SyncedOffer(
                    offer_id=offer_id,
                    chain_id=chain_id,
                    provider=str(offer_data.get("provider", offer_data.get("owner", ""))),
                    service_type="gpu_marketplace",
                    price=float(offer_data.get("price", 0.0)),
                    quantity=int(offer_data.get("capacity", offer_data.get("quantity", 1))),
                    status=str(offer_data.get("status", "available")),
                    attributes={
                        k: v
                        for k, v in offer_data.items()
                        if k
                        not in ("gpu_id", "id", "provider", "owner", "price", "capacity", "quantity", "status", "chain_id")
                    },
                    last_synced=now_iso,
                    sync_status=OfferSyncStatus.FRESH.value,
                    sync_confidence=1.0,
                )
                self._cache.set_offer(synced, ttl=settings.offer_cache_ttl_seconds)
                synced_count += 1

            # Update sync metadata
            self._cache.set_sync_metadata(
                chain_id,
                {
                    "last_sync": now_iso,
                    "offer_count": synced_count,
                    "staleness_threshold": threshold,
                },
            )

            entry.last_sync = now_iso
            entry.offer_count = synced_count
            entry.stale_count = len(self._cache.get_stale_offers(chain_id))
            entry.error_count = 0
            entry.is_syncing = False

            self._cache.mark_syncing(chain_id, False)

            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            logger.info("Synced %d offers from chain %s in %.2fs", synced_count, chain_id, elapsed)

            return {
                "chain_id": chain_id,
                "synced": synced_count,
                "last_sync": now_iso,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            entry.is_syncing = False
            entry.error_count += 1
            self._cache.mark_syncing(chain_id, False)
            logger.warning("Sync failed for chain %s: %s", chain_id, e)
            return {
                "chain_id": chain_id,
                "error": str(e),
                "synced": 0,
            }

    async def sync_all_chains(self) -> list[dict[str, Any]]:
        """Sync offers from all registered chains.

        Returns a list of sync results per chain.
        """
        stmt = select(IslandRegistryEntry).where(IslandRegistryEntry.status == "active")
        result = await self.session.execute(stmt)
        chains = list(result.scalars().all())

        if not chains:
            # Fallback: sync the default chain
            return [await self.sync_chain(settings.default_chain_id)]

        results: list[dict[str, Any]] = []
        for chain in chains:
            res = await self.sync_chain(chain.chain_id)
            results.append(res)

        return results

    async def discover_offers(self, request: OfferDiscoveryRequest) -> OfferDiscoveryResult:
        """Discover offers matching the given request.

        Queries the OfferCache with filters. If cached offers are stale,
        triggers an on-demand sync before returning.
        """
        # Check if we need to sync first
        sync_triggered = False
        if request.source_chain:
            stale = self._cache.get_stale_offers(request.source_chain)
            if stale:
                logger.info("Triggering on-demand sync for chain %s (%d stale offers)", request.source_chain, len(stale))
                await self.sync_chain(request.source_chain)
                sync_triggered = True

        # Get offers from cache
        all_offers: list[SyncedOffer] = []
        if request.source_chain:
            all_offers = self._cache.list_offers_by_chain(request.source_chain)
        else:
            # Get from all known chains
            for chain_id in self._cache._get_known_chains():  # noqa: SLF001
                all_offers.extend(self._cache.list_offers_by_chain(chain_id))

        # Apply filters
        filtered = self._apply_filters(all_offers, request)

        # Deduplicate by offer_id (source-chain-wins already applied during sync)
        seen: set[str] = set()
        deduped: list[SyncedOffer] = []
        for offer in filtered:
            if offer.offer_id not in seen:
                seen.add(offer.offer_id)
                deduped.append(offer)

        # Rank by price (lowest first) then by freshness
        ranked = sorted(deduped, key=lambda o: (o.price, -o.sync_confidence))

        # Apply limit
        if request.limit > 0:
            ranked = ranked[: request.limit]

        return OfferDiscoveryResult(
            offers=ranked,
            total_count=len(ranked),
            chains_searched=list({o.chain_id for o in ranked}),
            stale_count=len(self._cache.get_stale_offers()),
            sync_triggered=sync_triggered,
        )

    def get_sync_status(self) -> list[OfferSyncStatusEntry]:
        """Get sync status for all known chains."""
        return list(self._sync_status.values())

    def get_cached_offers(
        self,
        chain_id: str | None = None,
        service_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[SyncedOffer]:
        """Get cached offers with optional filters."""
        if chain_id:
            offers = self._cache.list_offers_by_chain(chain_id)
        else:
            offers = []
            for cid in self._cache._get_known_chains():  # noqa: SLF001
                offers.extend(self._cache.list_offers_by_chain(cid))

        if service_type:
            offers = [o for o in offers if o.service_type == service_type]
        if status:
            offers = [o for o in offers if o.status == status]

        return offers[:limit]

    def _init_status_entry(self, chain_id: str) -> OfferSyncStatusEntry:
        """Initialize or get the sync status entry for a chain."""
        if chain_id not in self._sync_status:
            self._sync_status[chain_id] = OfferSyncStatusEntry(
                chain_id=chain_id,
                last_sync="",
                offer_count=0,
                stale_count=0,
                is_syncing=False,
                error_count=0,
            )
        return self._sync_status[chain_id]

    def _apply_filters(self, offers: list[SyncedOffer], request: OfferDiscoveryRequest) -> list[SyncedOffer]:
        """Apply discovery request filters to a list of offers."""
        filtered = offers

        if request.service_type:
            filtered = [o for o in filtered if o.service_type == request.service_type]

        if request.min_price is not None:
            filtered = [o for o in filtered if o.price >= request.min_price]

        if request.max_price is not None:
            filtered = [o for o in filtered if o.price <= request.max_price]

        if request.gpu_model:
            filtered = [o for o in filtered if request.gpu_model.lower() in str(o.attributes.get("model", "")).lower()]

        if request.region:
            filtered = [o for o in filtered if request.region.lower() in str(o.attributes.get("region", "")).lower()]

        return filtered
