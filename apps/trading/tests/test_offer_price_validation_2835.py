"""#2835: offer price validation at every ingest surface.

A NaN/Infinity/negative price from a buggy or malicious source must never
reach OfferCache — once cached it crashes every ``offer.price``
sort/filter (InvalidOperation → persistent 500s on discover/search/
subscription delivery) and serializes to clients as a real quote.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import OfferEventType, SyncedOffer
from aitbc.trading.subscription_types import OfferEvent


def test_parse_offer_price_accepts_valid() -> None:
    from aitbc.trading.offer_types import parse_offer_price

    assert parse_offer_price("0") == Decimal("0")  # zero sorts/filters cleanly
    assert parse_offer_price("0.05") == Decimal("0.05")
    assert parse_offer_price(3) == Decimal("3")
    assert parse_offer_price(Decimal("1E+2")) == Decimal("100")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "-0.5", "-1", "abc", "", None])
def test_parse_offer_price_rejects_bad(bad: object) -> None:
    from aitbc.trading.offer_types import parse_offer_price

    with pytest.raises(ValueError):
        parse_offer_price(bad)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "abc"])
def test_synced_offer_from_dict_rejects_bad_price(bad: str) -> None:
    with pytest.raises(ValueError):
        SyncedOffer.from_dict({"offer_id": "o1", "chain_id": "ait-x", "price": bad})


def test_offer_event_from_dict_rejects_bad_price() -> None:
    """Gossip path: OfferEvent.from_dict must raise so the subscription
    service's _OPS_ERRORS decode guard drops the event."""
    with pytest.raises(ValueError):
        OfferEvent.from_dict(
            {
                "event_type": OfferEventType.UPDATED.value,
                "offer_id": "o1",
                "chain_id": "ait-x",
                "offer": {"offer_id": "o1", "price": "NaN"},
            }
        )


def test_poisoned_cache_entry_reads_as_absent() -> None:
    """A bad row already in the cache backend must not crash hydration —
    _read_offer_key treats it like any other deserialize failure."""
    cache = OfferCache()
    cache._cache.set(
        "offer:ait-x:bad",
        json.dumps({"offer_id": "bad", "chain_id": "ait-x", "price": "NaN", "quantity": 1}),
    )
    assert cache.get_offer("bad", "ait-x") is None


async def test_sync_chain_skips_invalid_price_offer() -> None:
    """The chain-RPC sync loop drops NaN-priced offers and still caches
    the valid ones — one poisoned row must not kill the sync."""
    from trading_service.services.offer_sync_service import OfferSyncService

    blockchain = AsyncMock()
    blockchain.query_offers = AsyncMock(
        return_value=[
            {"gpu_id": "gpu-bad", "price": "NaN", "capacity": 1, "provider": "p1"},
            {"gpu_id": "gpu-neg", "price": "-2", "capacity": 1, "provider": "p1"},
            {"gpu_id": "gpu-ok", "price": "0.05", "capacity": 4, "provider": "p1"},
        ]
    )
    cache = OfferCache()
    svc = OfferSyncService(session=AsyncMock(), cache=cache, blockchain_client=blockchain)

    result = await svc.sync_chain("ait-x")

    assert result["synced"] == 1
    assert cache.get_offer("gpu-ok", "ait-x") is not None
    assert cache.get_offer("gpu-bad", "ait-x") is None
    assert cache.get_offer("gpu-neg", "ait-x") is None
