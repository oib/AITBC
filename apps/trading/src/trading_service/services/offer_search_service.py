"""Offer search index service (v0.8.2 §B7).

Optional integration with Meilisearch (preferred) or Elasticsearch for
advanced offer search. Falls back to in-memory search when the index
is unavailable or disabled.

The service indexes offers on sync/event and provides a query method
for advanced search with relevance ranking.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.trading.offer_types import SyncedOffer

from ..config import settings

logger = logging.getLogger(__name__)


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
        self._in_memory_offers: dict[str, SyncedOffer] = {}

        if self._enabled:
            self._init_backend()

    def _init_backend(self) -> None:
        """Initialize the external search backend client."""
        try:
            if self._backend == "meilisearch":
                try:
                    import meilisearch  # type: ignore[import-not-found]

                    self._client = meilisearch.Client(self._backend_url)
                    # Ensure index exists
                    try:
                        self._client.get_index(self._index_name)
                    except Exception:
                        self._client.create_index(self._index_name)
                    logger.info("Meilisearch connected at %s", self._backend_url)
                except ImportError:
                    logger.warning("meilisearch package not installed, falling back to in-memory search")
                    self._enabled = False
            else:
                logger.warning("Unknown search backend %s, falling back to in-memory", self._backend)
                self._enabled = False
        except Exception as e:
            logger.warning("Search backend init failed: %s, falling back to in-memory", e)
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def index_offer(self, offer: SyncedOffer) -> None:
        """Add or update an offer in the search index."""
        if self._enabled and self._client is not None:
            try:
                self._client.index(self._index_name).add_documents([offer.to_dict()], "offer_id")
            except Exception as e:
                logger.warning("Search index error for offer %s: %s", offer.offer_id, e)
                self._in_memory_offers[offer.offer_id] = offer
        else:
            self._in_memory_offers[offer.offer_id] = offer

    def delete_offer(self, offer_id: str) -> None:
        """Remove an offer from the search index."""
        if self._enabled and self._client is not None:
            try:
                self._client.index(self._index_name).delete_document(offer_id)
            except Exception as e:
                logger.warning("Search delete error for offer %s: %s", offer_id, e)
        self._in_memory_offers.pop(offer_id, None)

    def search(
        self,
        query: str = "",
        chain_id: str | None = None,
        service_type: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        limit: int = 100,
    ) -> list[SyncedOffer]:
        """Search offers with text query and filters."""
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
            except Exception as e:
                logger.warning("Search query error: %s, falling back to in-memory", e)

        return self._in_memory_search(query, chain_id, service_type, min_price, max_price, limit)

    def _in_memory_search(
        self,
        query: str,
        chain_id: str | None,
        service_type: str | None,
        min_price: float | None,
        max_price: float | None,
        limit: int,
    ) -> list[SyncedOffer]:
        """Fallback in-memory search with basic text matching."""
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
        self._client = None
