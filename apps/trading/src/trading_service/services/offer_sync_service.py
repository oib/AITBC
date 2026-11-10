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
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc.market.blockchain_rpc import BlockchainRPCClient
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

# Offer statuses that must never be served to clients (#1567): the chain
# keeps deactivated/withdrawn registrations visible via /rpc/gpus, and the
# cache stores them verbatim — but discovery and the cache listing filter
# them out unless the caller asks for that status explicitly.
_NON_DISCOVERABLE_OFFER_STATUSES = frozenset({"deactivated", "inactive", "delisted", "expired", "cancelled"})

# Page size passed to ``BlockchainRPCClient.query_offers`` — a response this
# large may be truncated, so deletion reconciliation must not run on it
# (#1567): offers past the cut would look "absent" and be wrongly deleted.
_SYNC_PAGE_LIMIT = 500


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
            api_key=settings.blockchain_rpc_api_key,
        )
        self._sync_tasks: dict[str, asyncio.Task[None]] = {}
        self._sync_status: dict[str, OfferSyncStatusEntry] = {}
        # Single-flight locks, one per chain (#1567): ``is_syncing`` flags
        # were written but never read as a guard, so N concurrent discovers
        # each ran a full sync. ``lock.locked()`` + ``async with`` is atomic
        # in asyncio — no await between check and acquire.
        self._sync_locks: dict[str, asyncio.Lock] = {}

    @property
    def cache(self) -> OfferCache:
        """The underlying OfferCache instance."""
        return self._cache

    async def sync_chain(self, chain_id: str) -> dict[str, Any]:
        """Sync offers from a single chain — single-flight per chain (#1567).

        A caller arriving while a sync for the same chain is running gets
        ``skipped: sync_in_progress`` instead of queueing a duplicate
        500-offer sync behind the lock.
        """
        lock = self._sync_locks.setdefault(chain_id, asyncio.Lock())
        if lock.locked():
            logger.info("Offer sync for chain %s already in progress — skipping", chain_id)
            return {"chain_id": chain_id, "skipped": "sync_in_progress", "synced": 0}
        async with lock:
            return await self._sync_chain_once(chain_id)

    async def _sync_chain_once(self, chain_id: str) -> dict[str, Any]:
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

                # #1567: keys are chain-namespaced — this chain's entry can
                # never collide with another chain's, so the old chainless
                # "source-chain-wins" skip is gone (it would have let chain
                # A's entry suppress chain B's legit offer_id forever).

                synced = SyncedOffer(  # not-money: ratio, threshold or configuration default — not an amount of money
                    offer_id=offer_id,
                    chain_id=chain_id,
                    provider=str(offer_data.get("provider", offer_data.get("owner", ""))),
                    service_type="gpu_market",
                    price=Decimal(str(offer_data.get("price", 0.0))),
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

            # Deletion reconciliation (#1567): an offer the chain no longer
            # reports is gone — drop it instead of letting it linger until
            # TTL. Only safe when the response is known complete: at the page
            # limit the tail may be unseen, so skip reconciliation entirely.
            deleted_count = 0
            if len(offers) < _SYNC_PAGE_LIMIT:
                # Same id extraction as the upsert loop above — an offer the
                # chain still reports must never look absent.
                seen_ids = {str(o.get("gpu_id", o.get("id", ""))) for o in offers}
                seen_ids.discard("")
                for cached in self._cache.list_offers_by_chain(chain_id):
                    if cached.offer_id not in seen_ids:
                        self._cache.delete_offer(cached.offer_id, chain_id)
                        deleted_count += 1

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
                "deleted": deleted_count,
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

        # Deduplicate by (chain_id, offer_id) — post-#1567 two chains can
        # legitimately carry the same offer_id (cache keys are
        # ``offer:{chain_id}:{offer_id}``), so a bare offer_id dedup silently
        # dropped every chain but the first (#1677).
        seen: set[tuple[str, str]] = set()
        deduped: list[SyncedOffer] = []
        for offer in filtered:
            key = (offer.chain_id, offer.offer_id)
            if key not in seen:
                seen.add(key)
                deduped.append(offer)

        # Rank by price (lowest first) then by freshness
        ranked = sorted(deduped, key=lambda o: (o.price, -o.sync_confidence))

        # total_count is the pre-pagination match count (#1419) — reporting
        # the post-limit length tells clients "2 matches" when 50 exist.
        total_count = len(ranked)
        offset = max(0, request.offset)
        if request.limit > 0:
            ranked = ranked[offset : offset + request.limit]
        elif offset:
            ranked = ranked[offset:]

        return OfferDiscoveryResult(
            offers=ranked,
            total_count=total_count,
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
        # Clamp like the router does — a negative limit would slice from the
        # end instead of bounding the read (#1543).
        limit = min(max(int(limit), 1), 500)
        if chain_id:
            offers = self._cache.list_offers_by_chain(chain_id)
        else:
            offers = []
            for cid in self._cache._get_known_chains():  # noqa: SLF001
                offers.extend(self._cache.list_offers_by_chain(cid))

        # Dead offers are hidden unless the caller filters for them
        # explicitly (#1567) — the cache stores whatever the chain reports.
        if not status:
            offers = [o for o in offers if o.status.lower() not in _NON_DISCOVERABLE_OFFER_STATUSES]
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
        # Deactivated/withdrawn offers are cached verbatim from the chain but
        # are never discoverable (#1567).
        filtered = [o for o in offers if o.status.lower() not in _NON_DISCOVERABLE_OFFER_STATUSES]

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
