"""Offer cache with staleness tracking (v0.8.1 §A3).

Wraps ``RedisCache`` from ``aitbc.caching`` to provide offer-specific
caching with per-chain staleness detection. Falls back to in-memory
dict when Redis is unavailable (matching RedisCache's behavior).

The cache stores offers keyed by ``offer:{chain_id}:{offer_id}`` — the chain
namespace matters: two chains can legitimately carry the same offer_id, and a
bare ``offer:{offer_id}`` key let one chain's sync overwrite the other's entry
(#1567). A per-chain index is maintained for efficient chain-scoped queries.
Sync metadata (last_sync, offer_count, stale_count) is tracked per chain.
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
    stored as JSON keyed by ``offer:{chain_id}:{offer_id}``. A per-chain index
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

    @staticmethod
    def _offer_key(chain_id: str, offer_id: str) -> str:
        """Namespaced offer key — ``offer:{chain_id}:{offer_id}`` (#1567).

        The chain id is part of the key so a sync on chain B can never
        overwrite chain A's entry for the same offer_id. Entries written
        before namespacing lived at ``offer:{offer_id}``; they age out via
        TTL and are also removed by :meth:`delete_offer`.
        """
        return f"offer:{chain_id}:{offer_id}"

    @staticmethod
    def _legacy_offer_key(offer_id: str) -> str:
        """Pre-#1567 unnamespaced key, kept only for delete hygiene."""
        return f"offer:{offer_id}"

    def _chain_index_key(self, chain_id: str) -> str:
        return f"chain:{chain_id}:offers"

    def _chain_meta_key(self, chain_id: str) -> str:
        return f"chain:{chain_id}:sync_meta"

    _CHAINS_INDEX_KEY = "trading:offer_chains"

    def _get_chain_registry(self) -> list[str]:
        raw = self._cache.get(self._CHAINS_INDEX_KEY)
        if isinstance(raw, list):
            return [str(c) for c in raw]
        return []

    def _register_chain(self, chain_id: str) -> None:
        chains = self._get_chain_registry()
        if chain_id not in chains:
            chains.append(chain_id)
            self._cache.set(self._CHAINS_INDEX_KEY, chains)

    def _unregister_chain(self, chain_id: str) -> None:
        chains = [c for c in self._get_chain_registry() if c != chain_id]
        self._cache.set(self._CHAINS_INDEX_KEY, chains)

    def _read_offer_key(self, key: str) -> SyncedOffer | None:
        raw = self._cache.get(key)
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str | bytes) else raw
            if not isinstance(data, dict):
                return None
            return SyncedOffer.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("Failed to deserialize offer at %s: %s", key, e)
            return None

    def get_offer(self, offer_id: str, chain_id: str | None = None) -> SyncedOffer | None:
        """Get a single offer from the cache.

        With ``chain_id`` this is a direct namespaced lookup. Without it the
        known chain registry is scanned for the offer_id — callers that know
        the chain should pass it (O(1) vs O(chains)).
        """
        if chain_id is not None:
            return self._read_offer_key(self._offer_key(chain_id, offer_id))
        for cid in self._get_known_chains():
            offer = self._read_offer_key(self._offer_key(cid, offer_id))
            if offer is not None:
                return offer
        # Pre-#1567 entries live at the unnamespaced key until TTL — keep them
        # readable so a rolling deploy does not blank the cache.
        return self._read_offer_key(self._legacy_offer_key(offer_id))

    def set_offer(self, offer: SyncedOffer, ttl: int | None = None) -> None:
        """Store an offer in the cache and update the chain index."""
        key = self._offer_key(offer.chain_id, offer.offer_id)
        self._cache.set(key, json.dumps(offer.to_dict()), ttl or self._config.cache_ttl_seconds)
        # Update chain index (store as JSON list since RedisCache doesn't expose sets)
        self._register_chain(offer.chain_id)
        index_key = self._chain_index_key(offer.chain_id)
        existing = self._get_chain_index(offer.chain_id)
        if offer.offer_id not in existing:
            existing.append(offer.offer_id)
            self._cache.set(index_key, json.dumps(existing), ttl or self._config.cache_ttl_seconds)

    def delete_offer(self, offer_id: str, chain_id: str | None = None) -> None:
        """Delete an offer from the cache and chain index."""
        offer = self.get_offer(offer_id, chain_id)
        if chain_id is None and offer:
            chain_id = offer.chain_id
        if chain_id:
            self._cache.delete(self._offer_key(chain_id, offer_id))
            self._remove_from_chain_index(chain_id, offer_id)
            # Pre-#1567 entries live at the unnamespaced key; drop it only
            # when it provably belongs to this chain.
            legacy = self._read_offer_key(self._legacy_offer_key(offer_id))
            if legacy is not None and legacy.chain_id == chain_id:
                self._cache.delete(self._legacy_offer_key(offer_id))

    def list_offers_by_chain(self, chain_id: str) -> list[SyncedOffer]:
        """List all cached offers for a specific chain."""
        offer_ids = self._get_chain_index(chain_id)
        offers: list[SyncedOffer] = []
        for oid in offer_ids:
            offer = self.get_offer(oid, chain_id)
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
        # #1677: dedup on (chain_id, offer_id) — post-#1567 the same offer_id
        # on two chains is two distinct offers, not a duplicate.
        seen: set[tuple[str, str]] = set()
        for chain_id in self._get_known_chains():
            for offer in self.list_offers_by_chain(chain_id):
                key = (offer.chain_id, offer.offer_id)
                if key not in seen and offer.service_type == service_type:
                    all_offers.append(offer)
                    seen.add(key)
        return all_offers

    def is_stale(self, offer_id: str, chain_id: str | None = None) -> bool:
        """Check if an offer is stale based on its last_synced timestamp."""
        offer = self.get_offer(offer_id, chain_id)
        if not offer or not offer.last_synced:
            return True
        try:
            last = datetime.fromisoformat(offer.last_synced)
        except (ValueError, TypeError):
            return True
        if last.tzinfo is None:
            # Naive timestamps are UTC by convention here — an offset-aware
            # now() minus a naive datetime raises TypeError (#1420).
            last = last.replace(tzinfo=UTC)
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
        return [o.offer_id for o in offers if self.is_stale(o.offer_id, o.chain_id)]

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
        self._register_chain(chain_id)
        offers = self.list_offers_by_chain(chain_id)
        metadata["offer_count"] = len(offers)
        metadata["stale_count"] = sum(1 for o in offers if self.is_stale(o.offer_id, o.chain_id))
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
            self._cache.delete(self._offer_key(chain_id, oid))
            # Legacy unnamespaced keys can't be attributed to a chain without
            # reading them — drop only this chain's.
            legacy = self._read_offer_key(self._legacy_offer_key(oid))
            if legacy is not None and legacy.chain_id == chain_id:
                self._cache.delete(self._legacy_offer_key(oid))
        self._cache.delete(self._chain_index_key(chain_id))
        self._cache.delete(self._chain_meta_key(chain_id))
        self._unregister_chain(chain_id)
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
        """Get all chain IDs with cached offers or sync metadata.

        Maintained as a JSON-list registry key (``trading:offer_chains``)
        updated by ``set_offer``/``set_sync_metadata``/``clear_chain`` —
        RedisCache exposes no SCAN (#1418). Chains cached before this
        index existed re-register on their next write or sync."""
        return self._get_chain_registry()
