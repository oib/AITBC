"""Pins for AUDIT-TRADING-DEBOUNCE-STARVE-1 (#3060).

``OfferNotificationService`` used to cancel and restart the flush timer
on EVERY matching event — a stream sustained faster than the debounce
window starved ``_flush_batch`` forever while ``_pending`` grew without
bound per subscriber. The deadline now belongs to the first pending
event (later events coalesce without extending it) and a full batch
flushes immediately.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from aitbc.trading.offer_types import OfferSyncStatus, SyncedOffer
from aitbc.trading.subscription_types import OfferEvent, OfferSubscription
from trading_service.services.offer_notification_service import OfferNotificationService


def _offer(offer_id: str, chain_id: str = "chain-a") -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="provider-x",
        service_type="gpu_market",
        price=Decimal("1.0"),
        quantity=1,
        status="available",
        attributes={},
        last_synced=datetime.now(UTC).isoformat(),
        sync_status=OfferSyncStatus.FRESH.value,
        sync_confidence=1.0,
    )


def _event(offer_id: str, chain_id: str = "chain-a") -> OfferEvent:
    return OfferEvent(
        event_type="created",
        offer_id=offer_id,
        chain_id=chain_id,
        offer=_offer(offer_id, chain_id),
        timestamp=datetime.now(UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_sustained_stream_cannot_starve_the_flush():
    """The defect verbatim: events every 20ms against a 50ms debounce —
    under reset-per-event semantics the flush NEVER fires; now it must
    fire roughly every debounce window and deliver every event."""
    svc = OfferNotificationService(debounce_ms=50)
    received: list = []
    await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), received.append)

    sent = 0
    for _ in range(15):  # ~300ms of sustained stream, 6x the debounce window
        await svc.process_event(_event(f"o{sent}"))
        sent += 1
        await asyncio.sleep(0.02)

    await asyncio.sleep(0.15)
    delivered = sum(n.batch_size for n in received)
    assert delivered == sent
    # Multiple batches prove periodic flushing — one giant batch at the
    # end would mean the stream still starved the timer.
    assert len(received) >= 2
    await svc.close()


@pytest.mark.asyncio
async def test_pending_cap_flushes_immediately():
    """A full batch must not keep queueing — it flushes now, bounding
    per-subscriber memory even under an infinite stream."""
    svc = OfferNotificationService(debounce_ms=60_000)  # deadline never reached
    svc._MAX_PENDING_EVENTS = 5
    received: list = []
    await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), received.append)

    for i in range(5):
        await svc.process_event(_event(f"cap{i}"))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].batch_size == 5
    assert svc.get_subscriptions()["sub-1"]["pending_events"] == 0
    await svc.close()


@pytest.mark.asyncio
async def test_events_during_callback_get_a_fresh_deadline():
    """Events appended while the notify callback is in flight miss the
    popped batch — they must arm a new deadline, not strand."""
    svc = OfferNotificationService(debounce_ms=30)
    received: list = []
    injected = False

    async def _cb(notification):
        nonlocal injected
        received.append(notification)
        if not injected:
            injected = True
            # Lands while this flush task is still registered — the exact
            # window where a naive first-event-wins check strands events.
            await svc.process_event(_event("late"))

    await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), _cb)
    await svc.process_event(_event("first"))
    await asyncio.sleep(0.15)

    assert len(received) == 2
    assert received[1].batch_size == 1
    assert received[1].events[0].offer_id == "late"
    await svc.close()


@pytest.mark.asyncio
async def test_unrelated_events_do_not_extend_the_deadline():
    """Non-matching events must not touch the subscriber's timer at all."""
    svc = OfferNotificationService(debounce_ms=40)
    received: list = []
    await svc.register_subscriber("sub-1", OfferSubscription(chain_id="chain-a"), received.append)

    await svc.process_event(_event("m1"))
    for i in range(10):
        await svc.process_event(_event(f"other{i}", chain_id="chain-b"))
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.08)

    assert len(received) == 1
    assert received[0].batch_size == 1
    await svc.close()
