"""Pins for AUDIT-TRADING-TRUST-BOUNDARY-1 (#3061), gossip half.

Gossip offer events had no publisher authentication and no chain
scoping: any well-formed OfferEvent on ``offers.<A>`` was written
verbatim into the cache — a forged cross-chain event could inject or
DELETE another chain's offers. The topic is now the enforced boundary:
``event.chain_id`` must equal the subscribed chain. The stale/replay
guard (#1696) is also enabled by default — each (chain, offer) pair has
a single publishing node, so per-key clock skew does not apply.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import SyncedOffer
from aitbc.trading.subscription_types import OfferEvent, SubscriptionStatus
from trading_service.config import settings
from trading_service.services.offer_subscription_service import OfferSubscriptionService


def _offer(offer_id: str, chain_id: str) -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="provider-1",
        service_type="gpu_market",
        price=5.0,
        quantity=1,
        status="available",
        attributes={},
        last_synced=datetime.now(UTC).isoformat(),
        sync_status="fresh",
        sync_confidence=1.0,
    )


def _ev(event_type: str, offer_id: str, chain_id: str, ts: str = "") -> OfferEvent:
    return OfferEvent(
        event_type=event_type,
        offer_id=offer_id,
        chain_id=chain_id,
        offer=_offer(offer_id, chain_id) if event_type != "deleted" else None,
        timestamp=ts or datetime.now(UTC).isoformat(),
        source="test",
    )


async def _svc_with_chain(chain_id: str, cache: OfferCache) -> OfferSubscriptionService:
    svc = OfferSubscriptionService(cache=cache)
    # Start the bookkeeping the gossip loop expects without opening a
    # real subscription — _gossip_iteration is driven directly.
    svc._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
    svc._last_event_time[chain_id] = 0.0
    return svc


async def _gossip(svc: OfferSubscriptionService, chain_id: str, event: OfferEvent) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(event)
    await svc._gossip_iteration(chain_id, queue, silent_threshold=999.0)


@pytest.mark.asyncio
async def test_cross_chain_created_is_dropped():
    """A forged event on offers.chain-a naming chain-b must not write
    chain-b's offer into the cache."""
    cache = OfferCache()
    svc = await _svc_with_chain("chain-a", cache)
    await _gossip(svc, "chain-a", _ev("created", "forged-1", "chain-b"))
    assert cache.get_offer("forged-1", "chain-b") is None
    assert cache.get_offer("forged-1", "chain-a") is None


@pytest.mark.asyncio
async def test_cross_chain_deleted_cannot_evict_legit_offer():
    """The destructive half: a forged DELETED on the wrong topic must not
    evict a legitimate offer belonging to another chain."""
    cache = OfferCache()
    svc = await _svc_with_chain("chain-a", cache)
    # Legit chain-b offer present (as if synced/published properly).
    cache.set_offer(_offer("victim-1", "chain-b"))
    assert cache.get_offer("victim-1", "chain-b") is not None

    await _gossip(svc, "chain-a", _ev("deleted", "victim-1", "chain-b"))
    assert cache.get_offer("victim-1", "chain-b") is not None


@pytest.mark.asyncio
async def test_same_chain_event_still_applies():
    """Control: an event whose chain matches the topic flows through."""
    cache = OfferCache()
    svc = await _svc_with_chain("chain-a", cache)
    await _gossip(svc, "chain-a", _ev("created", "real-1", "chain-a"))
    assert cache.get_offer("real-1", "chain-a") is not None


@pytest.mark.asyncio
async def test_cross_chain_event_does_not_count_as_liveness():
    """A forged event must not reset the silence clock either — it is
    dropped before _last_event_time is touched."""
    cache = OfferCache()
    svc = await _svc_with_chain("chain-a", cache)
    before = svc._last_event_time["chain-a"]
    await _gossip(svc, "chain-a", _ev("created", "forged-2", "chain-b"))
    assert svc._last_event_time["chain-a"] == before


@pytest.mark.asyncio
async def test_stale_guard_enabled_by_default():
    """#3061 flipped the #1696 default: a replayed older event is dropped
    with NO monkeypatch — the guard is on out of the box."""
    assert settings.offer_event_stale_guard_enabled is True
    cache = OfferCache()
    svc = OfferSubscriptionService(cache=cache)
    await svc.start_chain("ait-hub")
    try:
        await svc.inject_event(_ev("created", "o1", "ait-hub", ts="2026-11-11T10:05:00+00:00"))
        # _offer() builds a fresh offer; overwrite with matching id via cache check below.
        await svc.inject_event(_ev("deleted", "o1", "ait-hub", ts="2026-11-11T10:00:00+00:00"))
        # The stale delete must NOT have evicted — replay dropped by default.
        assert cache.get_offer("o1", "ait-hub") is not None
    finally:
        svc._running = False
