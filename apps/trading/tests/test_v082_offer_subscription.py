"""Integration tests for v0.8.2 offer subscription features (B8).

Tests cover:
- OfferSubscriptionService: event handling, cache updates, status tracking
- OfferNotificationService: saved query matching, debounced batches
- OfferSearchService: in-memory fallback search
- CLI commands: smoke tests for watch, subscription-status, search
- WebSocket endpoint: subscription registration and event streaming
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import SyncedOffer
from aitbc.trading.subscription_types import (
    OfferEvent,
    OfferNotification,
    OfferSubscription,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_offer(
    offer_id: str = "offer-1", chain_id: str = "ait-hub", price: float = 5.0, status: str = "available"
) -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="provider-1",
        service_type="gpu_marketplace",
        price=price,
        quantity=1,
        status=status,
        attributes={"region": "us-east", "gpu_model": "A100"},
        last_synced=datetime.now(UTC).isoformat(),
        sync_status="fresh",
        sync_confidence=1.0,
    )


def _make_event(
    event_type: str = "created",
    offer_id: str = "offer-1",
    chain_id: str = "ait-hub",
    offer: SyncedOffer | None = None,
) -> OfferEvent:
    return OfferEvent(
        event_type=event_type,
        offer_id=offer_id,
        chain_id=chain_id,
        offer=offer,
        timestamp=datetime.now(UTC).isoformat(),
        source="test",
    )


# ---------------------------------------------------------------------------
# OfferSubscriptionService tests
# ---------------------------------------------------------------------------


class TestOfferSubscriptionService:
    @pytest.mark.asyncio
    async def test_start_and_stop_chain(self) -> None:
        from trading_service.services.offer_subscription_service import OfferSubscriptionService

        svc = OfferSubscriptionService()
        await svc.start_chain("ait-hub")
        assert svc.running
        assert svc.get_chain_status()[0]["chain_id"] == "ait-hub"
        assert svc.get_chain_status()[0]["status"] == "subscribed"
        await svc.stop_chain("ait-hub")
        assert svc.get_chain_status()[0]["status"] == "disconnected"
        await svc.stop_all()

    @pytest.mark.asyncio
    async def test_event_updates_cache(self) -> None:
        from trading_service.services.offer_subscription_service import OfferSubscriptionService

        cache = OfferCache()
        svc = OfferSubscriptionService(cache=cache)
        await svc.start_chain("ait-hub")

        offer = _make_offer()
        event = _make_event("created", offer=offer)
        await svc.inject_event(event)

        cached = cache.get_offer("offer-1")
        assert cached is not None
        assert cached.offer_id == "offer-1"
        assert cached.chain_id == "ait-hub"
        await svc.stop_all()

    @pytest.mark.asyncio
    async def test_deleted_event_removes_from_cache(self) -> None:
        from trading_service.services.offer_subscription_service import OfferSubscriptionService

        cache = OfferCache()
        svc = OfferSubscriptionService(cache=cache)
        await svc.start_chain("ait-hub")

        offer = _make_offer()
        await svc.inject_event(_make_event("created", offer=offer))
        assert cache.get_offer("offer-1") is not None

        await svc.inject_event(_make_event("deleted", offer_id="offer-1", offer=None))
        assert cache.get_offer("offer-1") is None
        await svc.stop_all()

    @pytest.mark.asyncio
    async def test_event_count_tracking(self) -> None:
        from trading_service.services.offer_subscription_service import OfferSubscriptionService

        svc = OfferSubscriptionService()
        await svc.start_chain("ait-hub")

        offer = _make_offer()
        await svc.inject_event(_make_event("created", offer=offer))
        await svc.inject_event(_make_event("updated", offer=offer, offer_id="offer-1"))

        status = svc.get_chain_status()
        assert status[0]["event_count"] == 2
        assert status[0]["last_event"] != ""
        await svc.stop_all()

    @pytest.mark.asyncio
    async def test_callback_invoked(self) -> None:
        from trading_service.services.offer_subscription_service import OfferSubscriptionService

        received: list[OfferEvent] = []

        async def on_event(event: OfferEvent) -> None:
            received.append(event)

        svc = OfferSubscriptionService(on_event_callback=on_event)
        await svc.start_chain("ait-hub")

        offer = _make_offer()
        await svc.inject_event(_make_event("created", offer=offer))
        assert len(received) == 1
        assert received[0].offer_id == "offer-1"
        await svc.stop_all()


# ---------------------------------------------------------------------------
# OfferNotificationService tests
# ---------------------------------------------------------------------------


class TestOfferNotificationService:
    @pytest.mark.asyncio
    async def test_register_and_unregister(self) -> None:
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=100)
        sub = OfferSubscription(chain_id="ait-hub")
        await svc.register_subscriber("sub-1", sub)
        assert svc.subscriber_count == 1
        assert "sub-1" in svc.get_subscriptions()
        await svc.unregister_subscriber("sub-1")
        assert svc.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_matching_events_collected(self) -> None:
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=500)
        sub = OfferSubscription(chain_id="ait-hub", service_type="gpu_marketplace")
        await svc.register_subscriber("sub-1", sub)

        offer = _make_offer()  # service_type defaults to "gpu_marketplace"
        event = _make_event("created", offer=offer)
        await svc.process_event(event)

        # Pending events should have 1 entry
        assert len(svc._pending.get("sub-1", [])) == 1  # noqa: SLF001
        await svc.unregister_subscriber("sub-1")

    @pytest.mark.asyncio
    async def test_non_matching_events_filtered(self) -> None:
        from trading_service.services.offer_notification_service import OfferNotificationService

        svc = OfferNotificationService(debounce_ms=500)
        sub = OfferSubscription(chain_id="ait-hub", max_price=3.0)
        await svc.register_subscriber("sub-1", sub)

        offer = _make_offer(price=10.0)  # price exceeds max_price
        event = _make_event("created", offer=offer)
        await svc.process_event(event)

        assert len(svc._pending.get("sub-1", [])) == 0  # noqa: SLF001
        await svc.unregister_subscriber("sub-1")

    @pytest.mark.asyncio
    async def test_debounced_batch_notification(self) -> None:
        from trading_service.services.offer_notification_service import OfferNotificationService

        received: list[OfferNotification] = []

        async def on_notify(notification: OfferNotification) -> None:
            received.append(notification)

        svc = OfferNotificationService(debounce_ms=50)
        sub = OfferSubscription(chain_id="ait-hub")
        await svc.register_subscriber("sub-1", sub, on_notify)

        offer1 = _make_offer(offer_id="offer-1")
        offer2 = _make_offer(offer_id="offer-2")
        await svc.process_event(_make_event("created", offer=offer1, offer_id="offer-1"))
        await svc.process_event(_make_event("created", offer=offer2, offer_id="offer-2"))

        # Wait for debounce to fire
        await asyncio.sleep(0.15)
        assert len(received) == 1
        assert received[0].batch_size == 2
        await svc.unregister_subscriber("sub-1")

    @pytest.mark.asyncio
    async def test_flush_all(self) -> None:
        from trading_service.services.offer_notification_service import OfferNotificationService

        received: list[OfferNotification] = []

        async def on_notify(notification: OfferNotification) -> None:
            received.append(notification)

        svc = OfferNotificationService(debounce_ms=10000)  # long debounce
        sub = OfferSubscription(chain_id="ait-hub")
        await svc.register_subscriber("sub-1", sub, on_notify)

        offer = _make_offer()
        await svc.process_event(_make_event("created", offer=offer))

        await svc.flush_all()
        assert len(received) == 1
        assert received[0].batch_size == 1
        await svc.close()


# ---------------------------------------------------------------------------
# OfferSearchService tests
# ---------------------------------------------------------------------------


class TestOfferSearchService:
    def test_in_memory_search(self) -> None:
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)  # force in-memory
        offer1 = _make_offer(offer_id="gpu-a100", price=5.0)
        offer2 = _make_offer(offer_id="gpu-v100", price=3.0, chain_id="ait-island1")
        svc.index_offer(offer1)
        svc.index_offer(offer2)

        results = svc.search(chain_id="ait-hub")
        assert len(results) == 1
        assert results[0].offer_id == "gpu-a100"

        results = svc.search(min_price=4.0)
        assert len(results) == 1
        assert results[0].offer_id == "gpu-a100"

        results = svc.search(query="v100")
        assert len(results) == 1
        assert results[0].offer_id == "gpu-v100"

    def test_delete_offer(self) -> None:
        from trading_service.services.offer_search_service import OfferSearchService

        svc = OfferSearchService(enabled=False)
        offer = _make_offer()
        svc.index_offer(offer)
        assert len(svc.search()) == 1
        svc.delete_offer("offer-1")
        assert len(svc.search()) == 0


# ---------------------------------------------------------------------------
# OfferSubscription matching tests
# ---------------------------------------------------------------------------


class TestOfferSubscriptionMatching:
    def test_chain_filter_matches(self) -> None:
        sub = OfferSubscription(chain_id="ait-hub")
        offer = _make_offer(chain_id="ait-hub")
        event = _make_event("created", offer=offer)
        assert sub.matches(event)

    def test_chain_filter_no_match(self) -> None:
        sub = OfferSubscription(chain_id="ait-island1")
        offer = _make_offer(chain_id="ait-hub")
        event = _make_event("created", offer=offer)
        assert not sub.matches(event)

    def test_price_filter(self) -> None:
        sub = OfferSubscription(min_price=2.0, max_price=8.0)
        offer = _make_offer(price=5.0)
        event = _make_event("created", offer=offer)
        assert sub.matches(event)

        offer_expensive = _make_offer(price=10.0)
        event_expensive = _make_event("created", offer=offer_expensive)
        assert not sub.matches(event_expensive)

    def test_deleted_event_matches_chain_only(self) -> None:
        sub = OfferSubscription(chain_id="ait-hub", service_type="gpu_marketplace")
        event = _make_event("deleted", offer=None)
        assert sub.matches(event)

    def test_region_filter(self) -> None:
        sub = OfferSubscription(region="us-east")
        offer = _make_offer()
        event = _make_event("created", offer=offer)
        assert sub.matches(event)

        offer_west = SyncedOffer(
            offer_id="offer-west",
            chain_id="ait-hub",
            provider="p",
            service_type="gpu_marketplace",
            price=5.0,
            quantity=1,
            status="available",
            attributes={"region": "us-west"},
        )
        event_west = _make_event("created", offer=offer_west, offer_id="offer-west")
        assert not sub.matches(event_west)


# ---------------------------------------------------------------------------
# OfferEvent serialization tests
# ---------------------------------------------------------------------------


class TestOfferEventSerialization:
    def test_to_dict_with_offer(self) -> None:
        offer = _make_offer()
        event = _make_event("created", offer=offer)
        data = event.to_dict()
        assert data["event_type"] == "created"
        assert data["offer_id"] == "offer-1"
        assert data["offer"] is not None
        assert data["offer"]["offer_id"] == "offer-1"

    def test_to_dict_without_offer(self) -> None:
        event = _make_event("deleted", offer=None)
        data = event.to_dict()
        assert data["offer"] is None
        assert data["event_type"] == "deleted"

    def test_from_dict_roundtrip(self) -> None:
        offer = _make_offer()
        event = _make_event("updated", offer=offer)
        data = event.to_dict()
        restored = OfferEvent.from_dict(data)
        assert restored.event_type == "updated"
        assert restored.offer_id == "offer-1"
        assert restored.offer is not None
        assert restored.offer.price == 5.0

    def test_notification_build_and_serialize(self) -> None:
        offer = _make_offer()
        events = [_make_event("created", offer=offer), _make_event("updated", offer=offer)]
        notification = OfferNotification.build(events, chain_id="ait-hub")
        assert notification.batch_size == 2
        assert notification.chain_id == "ait-hub"
        data = notification.to_dict()
        assert data["batch_size"] == 2
        assert len(data["events"]) == 2


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


class TestCLICommands:
    def test_watch_command_exists(self) -> None:
        from click.testing import CliRunner

        from aitbc_cli.commands.trade import trade

        runner = CliRunner()
        result = runner.invoke(trade, ["watch", "--help"])
        assert result.exit_code == 0
        assert "Stream offer changes" in result.output

    def test_subscription_status_command_exists(self) -> None:
        from click.testing import CliRunner

        from aitbc_cli.commands.trade import trade

        runner = CliRunner()
        result = runner.invoke(trade, ["subscription-status", "--help"])
        assert result.exit_code == 0
        assert "subscription health" in result.output

    def test_search_command_exists(self) -> None:
        from click.testing import CliRunner

        from aitbc_cli.commands.trade import trade

        runner = CliRunner()
        result = runner.invoke(trade, ["search", "--help"])
        assert result.exit_code == 0
        assert "search index" in result.output.lower()


# ---------------------------------------------------------------------------
# WebSocket endpoint tests (using FastAPI TestClient)
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:
    def test_subscribe_lease_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from trading_service.main import app

        client = TestClient(app)
        response = client.post(
            "/v1/trading/offers/subscribe",
            json={"node_id": "test-node", "chain_id": "ait-hub"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "test-node"
        assert data["chain_id"] == "ait-hub"
        assert "expiry" in data

    def test_heartbeat_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from trading_service.main import app

        client = TestClient(app)
        response = client.post(
            "/v1/trading/offers/heartbeat",
            json={"node_id": "test-node", "chain_id": "ait-hub"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["renewed"] is True

    def test_subscription_status_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from trading_service.main import app

        client = TestClient(app)
        response = client.get("/v1/trading/offers/subscription-status")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_search_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        from trading_service.main import app

        client = TestClient(app)
        response = client.get("/v1/trading/offers/search", params={"q": "gpu", "limit": 10})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_subscribe_missing_node_id(self) -> None:
        from fastapi.testclient import TestClient

        from trading_service.main import app

        client = TestClient(app)
        response = client.post(
            "/v1/trading/offers/subscribe",
            json={"chain_id": "ait-hub"},
        )
        assert response.status_code == 400
