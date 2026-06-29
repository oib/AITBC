"""Unit tests for the aitbc.trading offer subscription SDK (v0.8.2 §A4).

Covers:
- Subscription types (OfferEventType, OfferEvent, OfferSubscription,
  SubscriptionStatus, OfferNotification)
- OfferEvent serialization round-trip (to_dict / from_dict)
- OfferSubscription filter matching (chain, service_type, price range,
  region, gpu_model; deleted events match on chain only)
- OfferNotification.build + to_dict
- OfferEventType re-export from offer_types
- OfferSubscriptionClient init, lease registration, status tracking,
  message parsing, unsubscribe, close (WebSocket mocked)
- Polling fallback path (OfferSyncClient mocked)

No real trading service, WebSocket server, or blockchain node required.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aitbc.trading.offer_types import OfferEventType, SyncedOffer
from aitbc.trading.subscription_client import OfferSubscriptionClient
from aitbc.trading.subscription_types import (
    OfferEvent,
    OfferNotification,
    OfferSubscription,
    SubscriptionStatus,
)

RPC_URL = "http://localhost:8104"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(f"HTTP {status_code}", request=MagicMock(), response=resp)
    return resp


def _sample_offer(
    offer_id: str = "offer_001",
    chain_id: str = "ait-hub",
    price: float = 2.5,
    service_type: str = "gpu_marketplace",
    status: str = "available",
    attributes: dict | None = None,
) -> SyncedOffer:
    return SyncedOffer(
        offer_id=offer_id,
        chain_id=chain_id,
        provider="provider-1",
        service_type=service_type,
        price=price,
        quantity=1,
        status=status,
        attributes=attributes or {"region": "us-east", "gpu_model": "A100"},
    )


def _sample_event(
    event_type: str = "created",
    offer_id: str = "offer_001",
    chain_id: str = "ait-hub",
    offer: SyncedOffer | None = None,
) -> OfferEvent:
    return OfferEvent(
        event_type=event_type,
        offer_id=offer_id,
        chain_id=chain_id,
        offer=offer if offer is not None else _sample_offer(offer_id=offer_id, chain_id=chain_id),
        timestamp="2026-06-29T12:00:00+00:00",
        source="blockchain-node",
    )


# ---------------------------------------------------------------------------
# OfferEventType
# ---------------------------------------------------------------------------


class TestOfferEventType:
    def test_values(self) -> None:
        assert OfferEventType.CREATED == "created"
        assert OfferEventType.UPDATED == "updated"
        assert OfferEventType.DELETED == "deleted"

    def test_is_strenum(self) -> None:
        assert isinstance(OfferEventType.CREATED, str)
        assert OfferEventType.CREATED.value == "created"

    def test_exported_from_offer_types(self) -> None:
        """OfferEventType is defined in offer_types and re-exported from package."""
        from aitbc.trading.offer_types import OfferEventType as A
        from aitbc.trading import OfferEventType as B

        assert A is B  # same class object

    def test_exported_from_package_init(self) -> None:
        from aitbc.trading import OfferEventType as Pkg

        assert Pkg is OfferEventType


# ---------------------------------------------------------------------------
# SubscriptionStatus
# ---------------------------------------------------------------------------


class TestSubscriptionStatus:
    def test_values(self) -> None:
        assert SubscriptionStatus.SUBSCRIBED == "subscribed"
        assert SubscriptionStatus.RECONNECTING == "reconnecting"
        assert SubscriptionStatus.POLLING_FALLBACK == "polling_fallback"
        assert SubscriptionStatus.DISCONNECTED == "disconnected"

    def test_is_strenum(self) -> None:
        assert isinstance(SubscriptionStatus.SUBSCRIBED, str)


# ---------------------------------------------------------------------------
# OfferEvent
# ---------------------------------------------------------------------------


class TestOfferEvent:
    def test_created_event_with_offer(self) -> None:
        offer = _sample_offer()
        event = OfferEvent(
            event_type=OfferEventType.CREATED.value,
            offer_id="offer_001",
            chain_id="ait-hub",
            offer=offer,
            timestamp="2026-06-29T12:00:00+00:00",
            source="blockchain-node",
        )
        assert event.event_type == "created"
        assert event.offer is not None
        assert event.offer.offer_id == "offer_001"

    def test_deleted_event_offer_is_none(self) -> None:
        event = OfferEvent(
            event_type=OfferEventType.DELETED.value,
            offer_id="offer_001",
            chain_id="ait-hub",
            offer=None,
        )
        assert event.offer is None
        assert event.timestamp == ""
        assert event.source is None

    def test_to_dict_with_offer(self) -> None:
        offer = _sample_offer()
        event = _sample_event(offer=offer)
        d = event.to_dict()
        assert d["event_type"] == "created"
        assert d["offer_id"] == "offer_001"
        assert d["chain_id"] == "ait-hub"
        assert d["timestamp"] == "2026-06-29T12:00:00+00:00"
        assert d["source"] == "blockchain-node"
        assert isinstance(d["offer"], dict)
        assert d["offer"]["offer_id"] == "offer_001"

    def test_to_dict_deleted_event(self) -> None:
        event = OfferEvent(
            event_type=OfferEventType.DELETED.value,
            offer_id="offer_001",
            chain_id="ait-hub",
        )
        d = event.to_dict()
        assert d["offer"] is None
        assert d["event_type"] == "deleted"

    def test_from_dict_roundtrip_created(self) -> None:
        offer = _sample_offer()
        event = _sample_event(offer=offer)
        restored = OfferEvent.from_dict(event.to_dict())
        assert restored.event_type == event.event_type
        assert restored.offer_id == event.offer_id
        assert restored.chain_id == event.chain_id
        assert restored.timestamp == event.timestamp
        assert restored.source == event.source
        assert restored.offer is not None
        assert restored.offer.offer_id == offer.offer_id
        assert restored.offer.price == offer.price

    def test_from_dict_roundtrip_deleted(self) -> None:
        event = OfferEvent(
            event_type=OfferEventType.DELETED.value,
            offer_id="offer_001",
            chain_id="ait-hub",
        )
        restored = OfferEvent.from_dict(event.to_dict())
        assert restored.event_type == "deleted"
        assert restored.offer is None

    def test_from_dict_tolerant_of_missing_fields(self) -> None:
        restored = OfferEvent.from_dict({"event_type": "created"})
        assert restored.event_type == "created"
        assert restored.offer_id == ""
        assert restored.chain_id == ""
        assert restored.offer is None
        assert restored.timestamp == ""
        assert restored.source is None

    def test_from_dict_offer_none_explicit(self) -> None:
        restored = OfferEvent.from_dict(
            {
                "event_type": "deleted",
                "offer_id": "o1",
                "chain_id": "c1",
                "offer": None,
            }
        )
        assert restored.offer is None

    def test_from_dict_offer_not_dict(self) -> None:
        """Non-dict offer payload is treated as None (defensive)."""
        restored = OfferEvent.from_dict(
            {
                "event_type": "created",
                "offer_id": "o1",
                "chain_id": "c1",
                "offer": "not-a-dict",
            }
        )
        assert restored.offer is None


# ---------------------------------------------------------------------------
# OfferSubscription
# ---------------------------------------------------------------------------


class TestOfferSubscription:
    def test_defaults(self) -> None:
        sub = OfferSubscription()
        assert sub.chain_id is None
        assert sub.service_type is None
        assert sub.min_price is None
        assert sub.max_price is None
        assert sub.region is None
        assert sub.gpu_model is None
        assert sub.debounce_ms == 1000

    def test_matches_no_filters_matches_all(self) -> None:
        sub = OfferSubscription()
        event = _sample_event()
        assert sub.matches(event) is True

    def test_matches_chain_filter(self) -> None:
        sub = OfferSubscription(chain_id="ait-hub")
        assert sub.matches(_sample_event(chain_id="ait-hub")) is True
        assert sub.matches(_sample_event(chain_id="ait-island1")) is False

    def test_matches_service_type(self) -> None:
        sub = OfferSubscription(service_type="gpu_marketplace")
        offer = _sample_offer(service_type="gpu_marketplace")
        assert sub.matches(_sample_event(offer=offer)) is True
        offer2 = _sample_offer(service_type="compute")
        assert sub.matches(_sample_event(offer=offer2)) is False

    def test_matches_min_price(self) -> None:
        sub = OfferSubscription(min_price=1.0)
        assert sub.matches(_sample_event(offer=_sample_offer(price=2.0))) is True
        assert sub.matches(_sample_event(offer=_sample_offer(price=0.5))) is False

    def test_matches_max_price(self) -> None:
        sub = OfferSubscription(max_price=5.0)
        assert sub.matches(_sample_event(offer=_sample_offer(price=4.0))) is True
        assert sub.matches(_sample_event(offer=_sample_offer(price=6.0))) is False

    def test_matches_region_from_attributes(self) -> None:
        sub = OfferSubscription(region="us-east")
        offer = _sample_offer(attributes={"region": "us-east", "gpu_model": "A100"})
        assert sub.matches(_sample_event(offer=offer)) is True
        offer2 = _sample_offer(attributes={"region": "eu-west", "gpu_model": "A100"})
        assert sub.matches(_sample_event(offer=offer2)) is False

    def test_matches_gpu_model_from_attributes(self) -> None:
        sub = OfferSubscription(gpu_model="A100")
        offer = _sample_offer(attributes={"region": "us-east", "gpu_model": "A100"})
        assert sub.matches(_sample_event(offer=offer)) is True
        offer2 = _sample_offer(attributes={"region": "us-east", "gpu_model": "H100"})
        assert sub.matches(_sample_event(offer=offer2)) is False

    def test_matches_deleted_event_chain_only(self) -> None:
        """Deleted events carry no offer — only chain filter applies."""
        sub = OfferSubscription(chain_id="ait-hub", service_type="gpu_marketplace", min_price=1.0)
        deleted = OfferEvent(
            event_type=OfferEventType.DELETED.value,
            offer_id="o1",
            chain_id="ait-hub",
            offer=None,
        )
        # Chain matches → deleted event matches regardless of other filters.
        assert sub.matches(deleted) is True
        deleted_other_chain = OfferEvent(
            event_type=OfferEventType.DELETED.value,
            offer_id="o1",
            chain_id="ait-island1",
            offer=None,
        )
        assert sub.matches(deleted_other_chain) is False

    def test_matches_region_missing_attribute(self) -> None:
        """Offer without region attribute does not match a region filter."""
        sub = OfferSubscription(region="us-east")
        offer = _sample_offer(attributes={"gpu_model": "A100"})  # no region
        assert sub.matches(_sample_event(offer=offer)) is False

    def test_to_filters_dict_includes_only_set_filters(self) -> None:
        sub = OfferSubscription(chain_id="ait-hub", min_price=1.0)
        filters = sub.to_filters_dict()
        assert filters == {"chain_id": "ait-hub", "min_price": 1.0}

    def test_to_filters_dict_empty_when_no_filters(self) -> None:
        sub = OfferSubscription()
        assert sub.to_filters_dict() == {}


# ---------------------------------------------------------------------------
# OfferNotification
# ---------------------------------------------------------------------------


class TestOfferNotification:
    def test_build_sets_batch_size_and_timestamp(self) -> None:
        events = [_sample_event(offer_id="o1"), _sample_event(offer_id="o2")]
        notif = OfferNotification.build(events, chain_id="ait-hub")
        assert notif.batch_size == 2
        assert notif.chain_id == "ait-hub"
        assert notif.timestamp != ""  # ISO timestamp set
        assert len(notif.events) == 2

    def test_build_empty(self) -> None:
        notif = OfferNotification.build([], chain_id="ait-hub")
        assert notif.batch_size == 0
        assert notif.events == []

    def test_build_copies_events_list(self) -> None:
        events = [_sample_event(offer_id="o1")]
        notif = OfferNotification.build(events)
        events.append(_sample_event(offer_id="o2"))
        assert len(notif.events) == 1  # not affected by external mutation

    def test_to_dict(self) -> None:
        notif = OfferNotification.build([_sample_event(offer_id="o1")], chain_id="ait-hub")
        d = notif.to_dict()
        assert d["chain_id"] == "ait-hub"
        assert d["batch_size"] == 1
        assert isinstance(d["events"], list)
        assert d["events"][0]["offer_id"] == "o1"

    def test_default_fields(self) -> None:
        notif = OfferNotification()
        assert notif.events == []
        assert notif.chain_id == ""
        assert notif.batch_size == 0
        assert notif.timestamp == ""


# ---------------------------------------------------------------------------
# OfferSubscriptionClient
# ---------------------------------------------------------------------------


class TestOfferSubscriptionClientInit:
    def test_defaults(self) -> None:
        client = OfferSubscriptionClient()
        assert client.rpc_url == "http://localhost:8104"
        assert client.node_id == "trading-client"
        assert client.get_subscription_status() == {}

    def test_custom_url(self) -> None:
        client = OfferSubscriptionClient(rpc_url="http://trading.example:9000/", node_id="node-1")
        assert client.rpc_url == "http://trading.example:9000"
        assert client.node_id == "node-1"

    def test_ws_url_derived_from_http(self) -> None:
        client = OfferSubscriptionClient(rpc_url="http://localhost:8104")
        assert client._ws_url == "ws://localhost:8104"
        client2 = OfferSubscriptionClient(rpc_url="https://trading.example")
        assert client2._ws_url == "wss://trading.example"

    def test_get_lease_remaining_no_lease(self) -> None:
        client = OfferSubscriptionClient()
        assert client.get_lease_remaining("ait-hub") == 0


class TestOfferSubscriptionClientLease:
    @pytest.mark.asyncio
    async def test_register_lease_success(self) -> None:
        client = OfferSubscriptionClient()
        mock_resp = _mock_response(json_data={"expiry": 9999999999.0, "lease_duration": 3600})
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            ok = await client._register_lease("ait-hub", {"chain_id": "ait-hub"})
        assert ok is True
        assert client.get_lease_remaining("ait-hub") > 0
        await client.close()

    @pytest.mark.asyncio
    async def test_register_lease_failure(self) -> None:
        client = OfferSubscriptionClient()
        mock_resp = _mock_response(status_code=500)
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            ok = await client._register_lease("ait-hub", {})
        assert ok is False
        assert client.get_lease_remaining("ait-hub") == 0
        await client.close()

    @pytest.mark.asyncio
    async def test_renew_lease_success(self) -> None:
        client = OfferSubscriptionClient()
        mock_resp = _mock_response(json_data={"expiry": 9999999999.0})
        with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
            ok = await client._renew_lease("ait-hub")
        assert ok is True
        await client.close()


class TestOfferSubscriptionClientParseMessage:
    def test_parse_json_string(self) -> None:
        client = OfferSubscriptionClient()
        msg = json.dumps(
            {
                "event_type": "created",
                "offer_id": "o1",
                "chain_id": "ait-hub",
                "offer": _sample_offer().to_dict(),
            }
        )
        event = client._parse_message(msg)
        assert event is not None
        assert event.event_type == "created"
        assert event.offer is not None

    def test_parse_dict(self) -> None:
        client = OfferSubscriptionClient()
        event = client._parse_message(
            {
                "event_type": "deleted",
                "offer_id": "o1",
                "chain_id": "ait-hub",
            }
        )
        assert event is not None
        assert event.event_type == "deleted"
        assert event.offer is None

    def test_parse_bytes(self) -> None:
        client = OfferSubscriptionClient()
        msg = json.dumps({"event_type": "updated", "offer_id": "o1", "chain_id": "c"}).encode()
        event = client._parse_message(msg)
        assert event is not None
        assert event.event_type == "updated"

    def test_parse_invalid_json_returns_none(self) -> None:
        client = OfferSubscriptionClient()
        assert client._parse_message("not json") is None

    def test_parse_non_dict_returns_none(self) -> None:
        client = OfferSubscriptionClient()
        assert client._parse_message(json.dumps([1, 2, 3])) is None

    def test_parse_missing_event_type_returns_none(self) -> None:
        client = OfferSubscriptionClient()
        assert client._parse_message({"offer_id": "o1"}) is None

    def test_parse_unknown_type_returns_none(self) -> None:
        client = OfferSubscriptionClient()
        assert client._parse_message(12345) is None


class TestOfferSubscriptionClientUnsubscribe:
    def test_unsubscribe_sets_disconnected(self) -> None:
        client = OfferSubscriptionClient()
        client._subscriptions["ait-hub"] = OfferSubscription(chain_id="ait-hub")
        client._status["ait-hub"] = SubscriptionStatus.SUBSCRIBED
        client.unsubscribe("ait-hub")
        assert "ait-hub" not in client._subscriptions
        assert client._status["ait-hub"] == SubscriptionStatus.DISCONNECTED

    def test_unsubscribe_unknown_chain_no_error(self) -> None:
        client = OfferSubscriptionClient()
        client.unsubscribe("nonexistent")  # should not raise


class TestOfferSubscriptionClientClose:
    @pytest.mark.asyncio
    async def test_close_sets_disconnected_and_closes_http(self) -> None:
        client = OfferSubscriptionClient()
        client._subscriptions["ait-hub"] = OfferSubscription(chain_id="ait-hub")
        client._status["ait-hub"] = SubscriptionStatus.SUBSCRIBED
        # Force creation of the http client.
        client._ensure_http()
        await client.close()
        assert client._running is False
        assert client._subscriptions == {}
        assert client._status["ait-hub"] == SubscriptionStatus.DISCONNECTED
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_close_without_http_client(self) -> None:
        client = OfferSubscriptionClient()
        await client.close()  # no http client created — should not raise
        assert client._http_client is None


class TestOfferSubscriptionClientPollingFallback:
    """The polling fallback uses OfferSyncClient.discover_offers.

    We mock OfferSyncClient to avoid real HTTP and verify the client
    emits CREATED / UPDATED / DELETED events correctly.
    """

    @pytest.mark.asyncio
    async def test_polling_emits_created_then_updated_then_deleted(self) -> None:
        client = OfferSubscriptionClient(reconnect_delay_seconds=0.01, poll_interval_seconds=0.01)
        sub = OfferSubscription(chain_id="ait-hub")

        offer_v1 = _sample_offer(offer_id="o1", chain_id="ait-hub", price=1.0, status="available")
        offer_v2 = _sample_offer(offer_id="o1", chain_id="ait-hub", price=2.0, status="reserved")
        offer_v3 = _sample_offer(offer_id="o2", chain_id="ait-hub", price=3.0)

        # Three poll cycles: [o1], [o1 updated, o2 new], [o2 only → o1 deleted]
        results = [
            MagicMock(offers=[offer_v1]),
            MagicMock(offers=[offer_v2, offer_v3]),
            MagicMock(offers=[offer_v3]),
        ]
        mock_poll_client = MagicMock()
        mock_poll_client.discover_offers = AsyncMock(side_effect=results)
        mock_poll_client.close = AsyncMock()

        with patch(
            "aitbc.trading.subscription_client.OfferSyncClient",
            return_value=mock_poll_client,
        ):
            client._running = True
            client._subscriptions["ait-hub"] = sub
            events: list[OfferEvent] = []
            gen = client._polling_fallback("ait-hub", sub)

            # Consume exactly 4 events (1 created + 1 updated + 1 created + 1 deleted).
            for _ in range(4):
                event = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
                events.append(event)

        # Stop the generator.
        client._running = False
        await client.close()

        # Event 0: o1 created
        assert events[0].event_type == "created"
        assert events[0].offer_id == "o1"
        # Event 1: o1 updated (price/status changed)
        assert events[1].event_type == "updated"
        assert events[1].offer_id == "o1"
        # Event 2: o2 created
        assert events[2].event_type == "created"
        assert events[2].offer_id == "o2"
        # Event 3: o1 deleted (absent in cycle 3)
        assert events[3].event_type == "deleted"
        assert events[3].offer_id == "o1"
        assert events[3].offer is None

    @pytest.mark.asyncio
    async def test_polling_filters_by_chain(self) -> None:
        """Polling fallback only emits events for the subscribed chain."""
        client = OfferSubscriptionClient(poll_interval_seconds=0.01)
        sub = OfferSubscription(chain_id="ait-hub")

        # Mix of chains in the result — only ait-hub should be emitted.
        offer_hub = _sample_offer(offer_id="o1", chain_id="ait-hub")
        offer_island = _sample_offer(offer_id="o2", chain_id="ait-island1")
        result = MagicMock(offers=[offer_hub, offer_island])
        mock_poll_client = MagicMock()
        mock_poll_client.discover_offers = AsyncMock(return_value=result)
        mock_poll_client.close = AsyncMock()

        with patch(
            "aitbc.trading.subscription_client.OfferSyncClient",
            return_value=mock_poll_client,
        ):
            client._running = True
            client._subscriptions["ait-hub"] = sub
            gen = client._polling_fallback("ait-hub", sub)
            event = await asyncio.wait_for(gen.__anext__(), timeout=5.0)

        client._running = False
        await client.close()

        assert event.chain_id == "ait-hub"
        assert event.offer_id == "o1"
