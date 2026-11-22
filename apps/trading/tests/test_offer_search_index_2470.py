"""#2470: offer sync must feed the search index.

``OfferSearchService.index_offer`` had zero call sites — sync wrote the
OfferCache but nothing populated the search index, so
``GET /v1/trading/offers/search`` could only ever return ``[]``. The fix
feeds every synced/deleted offer into the process search singleton and
backfills the in-memory index from the shared OfferCache on first use.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from aitbc.trading.offer_types import SyncedOffer
from trading_service.services.offer_search_service import OfferSearchService
from trading_service.services.offer_sync_service import OfferSyncService


def _offer(offer_id: str, chain_id: str = "bc-2", price: str = "1.5") -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="prov",
        service_type="gpu_market",
        price=Decimal(price),
        quantity=1,
        status="available",
        attributes={"model": "h100"},
    )


class _RecordingIndex:
    def __init__(self) -> None:
        self.indexed: list[SyncedOffer] = []
        self.deleted: list[tuple[str, str | None]] = []

    def index_offer(self, offer: SyncedOffer) -> None:
        self.indexed.append(offer)

    def delete_offer(self, offer_id: str, chain_id: str | None = None) -> None:
        self.deleted.append((offer_id, chain_id))


# --- OfferSearchService in-memory namespacing ---


def test_in_memory_index_is_chain_namespaced():
    """Two chains may carry the same offer_id — both must stay searchable."""
    svc = OfferSearchService(enabled=False)
    svc.index_offer(_offer("gpu-1", chain_id="bc-2"))
    svc.index_offer(_offer("gpu-1", chain_id="bc-3", price="2.5"))

    hits = svc.search(chain_id="bc-2")
    assert len(hits) == 1 and hits[0].chain_id == "bc-2"
    hits = svc.search(chain_id="bc-3")
    assert len(hits) == 1 and hits[0].price == Decimal("2.5")


def test_delete_offer_scoped_to_chain():
    svc = OfferSearchService(enabled=False)
    svc.index_offer(_offer("gpu-1", chain_id="bc-2"))
    svc.index_offer(_offer("gpu-1", chain_id="bc-3"))

    svc.delete_offer("gpu-1", "bc-2")
    assert [o.chain_id for o in svc.search()] == ["bc-3"]

    svc.delete_offer("gpu-1")
    assert svc.search() == []


def test_reindex_from_cache_backfills_and_prunes():
    svc = OfferSearchService(enabled=False)
    # A stale memory entry for a scanned chain that the cache no longer has.
    svc.index_offer(_offer("ghost", chain_id="bc-2"))

    cache = MagicMock()
    cache._get_known_chains.return_value = ["bc-2"]
    cache.list_offers_by_chain.return_value = [_offer("gpu-1", chain_id="bc-2")]

    assert svc.reindex_from_cache(cache) == 1
    remaining = {o.offer_id for o in svc.search()}
    assert remaining == {"gpu-1"}


def test_reindex_from_cache_swallows_cache_errors():
    svc = OfferSearchService(enabled=False)
    cache = MagicMock()
    cache._get_known_chains.side_effect = RuntimeError("redis down")
    assert svc.reindex_from_cache(cache) == 0


# --- sync feeds the index ---


def _sync_service_with_index(index: _RecordingIndex) -> OfferSyncService:
    blockchain = AsyncMock()
    blockchain.query_offers = AsyncMock(
        return_value=[
            {"gpu_id": "gpu-1", "provider": "p1", "price": 1.5, "capacity": 2, "status": "available"},
            {"gpu_id": "gpu-2", "provider": "p2", "price": 2.0, "capacity": 1, "status": "available"},
        ]
    )
    svc = OfferSyncService(session=AsyncMock(), cache=MagicMock(), blockchain_client=blockchain)
    svc._search_index = lambda: index  # noqa: SLF001 - inject the recorder
    # cache is a MagicMock — give it the methods sync_chain calls
    svc._cache.set_offer = MagicMock()  # noqa: SLF001
    svc._cache.set_sync_metadata = MagicMock()  # noqa: SLF001
    svc._cache.mark_syncing = MagicMock()  # noqa: SLF001
    svc._cache.get_stale_offers = MagicMock(return_value=[])  # noqa: SLF001
    svc._cache.list_offers_by_chain = MagicMock(return_value=[])  # noqa: SLF001
    return svc


@pytest.mark.asyncio
async def test_sync_chain_indexes_every_offer():
    index = _RecordingIndex()
    svc = _sync_service_with_index(index)

    result = await svc.sync_chain("bc-2")
    assert result["synced"] == 2
    assert {o.offer_id for o in index.indexed} == {"gpu-1", "gpu-2"}
    assert all(o.chain_id == "bc-2" for o in index.indexed)


@pytest.mark.asyncio
async def test_sync_chain_unindexes_deleted_offers():
    index = _RecordingIndex()
    svc = _sync_service_with_index(index)
    # Chain reports nothing new; cache holds one offer the chain dropped.
    stale = _offer("gpu-old", chain_id="bc-2")
    svc._cache.list_offers_by_chain = MagicMock(return_value=[stale])  # noqa: SLF001
    svc._cache.delete_offer = MagicMock()  # noqa: SLF001
    svc._blockchain.query_offers = AsyncMock(return_value=[])  # type: ignore[attr-defined]

    result = await svc.sync_chain("bc-2")
    assert result.get("deleted") == 1
    assert index.deleted == [("gpu-old", "bc-2")]


@pytest.mark.asyncio
async def test_sync_survives_index_failure():
    class _BoomIndex:
        def index_offer(self, offer):  # noqa: ANN001, ANN202
            raise RuntimeError("index down")

        def delete_offer(self, offer_id, chain_id=None):  # noqa: ANN001, ANN202
            raise RuntimeError("index down")

    svc = _sync_service_with_index(_BoomIndex())  # type: ignore[arg-type]
    result = await svc.sync_chain("bc-2")
    assert result["synced"] == 2
