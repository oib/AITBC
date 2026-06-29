r"""Offer subscription types for real-time offer sync (v0.8.2 §A1).

Defines the canonical types for subscription-based offer synchronization
across AITBC chains. These types extend the v0.8.1 polling-based offer
sync with WebSocket streaming, gossip-published change events, and
debounced batch notifications.

The event schema is aligned with the agent-coordinator event pattern
(``apps/agent-coordinator/src/app/routing/agent_discovery.py:370-375``)
and the generic ``aitbc.events.Event`` dataclass
(``aitbc/events/events.py:30-42``) — see Design Decision 1 in the
v0.8.2 release plan for rationale.

Consumers:
- ``OfferSubscriptionClient`` (this package, §A2) — WebSocket client
- ``apps/trading/`` offer subscription service (Agent B B3)
- ``cli/aitbc_cli/commands/trade.py`` ``trade watch`` command (Agent B B6)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .offer_types import SyncedOffer


class SubscriptionStatus(StrEnum):
    """Status of a WebSocket offer subscription per chain.

    Lifecycle: ``SUBSCRIBED`` → ``RECONNECTING`` (on disconnect) →
    ``SUBSCRIBED`` (reconnect success) | ``POLLING_FALLBACK`` (reconnect
    failure after max attempts) → ``DISCONNECTED`` (explicit close).
    """

    SUBSCRIBED = "subscribed"
    RECONNECTING = "reconnecting"
    POLLING_FALLBACK = "polling_fallback"
    DISCONNECTED = "disconnected"


@dataclass
class OfferEvent:
    """An offer change event from a chain.

    Schema aligned with the agent-coordinator event pattern
    (``agent_discovery.py:370-375``) and ``aitbc.events.Event``
    (``events.py:30-42``). See Design Decision 1 for rationale.

    The ``offer`` field is ``None`` for ``DELETED`` events (only
    ``offer_id`` + ``chain_id`` are needed to invalidate the cache).
    For ``CREATED`` / ``UPDATED`` it carries the full ``SyncedOffer``
    so consumers can update their cache in one step.
    """

    event_type: str  # OfferEventType value
    offer_id: str
    chain_id: str
    offer: SyncedOffer | None = None  # None for deleted events
    timestamp: str = ""  # ISO 8601 timestamp
    source: str | None = None  # "blockchain-node" | "trading-service" | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for gossip transport / WebSocket.

        Embeds the full ``SyncedOffer`` (via ``to_dict``) when present,
        matching how ``SyncedOffer`` is already serialized in
        ``offer_cache.py:65-74`` and ``offer_types.py:64-116``.
        """
        result: dict[str, Any] = {
            "event_type": self.event_type,
            "offer_id": self.offer_id,
            "chain_id": self.chain_id,
            "timestamp": self.timestamp,
            "source": self.source,
        }
        if self.offer is not None:
            result["offer"] = self.offer.to_dict()
        else:
            result["offer"] = None
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OfferEvent:
        """Deserialize from gossip transport / WebSocket message.

        Tolerant of missing fields — defaults match dataclass defaults so
        a partially-populated gossip message still deserializes.
        """
        offer_data = data.get("offer")
        offer = SyncedOffer.from_dict(offer_data) if isinstance(offer_data, dict) else None
        return cls(
            event_type=data.get("event_type", ""),
            offer_id=data.get("offer_id", ""),
            chain_id=data.get("chain_id", ""),
            offer=offer,
            timestamp=data.get("timestamp", ""),
            source=data.get("source"),
        )


@dataclass
class OfferSubscription:
    r"""Configuration for an offer subscription (saved query).

    A WebSocket client sends a subscription request with these filters.
    The trading service matches incoming ``OfferEvent``\ s against the
    subscription and pushes matching events (debounced into batches via
    ``OfferNotification``) back to the client.

    ``chain_id=None`` means "all chains". Other ``None`` filters mean
    "no filter on this dimension".
    """

    chain_id: str | None = None  # None = all chains
    service_type: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    region: str | None = None
    gpu_model: str | None = None
    debounce_ms: int = 1000  # batch notifications within this window

    def matches(self, event: OfferEvent) -> bool:
        """Check if an event matches this subscription filter.

        ``DELETED`` events match on ``chain_id`` only (the offer payload
        is absent, so service/price/region/gpu filters cannot apply).
        For ``CREATED`` / ``UPDATED`` events the full ``SyncedOffer`` is
        checked against every non-None filter.
        """
        # Chain filter applies to all event types.
        if self.chain_id is not None and event.chain_id != self.chain_id:
            return False
        # Deleted events carry no offer payload — only chain filter applies.
        if event.offer is None:
            return True
        offer = event.offer
        if self.service_type is not None and offer.service_type != self.service_type:
            return False
        if self.min_price is not None and offer.price < self.min_price:
            return False
        if self.max_price is not None and offer.price > self.max_price:
            return False
        if self.region is not None:
            offer_region = offer.attributes.get("region")
            if offer_region != self.region:
                return False
        if self.gpu_model is not None:
            offer_gpu = offer.attributes.get("gpu_model")
            if offer_gpu != self.gpu_model:
                return False
        return True

    def to_filters_dict(self) -> dict[str, Any]:
        """Serialize the filter set for the WebSocket first message.

        Only non-None filters are included so the server can distinguish
        "no filter" from "filter set to default".
        """
        filters: dict[str, Any] = {}
        if self.chain_id is not None:
            filters["chain_id"] = self.chain_id
        if self.service_type is not None:
            filters["service_type"] = self.service_type
        if self.min_price is not None:
            filters["min_price"] = self.min_price
        if self.max_price is not None:
            filters["max_price"] = self.max_price
        if self.region is not None:
            filters["region"] = self.region
        if self.gpu_model is not None:
            filters["gpu_model"] = self.gpu_model
        return filters


@dataclass
class OfferNotification:
    r"""A debounced batch notification of offer changes.

    The notification service (Agent B B4) collects ``OfferEvent``\ s
    matching a subscription within the ``debounce_ms`` window, then
    emits a single ``OfferNotification`` to the WebSocket subscriber.
    This reduces message rate during bursty offer activity (e.g. a
    chain restart that touches many offers at once).
    """

    events: list[OfferEvent] = field(default_factory=list)
    chain_id: str = ""
    batch_size: int = 0
    timestamp: str = ""  # ISO timestamp

    @classmethod
    def build(cls, events: list[OfferEvent], chain_id: str = "") -> OfferNotification:
        """Build a notification from a list of events.

        ``timestamp`` is set to now (UTC, ISO 8601) and ``batch_size``
        is derived from ``events`` length.
        """
        return cls(
            events=list(events),
            chain_id=chain_id,
            batch_size=len(events),
            timestamp=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for WebSocket transport."""
        return {
            "events": [e.to_dict() for e in self.events],
            "chain_id": self.chain_id,
            "batch_size": self.batch_size,
            "timestamp": self.timestamp,
        }
