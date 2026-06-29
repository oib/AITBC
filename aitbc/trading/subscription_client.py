r"""Offer subscription WebSocket client (v0.8.2 §A2).

Async WebSocket client for real-time offer change streaming from the
trading service. Follows the same reconnection and lease pattern as
``apps/blockchain-node/src/aitbc_chain/subscription_client.py`` but is
blockchain-agnostic — it yields ``OfferEvent``\ s to the caller rather
than importing blocks.

Lifecycle per chain:
    SUBSCRIBED → RECONNECTING (on disconnect) → SUBSCRIBED (reconnect)
               → POLLING_FALLBACK (max reconnect attempts exceeded)

Reconnection:
    - WebSocket disconnect → retry after ``reconnect_delay_seconds`` (default 5s)
    - Other errors → fall back to polling (v0.8.1 ``OfferSyncClient``)
      after ``max_reconnect_attempts`` (default 3)

The client is async-iterator based: ``async for event in client.subscribe(...)``.
This keeps the consumer simple and lets the client own reconnection
internally without surfacing it to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from .offer_types import OfferEventType
from .offer_client import OfferSyncClient
from .offer_types import OfferDiscoveryRequest, SyncedOffer
from .subscription_types import (
    OfferEvent,
    OfferSubscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


class OfferSubscriptionClient:
    """WebSocket client for real-time offer change streaming.

    Wraps the trading service offer subscription endpoints:
    - ``POST /v1/trading/offers/subscribe`` — register, get lease
    - ``POST /v1/trading/offers/heartbeat`` — extend lease
    - ``WS  /v1/trading/offers/subscribe/ws`` — stream offer events

    The client mirrors the lease-based auth pattern from
    ``apps/blockchain-node/src/aitbc_chain/subscription_client.py``:
    an initial HTTP POST obtains a lease, then a WebSocket connection
    streams events. On disconnect the client reconnects automatically;
    after ``max_reconnect_attempts`` failures it falls back to polling
    via ``OfferSyncClient`` (v0.8.1).
    """

    def __init__(
        self,
        rpc_url: str = "http://localhost:8104",
        node_id: str = "trading-client",
        reconnect_delay_seconds: float = 5.0,
        max_reconnect_attempts: int = 3,
        heartbeat_interval_seconds: float = 60.0,
        lease_renewal_threshold_seconds: float = 300.0,
        http_timeout: float = 30.0,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        # WebSocket URL derived from the HTTP base URL.
        self._ws_url = self._rpc_url.replace("http://", "ws://").replace("https://", "wss://")
        self._node_id = node_id
        self._reconnect_delay = reconnect_delay_seconds
        self._max_reconnect_attempts = max_reconnect_attempts
        self._heartbeat_interval = heartbeat_interval_seconds
        self._lease_renewal_threshold = lease_renewal_threshold_seconds
        self._http_timeout = http_timeout
        self._poll_interval = poll_interval_seconds
        self._http_client: httpx.AsyncClient | None = None
        # Per-chain lease expiry timestamps (epoch seconds).
        self._lease_expiry: dict[str, float] = {}
        # Per-chain subscription status.
        self._status: dict[str, SubscriptionStatus] = {}
        # Active subscriptions: chain_id -> OfferSubscription filter.
        self._subscriptions: dict[str, OfferSubscription] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Properties / introspection
    # ------------------------------------------------------------------

    @property
    def rpc_url(self) -> str:
        """The base HTTP URL for the trading service."""
        return self._rpc_url

    @property
    def node_id(self) -> str:
        """The node ID used for lease registration."""
        return self._node_id

    def get_subscription_status(self) -> dict[str, str]:
        """Get per-chain subscription status as string values.

        Returns a mapping of ``chain_id`` → ``SubscriptionStatus`` value
        for every chain with an active or recent subscription.
        """
        return {cid: status.value for cid, status in self._status.items()}

    def get_lease_remaining(self, chain_id: str) -> int:
        """Get remaining lease time in seconds for a chain."""
        return int(max(0.0, self._lease_expiry.get(chain_id, 0.0) - time.time()))

    # ------------------------------------------------------------------
    # HTTP lease management
    # ------------------------------------------------------------------

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._rpc_url,
                timeout=self._http_timeout,
            )
        return self._http_client

    async def _register_lease(self, chain_id: str, filters: dict[str, Any]) -> bool:
        """Register a subscription and obtain a lease from the trading service.

        Mirrors ``POST /rpc/subscribe`` in the blockchain-node pattern.
        Returns True on success, False on failure.
        """
        payload: dict[str, Any] = {
            "node_id": self._node_id,
            "chain_id": chain_id,
            "transport": "websocket",
        }
        if filters:
            payload["filters"] = filters
        try:
            resp = await self._ensure_http().post("/v1/trading/offers/subscribe", json=payload)
            resp.raise_for_status()
            data = resp.json()
            self._lease_expiry[chain_id] = float(data.get("expiry", 0.0))
            logger.info(
                "Obtained offer subscription lease for chain %s (expiry=%s)",
                chain_id,
                self._lease_expiry[chain_id],
            )
            return True
        except Exception as e:
            logger.warning("Failed to obtain offer subscription lease for %s: %s", chain_id, e)
            return False

    async def _renew_lease(self, chain_id: str) -> bool:
        """Renew the lease for a chain via heartbeat.

        Mirrors ``POST /rpc/heartbeat`` in the blockchain-node pattern.
        """
        try:
            resp = await self._ensure_http().post(
                "/v1/trading/offers/heartbeat",
                json={"node_id": self._node_id, "chain_id": chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
            self._lease_expiry[chain_id] = float(data.get("expiry", 0.0))
            return True
        except Exception as e:
            logger.warning("Failed to renew offer subscription lease for %s: %s", chain_id, e)
            return False

    async def _heartbeat_loop(self, chain_id: str) -> None:
        """Background loop that renews the lease before it expires."""
        while self._running and chain_id in self._subscriptions:
            remaining = self.get_lease_remaining(chain_id)
            if remaining < self._lease_renewal_threshold:
                await self._renew_lease(chain_id)
            await asyncio.sleep(self._heartbeat_interval)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        chain_id: str,
        subscription: OfferSubscription | None = None,
    ) -> AsyncIterator[OfferEvent]:
        r"""Subscribe to offer change events for a chain.

        Yields ``OfferEvent``\ s as they arrive over the WebSocket. The
        call blocks (cooperatively) until the consumer breaks out of the
        loop or ``close()`` is called. On disconnect the client
        reconnects automatically; after ``max_reconnect_attempts``
        failures it falls back to polling via ``OfferSyncClient`` and
        continues yielding events.

        Args:
            chain_id: The chain to subscribe to.
            subscription: Optional filter set. If omitted, a subscription
                scoped to ``chain_id`` with no other filters is used.
        """
        sub = subscription or OfferSubscription(chain_id=chain_id)
        self._subscriptions[chain_id] = sub
        self._status[chain_id] = SubscriptionStatus.SUBSCRIBED
        self._running = True

        filters = sub.to_filters_dict()
        # Always include chain_id in the first message (defense-in-depth,
        # matching how block messages redundantly include chain_id).
        filters["chain_id"] = chain_id

        obtained_lease = await self._register_lease(chain_id, filters)
        if not obtained_lease:
            # No lease — go straight to polling fallback if enabled.
            self._status[chain_id] = SubscriptionStatus.POLLING_FALLBACK

        # Start lease renewal in the background.
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(chain_id))
        try:
            if self._status[chain_id] == SubscriptionStatus.SUBSCRIBED:
                async for event in self._ws_stream(chain_id, filters):
                    yield event
            else:
                # Polling fallback path.
                async for event in self._polling_fallback(chain_id, sub):
                    yield event
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            self._status[chain_id] = SubscriptionStatus.DISCONNECTED

    async def _ws_stream(self, chain_id: str, filters: dict[str, Any]) -> AsyncIterator[OfferEvent]:
        """Yield events from the WebSocket, reconnecting on disconnect."""
        ws_url = f"{self._ws_url}/v1/trading/offers/subscribe/ws"
        first_message = json.dumps(
            {
                "node_id": self._node_id,
                "chain_id": chain_id,
                "transport": "websocket",
                "filters": filters,
            }
        )
        reconnect_attempts = 0
        while self._running and chain_id in self._subscriptions:
            try:
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                ) as websocket:
                    await websocket.send(first_message)
                    self._status[chain_id] = SubscriptionStatus.SUBSCRIBED
                    reconnect_attempts = 0
                    logger.info("Offer subscription WebSocket connected for chain %s", chain_id)
                    async for raw in websocket:
                        event = self._parse_message(raw)
                        if event is not None:
                            yield event
            except ConnectionClosed:
                logger.warning(
                    "Offer subscription WebSocket closed for chain %s, reconnecting",
                    chain_id,
                )
                self._status[chain_id] = SubscriptionStatus.RECONNECTING
                reconnect_attempts += 1
                if reconnect_attempts > self._max_reconnect_attempts:
                    logger.warning(
                        "Offer subscription for chain %s exceeded max reconnect attempts, falling back to polling",
                        chain_id,
                    )
                    self._status[chain_id] = SubscriptionStatus.POLLING_FALLBACK
                    async for event in self._polling_fallback(chain_id, self._subscriptions[chain_id]):
                        yield event
                    return
                await asyncio.sleep(self._reconnect_delay)
            except Exception as e:
                logger.warning(
                    "Offer subscription WebSocket error for chain %s: %s, falling back to polling",
                    chain_id,
                    e,
                )
                self._status[chain_id] = SubscriptionStatus.POLLING_FALLBACK
                async for event in self._polling_fallback(chain_id, self._subscriptions[chain_id]):
                    yield event
                return

    async def _polling_fallback(self, chain_id: str, sub: OfferSubscription) -> AsyncIterator[OfferEvent]:
        r"""Fall back to v0.8.1 polling-based sync.

        Periodically polls the trading service offer cache and emits
        ``OfferEvent``\ s for offers that changed since the last poll.
        This is the safety net when the WebSocket subscription is
        unavailable — it mirrors the push→pull fallback in
        ``subscription_client.py:262-276``.
        """
        logger.info("Offer subscription for chain %s using polling fallback", chain_id)
        poll_client = OfferSyncClient(self._rpc_url, timeout=int(self._http_timeout))
        seen_offer_ids: set[str] = set()
        last_seen: dict[str, SyncedOffer] = {}
        poll_interval = max(self._poll_interval, sub.debounce_ms / 1000.0)
        try:
            while self._running and chain_id in self._subscriptions:
                try:
                    request = OfferDiscoveryRequest(
                        source_chain=chain_id,
                        service_type=sub.service_type,
                        min_price=sub.min_price,
                        max_price=sub.max_price,
                        region=sub.region,
                        gpu_model=sub.gpu_model,
                        limit=500,
                    )
                    result = await poll_client.discover_offers(request)
                    current_ids: set[str] = set()
                    for offer in result.offers:
                        if offer.chain_id != chain_id:
                            continue
                        current_ids.add(offer.offer_id)
                        prev = last_seen.get(offer.offer_id)
                        if prev is None:
                            yield OfferEvent(
                                event_type=OfferEventType.CREATED.value,
                                offer_id=offer.offer_id,
                                chain_id=offer.chain_id,
                                offer=offer,
                                source="polling-fallback",
                            )
                        elif prev.status != offer.status or prev.price != offer.price or prev.quantity != offer.quantity:
                            yield OfferEvent(
                                event_type=OfferEventType.UPDATED.value,
                                offer_id=offer.offer_id,
                                chain_id=offer.chain_id,
                                offer=offer,
                                source="polling-fallback",
                            )
                        last_seen[offer.offer_id] = offer
                    # Detect deleted offers.
                    for deleted_id in seen_offer_ids - current_ids:
                        yield OfferEvent(
                            event_type=OfferEventType.DELETED.value,
                            offer_id=deleted_id,
                            chain_id=chain_id,
                            offer=None,
                            source="polling-fallback",
                        )
                        last_seen.pop(deleted_id, None)
                    seen_offer_ids = current_ids
                except Exception as e:
                    logger.warning("Polling fallback error for chain %s: %s", chain_id, e)
                await asyncio.sleep(poll_interval)
        finally:
            await poll_client.close()

    def _parse_message(self, raw: Any) -> OfferEvent | None:
        """Parse a raw WebSocket message into an OfferEvent.

        Tolerates str (JSON), bytes (JSON), or dict payloads. Returns
        None for malformed messages (logged at debug level).
        """
        data: Any
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON WebSocket message: %r", raw[:80])
                return None
        elif isinstance(raw, bytes):
            try:
                data = json.loads(raw.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.debug("Skipping non-JSON WebSocket message: %r", raw[:80])
                return None
        elif isinstance(raw, dict):
            data = raw
        else:
            logger.debug("Skipping unknown WebSocket message type: %s", type(raw).__name__)
            return None
        if not isinstance(data, dict):
            return None
        if "event_type" not in data:
            logger.debug("Skipping WebSocket message without event_type: %s", list(data.keys()))
            return None
        return OfferEvent.from_dict(data)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def unsubscribe(self, chain_id: str) -> None:
        """Stop subscribing to a chain.

        The active ``subscribe()`` generator will exit on its next
        iteration. Does not block — the running generator winds down
        asynchronously.
        """
        self._subscriptions.pop(chain_id, None)
        self._status[chain_id] = SubscriptionStatus.DISCONNECTED

    async def close(self) -> None:
        """Close the client and release all resources."""
        self._running = False
        self._subscriptions.clear()
        for cid in list(self._status):
            self._status[cid] = SubscriptionStatus.DISCONNECTED
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
