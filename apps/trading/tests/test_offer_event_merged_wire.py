"""Merge-regression pin: legacy node market-listing wire → OfferEvent →
SyncedOffer → OfferCache → subscription filter (#1635 + #1567 merged state).

The blockchain-node publishes ``offer`` payloads keyed
``listing_id``/``seller_address``/``item_type`` with status ``"active"`` —
*not* the canonical ``SyncedOffer.to_dict()`` shape. Before #1635 every
node event collapsed to an empty ``offer_id`` and all offers shared the
``offer:`` cache key; #1567 then namespaced cache keys by chain. This test
exercises the merged path end-to-end: a faithful legacy payload rides the
gossip ``OfferEvent`` envelope (which carries ``chain_id``), lands in the
chain-namespaced ``OfferCache``, and still matches an
``OfferSubscription`` filter on the folded ``attributes``.

Coder: C
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.subscription_types import OfferEvent, OfferSubscription


def _legacy_node_offer_payload() -> dict:
    """Faithful copy of the dict ``apps/blockchain-node/src/aitbc_chain/rpc/market.py``
    builds for each parsed ``market_create`` tx — the wire the trading sync
    layer actually consumes."""
    return {
        "listing_id": "tx_0042",
        "seller_address": "0xSeller00000000000000000000000000000001",
        "provider_address": "0xProvider000000000000000000000000000002",
        "service_type": "gpu_market",
        "model": "",
        "item_type": "GPU",
        "price": 0.05,
        "price_unit": "AIT/h",
        "description": "H100 rental",
        "deployment_type": "",
        "gpu_name": "NVIDIA H100",
        "gpu_device": "0",
        "gpu_uuid": "GPU-aaa",
        "gpu_model": "NVIDIA H100",
        "memory_gb": 80,
        "disk_quota_mb": 512000,
        "compute_capability": "9.0",
        "endpoint": "http://10.0.0.5:11434",
        "status": "active",
        "created_at": "2026-11-10T00:00:00+00:00",
    }


def _legacy_gossip_message(chain_id: str = "ait-hub") -> dict:
    """What the node gossips on ``offers.{chain_id}``: the OfferEvent envelope
    carries chain_id; the embedded offer payload does not."""
    return {
        "event_type": "created",
        "offer_id": "tx_0042",
        "chain_id": chain_id,
        "offer": _legacy_node_offer_payload(),
        "timestamp": "2026-11-10T12:00:00+00:00",
        "source": "blockchain-node",
    }


@pytest.mark.asyncio
async def test_legacy_wire_event_populates_chain_namespaced_cache() -> None:
    from trading_service.services.offer_subscription_service import OfferSubscriptionService

    cache = OfferCache()
    svc = OfferSubscriptionService(cache=cache)

    event = OfferEvent.from_dict(_legacy_gossip_message())
    # Envelope backfill: the offer payload has no chain_id of its own.
    assert event.offer is not None
    assert event.offer.chain_id == "ait-hub"
    assert event.offer.offer_id == "tx_0042"
    assert event.offer.status == "available"  # node says "active"

    await svc.inject_event(event)

    # #1567 namespaced key: the offer is retrievable under its real chain,
    # not collapsed onto a shared "offer:" key.
    cached = cache.get_offer("tx_0042", "ait-hub")
    assert cached is not None
    assert cached.offer_id == "tx_0042"
    assert cached.chain_id == "ait-hub"
    assert cached.provider == "0xSeller00000000000000000000000000000001"
    assert cached.service_type == "gpu_market"
    assert cached.price == Decimal("0.05")
    # Descriptive wire keys survive in attributes for filter matching.
    assert cached.attributes["gpu_model"] == "NVIDIA H100"
    assert cached.attributes["endpoint"] == "http://10.0.0.5:11434"
    await svc.stop_all()


@pytest.mark.asyncio
async def test_legacy_wire_offer_matches_subscription_filters() -> None:
    """The folded attributes must satisfy the same OfferSubscription filters
    a canonical-shape offer would — gpu_model/service_type/price bounds."""
    from trading_service.services.offer_subscription_service import OfferSubscriptionService

    cache = OfferCache()
    svc = OfferSubscriptionService(cache=cache)
    await svc.inject_event(OfferEvent.from_dict(_legacy_gossip_message()))

    matching = OfferSubscription(
        chain_id="ait-hub",
        service_type="gpu_market",
        min_price=Decimal("0.01"),
        max_price=Decimal("0.10"),
        gpu_model="NVIDIA H100",
    )
    assert matching.matches(OfferEvent.from_dict(_legacy_gossip_message())) is True

    # Same event, wrong gpu_model filter — must not match.
    wrong_gpu = OfferSubscription(chain_id="ait-hub", gpu_model="NVIDIA A100")
    assert wrong_gpu.matches(OfferEvent.from_dict(_legacy_gossip_message())) is False

    # Wrong chain filter — must not match even though the offer is cached.
    wrong_chain = OfferSubscription(chain_id="ait-island1")
    assert wrong_chain.matches(OfferEvent.from_dict(_legacy_gossip_message())) is False

    # And the cached offer is directly visible to a chain-scoped listing.
    listed = cache.list_offers_by_chain("ait-hub")
    assert [o.offer_id for o in listed] == ["tx_0042"]
    await svc.stop_all()


@pytest.mark.asyncio
async def test_two_chains_same_listing_id_do_not_collide() -> None:
    """#1567 merged with #1635: two chains can legitimately carry the same
    listing_id; the namespaced cache must keep both."""
    from trading_service.services.offer_subscription_service import OfferSubscriptionService

    cache = OfferCache()
    svc = OfferSubscriptionService(cache=cache)

    msg_a = _legacy_gossip_message(chain_id="ait-hub")
    msg_b = _legacy_gossip_message(chain_id="ait-island1")
    await svc.inject_event(OfferEvent.from_dict(msg_a))
    await svc.inject_event(OfferEvent.from_dict(msg_b))

    a = cache.get_offer("tx_0042", "ait-hub")
    b = cache.get_offer("tx_0042", "ait-island1")
    assert a is not None and a.chain_id == "ait-hub"
    assert b is not None and b.chain_id == "ait-island1"
    assert len(cache.list_offers_by_chain("ait-hub")) == 1
    assert len(cache.list_offers_by_chain("ait-island1")) == 1
    await svc.stop_all()
