"""Offer cache with staleness tracking (v0.8.1 §A3).

Wraps ``RedisCache`` from ``aitbc.caching`` to provide offer-specific
caching with per-chain staleness detection. Falls back to in-memory
dict when Redis is unavailable (matching RedisCache's behavior).

The cache stores offers keyed by ``offer_id`` and maintains a per-chain
index for efficient chain-scoped queries. Sync metadata (last_sync,
offer_count, stale_count) is tracked per chain.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from typing import Any

from aitbc.caching.redis_cache import RedisCache

from .offer_types import OfferSyncConfig, SyncedOffer

logger = logging.getLogger(__name__)


class OfferCache:
    """Cache for cross-chain offers with staleness tracking.

    Wraps ``RedisCache`` for offer-specific caching. Each offer is
    stored as JSON keyed by ``offer:{offer_id}``. A per-chain index
    is maintained at ``chain:{chain_id}:offers`` (a set of offer IDs).
    Sync metadata is stored at ``chain:{chain_id}:sync_meta``.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        config: OfferSyncConfig | None = None,
        default_ttl: int = 300,
    ) -> None:
        self._config = config or OfferSyncConfig()
        self._cache = RedisCache(redis_url=redis_url, default_ttl=default_ttl or self._config.cache_ttl_seconds)

    def _offer_key(self, offer_id: str) -> str:
        return f"offer:{offer_id}"

    def _chain_index_key(self, chain_id: str) -> str:
        return f"chain:{chain_id}:offers"

    def _chain_meta_key(self, chain_id: str) -> str:
        return f"chain:{chain_id}:sync_meta"

    def get_offer(self, offer_id: str) -> SyncedOffer | None:
        """Get a single offer from the cache."""
        raw = self._cache.get(self._offer_key(offer_id))
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str | bytes) else raw
            return SyncedOffer.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning("Failed to deserialize offer %s: %s", offer_id, e)
            return None

    def set_offer(self, offer: SyncedOffer, ttl: int | None = None) -> None:
        """Store an offer in the cache and update the chain index."""
        key = self._offer_key(offer.offer_id)
        self._cache.set(key, json.dumps(offer.to_dict()), ttl or self._config.cache_ttl_seconds)
        # Update chain index (store as JSON list since RedisCache doesn't expose sets)
        index_key = self._chain_index_key(offer.chain_id)
        existing = self._get_chain_index(offer.chain_id)
        if offer.offer_id not in existing:
            existing.append(offer.offer_id)
            self._cache.set(index_key, json.dumps(existing), ttl or self._config.cache_ttl_seconds)

    def delete_offer(self, offer_id: str, chain_id: str | None = None) -> None:
        """Delete an offer from the cache and chain index."""
        offer = self.get_offer(offer_id)
        if chain_id is None and offer:
            chain_id = offer.chain_id
        self._cache.delete(self._offer_key(offer_id))
        if chain_id:
            self._remove_from_chain_index(chain_id, offer_id)

    def list_offers_by_chain(self, chain_id: str) -> list[SyncedOffer]:
        """List all cached offers for a specific chain."""
        offer_ids = self._get_chain_index(chain_id)
        offers: list[SyncedOffer] = []
        for oid in offer_ids:
            offer = self.get_offer(oid)
            if offer and offer.chain_id == chain_id:
                offers.append(offer)
        return offers

    def list_offers_by_type(self, service_type: str) -> list[SyncedOffer]:
        """List all cached offers for a specific service type.

        Scans all offers in the cache. For large caches, prefer
        ``list_offers_by_chain`` with a known chain_id.
        """
        # We don't have a global index, so we scan chain indices.
        # This is acceptable for v0.8.1 (polling-based, limited chains).
        all_offers: list[SyncedOffer] = []
        seen: set[str] = set()
        for chain_id in self._get_known_chains():
            for offer in self.list_offers_by_chain(chain_id):
                if offer.offer_id not in seen and offer.service_type == service_type:
                    all_offers.append(offer)
                    seen.add(offer.offer_id)
        return all_offers

    def is_stale(self, offer_id: str) -> bool:
        """Check if an offer is stale based on its last_synced timestamp."""
        offer = self.get_offer(offer_id)
        if not offer or not offer.last_synced:
            return True
        try:
            last = datetime.fromisoformat(offer.last_synced)
        except ValueError:
            return True
        threshold = self._config.get_staleness_for_chain(offer.chain_id)
        elapsed = (datetime.now(UTC) - last).total_seconds()
        return elapsed > threshold

    def get_stale_offers(self, chain_id: str | None = None) -> list[str]:
        """Get IDs of stale offers, optionally filtered by chain."""
        if chain_id:
            offers = self.list_offers_by_chain(chain_id)
        else:
            offers = []
            for cid in self._get_known_chains():
                offers.extend(self.list_offers_by_chain(cid))
        return [o.offer_id for o in offers if self.is_stale(o.offer_id)]

    def get_sync_metadata(self, chain_id: str) -> dict[str, Any]:
        """Get sync metadata for a chain (last_sync, offer_count, stale_count)."""
        raw = self._cache.get(self._chain_meta_key(chain_id))
        if raw is None:
            return {
                "chain_id": chain_id,
                "last_sync": "",
                "offer_count": 0,
                "stale_count": 0,
                "is_syncing": False,
            }
        try:
            parsed: Any = json.loads(raw) if isinstance(raw, str | bytes) else raw
            data: dict[str, Any] = parsed if isinstance(parsed, dict) else {}
            data.setdefault("chain_id", chain_id)
            return data
        except (json.JSONDecodeError, TypeError):
            return {
                "chain_id": chain_id,
                "last_sync": "",
                "offer_count": 0,
                "stale_count": 0,
                "is_syncing": False,
            }

    def set_sync_metadata(self, chain_id: str, metadata: dict[str, Any]) -> None:
        """Update sync metadata for a chain."""
        metadata.setdefault("chain_id", chain_id)
        offers = self.list_offers_by_chain(chain_id)
        metadata["offer_count"] = len(offers)
        metadata["stale_count"] = sum(1 for o in offers if self.is_stale(o.offer_id))
        self._cache.set(
            self._chain_meta_key(chain_id),
            json.dumps(metadata),
            self._config.cache_ttl_seconds * 2,
        )

    def mark_syncing(self, chain_id: str, is_syncing: bool) -> None:
        """Mark a chain as currently syncing or not."""
        meta = self.get_sync_metadata(chain_id)
        meta["is_syncing"] = is_syncing
        self.set_sync_metadata(chain_id, meta)

    def clear_chain(self, chain_id: str) -> int:
        """Clear all offers for a chain. Returns the number of offers removed."""
        offer_ids = self._get_chain_index(chain_id)
        for oid in offer_ids:
            self._cache.delete(self._offer_key(oid))
        self._cache.delete(self._chain_index_key(chain_id))
        self._cache.delete(self._chain_meta_key(chain_id))
        return len(offer_ids)

    def is_available(self) -> bool:
        """Check if Redis backend is available (vs in-memory fallback)."""
        return self._cache.is_available()

    def _get_chain_index(self, chain_id: str) -> list[str]:
        raw = self._cache.get(self._chain_index_key(chain_id))
        if raw is None:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str | bytes) else raw
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _remove_from_chain_index(self, chain_id: str, offer_id: str) -> None:
        existing = self._get_chain_index(chain_id)
        if offer_id in existing:
            existing.remove(offer_id)
            self._cache.set(
                self._chain_index_key(chain_id),
                json.dumps(existing),
                self._config.cache_ttl_seconds,
            )

    def _get_known_chains(self) -> list[str]:
        """Get all chain IDs that have sync metadata or offers.

        Since RedisCache doesn't expose key scanning, we rely on the
        sync metadata keys. Chains without metadata won't be returned.
        """
        # RedisCache doesn't expose SCAN, so we can't enumerate chains.
        # In practice, the OfferSyncService maintains a list of known
        # chains via the IslandRegistry. This method is a best-effort
        # fallback for standalone cache usage.
        return []
