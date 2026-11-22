"""Offer search index service (v0.8.2 §B7).

Optional integration with Meilisearch (preferred) or Elasticsearch for
advanced offer search. Falls back to in-memory search when the index
is unavailable or disabled.

The service indexes offers on sync/event and provides a query method
for advanced search with relevance ranking.
"""

from __future__ import annotations

from decimal import Decimal
import logging
import time
from typing import Any

import httpx

from aitbc.trading.offer_types import SyncedOffer

from ..config import settings

logger = logging.getLogger(__name__)

# meilisearch is an optional dependency (lazy-imported in _init_backend);
# fold its error base into the ops tuple only when importable. httpx covers
# the transport-level failures the client can leak.
try:
    from meilisearch.errors import MeilisearchError as _MeilisearchError

    _SEARCH_ERRORS: tuple[type[BaseException], ...] = (_MeilisearchError,)
except ImportError:
    _SEARCH_ERRORS = ()

# Expected failure surface for the search-backend fallbacks below: lazy
# backend import (ImportError), backend API/transport errors, response
# decode and data-shape errors. RuntimeError covers abort-style raises;
# genuine BaseExceptions still propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
    *_SEARCH_ERRORS,
)


class OfferSearchService:
    """Search index for offers with in-memory fallback.

    When ``offer_search_index_enabled`` is True and the external search
    backend (Meilisearch/Elasticsearch) is reachable, offers are indexed
    in the external system for advanced full-text search. Otherwise,
    a simple in-memory filter is used (matching v0.8.1 behavior).
    """

    def __init__(self, enabled: bool | None = None, backend_url: str | None = None) -> None:
        self._enabled = enabled if enabled is not None else settings.offer_search_index_enabled
        self._backend_url = backend_url or settings.offer_search_index_url
        self._backend = settings.offer_search_index_backend
        self._client: Any | None = None
        self._index_name = "offers"
        # Keyed ``{chain_id}:{offer_id}`` (#2470): the OfferCache namespaces
        # offers per chain, so two chains can legitimately carry the same
        # offer_id — a bare-offer_id dict silently kept only the last one.
        self._in_memory_offers: dict[str, SyncedOffer] = {}
        # #2481: monotonic index time per key. Entries self-expire at the
        # OfferCache TTL — a chain-deleted offer stops being refreshed in
        # the cache and must stop being searchable here too, instead of
        # living in this map forever.
        self._indexed_at: dict[str, float] = {}

        if self._enabled:
            self._init_backend()

    def _init_backend(self) -> None:
        """Initialize the external search backend client."""
        try:
            if self._backend == "meilisearch":
                try:
                    import meilisearch

                    self._client = meilisearch.Client(self._backend_url)
                    # Ensure index exists
                    try:
                        self._client.get_index(self._index_name)
                    except _OPS_ERRORS:
                        self._client.create_index(self._index_name)
                    logger.info("Meilisearch connected at %s", self._backend_url)
                except ImportError:
                    logger.warning("meilisearch package not installed, falling back to in-memory search")
                    self._enabled = False
            else:
                logger.warning("Unknown search backend %s, falling back to in-memory", self._backend)
                self._enabled = False
        except _OPS_ERRORS as e:
            logger.warning("Search backend init failed: %s, falling back to in-memory", e)
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _memory_key(offer: SyncedOffer) -> str:
        return f"{offer.chain_id}:{offer.offer_id}"

    @staticmethod
    def _index_ttl_seconds() -> float:
        return max(float(getattr(settings, "offer_cache_ttl_seconds", 300)), 1.0)

    @staticmethod
    def _index_cap() -> int:
        return max(int(getattr(settings, "offer_search_index_max_entries", 10000)), 1)

    def _expire_stale(self) -> None:
        """Drop memory entries older than the OfferCache TTL (#2481)."""
        cutoff = time.monotonic() - self._index_ttl_seconds()
        stale = [k for k, ts in self._indexed_at.items() if ts < cutoff]
        for key in stale:
            self._in_memory_offers.pop(key, None)
            self._indexed_at.pop(key, None)

    def _enforce_cap(self) -> None:
        """Bound the map: evict the oldest-indexed entries past the cap."""
        cap = self._index_cap()
        while len(self._in_memory_offers) > cap:
            oldest = min(self._indexed_at, key=self._indexed_at.get)  # type: ignore[arg-type]
            self._in_memory_offers.pop(oldest, None)
            self._indexed_at.pop(oldest, None)

    def index_offer(self, offer: SyncedOffer) -> None:
        """Add or update an offer in the search index."""
        if self._enabled and self._client is not None:
            try:
                self._client.index(self._index_name).add_documents([offer.to_dict()], "offer_id")
            except _OPS_ERRORS as e:
                logger.warning("Search index error for offer %s: %s", offer.offer_id, e)
                self._in_memory_offers[self._memory_key(offer)] = offer
                self._indexed_at[self._memory_key(offer)] = time.monotonic()
                self._enforce_cap()
        else:
            self._in_memory_offers[self._memory_key(offer)] = offer
            self._indexed_at[self._memory_key(offer)] = time.monotonic()
            self._enforce_cap()

    def delete_offer(self, offer_id: str, chain_id: str | None = None) -> None:
        """Remove an offer from the search index.

        ``chain_id`` disambiguates the namespaced memory key; without it
        every chain's entry for the id is dropped (the external backend
        keys documents by bare offer_id, so it can only ever hold one).
        """
        if self._enabled and self._client is not None:
            try:
                self._client.index(self._index_name).delete_document(offer_id)
            except _OPS_ERRORS as e:
                logger.warning("Search delete error for offer %s: %s", offer_id, e)
        if chain_id is not None:
            self._in_memory_offers.pop(f"{chain_id}:{offer_id}", None)
            self._indexed_at.pop(f"{chain_id}:{offer_id}", None)
        else:
            for key in [k for k in self._in_memory_offers if k.endswith(f":{offer_id}")]:
                del self._in_memory_offers[key]
                self._indexed_at.pop(key, None)

    def reindex_from_cache(self, cache: Any) -> int:
        """Backfill the in-memory index from an OfferCache (#2470).

        Offers synced before this feed existed (or while the search service
        was down) live only in the cache — hydrate once so ``search`` sees
        them. Memory entries for scanned chains that the cache no longer
        holds are pruned; chains the cache does not know are left alone.
        Returns the number of offers indexed.
        """
        indexed = 0
        seen_keys: set[str] = set()
        self._expire_stale()
        try:
            known = list(cache._get_known_chains())  # noqa: SLF001
        except _OPS_ERRORS:
            return 0
        for cid in known:
            try:
                offers = cache.list_offers_by_chain(cid)
            except _OPS_ERRORS:
                continue
            cached_ids = {o.offer_id for o in offers}
            for key in [k for k in self._in_memory_offers if k.startswith(f"{cid}:")]:
                if key.split(":", 1)[1] not in cached_ids:
                    del self._in_memory_offers[key]
                    self._indexed_at.pop(key, None)
            for offer in offers:
                self.index_offer(offer)
                seen_keys.add(self._memory_key(offer))
                indexed += 1
        return indexed

    def search(
        self,
        query: str = "",
        chain_id: str | None = None,
        service_type: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int = 100,
    ) -> list[SyncedOffer]:
        """Search offers with text query and filters."""
        # Clamp like the router does — a negative limit would slice from the
        # end / pass through to the backend unbounded (#1543).
        limit = min(max(int(limit), 1), 500)
        if self._enabled and self._client is not None:
            try:
                filter_expr: list[str] = []
                if chain_id:
                    filter_expr.append(f'chain_id = "{chain_id}"')
                if service_type:
                    filter_expr.append(f'service_type = "{service_type}"')
                if min_price is not None:
                    filter_expr.append(f"price >= {min_price}")
                if max_price is not None:
                    filter_expr.append(f"price <= {max_price}")

                results = self._client.index(self._index_name).search(
                    query,
                    {"limit": limit, "filter": " AND ".join(filter_expr) if filter_expr else None},
                )
                hits = results.get("hits", []) if isinstance(results, dict) else []
                return [SyncedOffer.from_dict(hit) for hit in hits]
            except _OPS_ERRORS as e:
                logger.warning("Search query error: %s, falling back to in-memory", e)

        return self._in_memory_search(query, chain_id, service_type, min_price, max_price, limit)

    def _in_memory_search(
        self,
        query: str,
        chain_id: str | None,
        service_type: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        limit: int,
    ) -> list[SyncedOffer]:
        """Fallback in-memory search with basic text matching."""
        self._expire_stale()
        offers = list(self._in_memory_offers.values())
        if chain_id:
            offers = [o for o in offers if o.chain_id == chain_id]
        if service_type:
            offers = [o for o in offers if o.service_type == service_type]
        if min_price is not None:
            offers = [o for o in offers if o.price >= min_price]
        if max_price is not None:
            offers = [o for o in offers if o.price <= max_price]
        if query:
            q_lower = query.lower()
            offers = [
                o
                for o in offers
                if q_lower in o.offer_id.lower()
                or q_lower in o.provider.lower()
                or q_lower in o.service_type.lower()
                or any(q_lower in str(v).lower() for v in o.attributes.values())
            ]
        offers.sort(key=lambda o: o.price)
        return offers[:limit]

    def close(self) -> None:
        """Clean up resources."""
        self._in_memory_offers.clear()
        self._indexed_at.clear()
        self._client = None
