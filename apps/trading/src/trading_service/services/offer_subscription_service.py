"""Offer subscription service for real-time offer sync (v0.8.2 §B3).

Subscribes to gossip topics ``offers.{chain_id}`` for each registered chain,
processes incoming ``OfferEvent`` messages, updates the OfferCache, and
forwards events to WebSocket subscribers via the notification service.

The service maintains per-chain subscription health tracking and supports
fallback to polling (v0.8.1 OfferSyncService) when gossip is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import OfferEventType
from aitbc.trading.subscription_types import OfferEvent, SubscriptionStatus

from ..config import settings

logger = logging.getLogger(__name__)


class OfferSubscriptionService:
    """Manages real-time offer subscriptions via gossip and WebSocket.

    Subscribes to ``offers.{chain_id}`` gossip topics for each registered
    chain, processes events, updates the OfferCache, and forwards matching
    events to WebSocket subscribers via a notification callback.
    """

    def __init__(
        self,
        cache: OfferCache | None = None,
        on_event_callback: Any | None = None,
    ) -> None:
        self._cache = cache or OfferCache()
        self._on_event = on_event_callback
        self._subscription_tasks: dict[str, asyncio.Task[None]] = {}
        self._chain_status: dict[str, SubscriptionStatus] = {}
        self._chain_stats: dict[str, dict[str, Any]] = {}
        self._running = False
        self._gossip_subscriptions: dict[str, Any] = {}

    @property
    def cache(self) -> OfferCache:
        return self._cache

    @property
    def running(self) -> bool:
        return self._running

    def get_chain_status(self) -> list[dict[str, Any]]:
        """Get subscription status for all chains."""
        results: list[dict[str, Any]] = []
        for chain_id, status in self._chain_status.items():
            stats = self._chain_stats.get(chain_id, {})
            results.append(
                {
                    "chain_id": chain_id,
                    "status": status.value,
                    "last_event": stats.get("last_event", ""),
                    "event_count": stats.get("event_count", 0),
                }
            )
        return results

    async def start_chain(self, chain_id: str) -> None:
        """Start subscribing to offer events for a single chain."""
        if chain_id in self._subscription_tasks:
            return
        self._running = True
        self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
        self._chain_stats[chain_id] = {"last_event": "", "event_count": 0}
        task = asyncio.create_task(self._subscribe_loop(chain_id), name=f"offer-sub-{chain_id}")
        self._subscription_tasks[chain_id] = task
        logger.info("Started offer subscription for chain %s", chain_id)

    async def stop_chain(self, chain_id: str) -> None:
        """Stop subscribing to a chain."""
        task = self._subscription_tasks.pop(chain_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._chain_status[chain_id] = SubscriptionStatus.DISCONNECTED
        logger.info("Stopped offer subscription for chain %s", chain_id)

    async def stop_all(self) -> None:
        """Stop all subscription tasks."""
        self._running = False
        for chain_id in list(self._subscription_tasks):
            await self.stop_chain(chain_id)

    async def _subscribe_loop(self, chain_id: str) -> None:
        """Subscribe to gossip topic and process events.

        Uses an in-memory asyncio.Queue to simulate gossip subscription
        when a real gossip broker is not available. In production, this
        would use ``GossipBroker.subscribe(f"offers.{chain_id}")``.
        """
        queue: asyncio.Queue[OfferEvent] = asyncio.Queue(maxsize=100)

        self._gossip_subscriptions[chain_id] = queue
        self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED

        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                    await self._handle_event(event)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Subscription loop error for chain %s: %s", chain_id, e)
            self._chain_status[chain_id] = SubscriptionStatus.RECONNECTING
        finally:
            self._gossip_subscriptions.pop(chain_id, None)

    async def _handle_event(self, event: OfferEvent) -> None:
        """Process an offer event: update cache, notify subscribers."""
        stats = self._chain_stats.setdefault(event.chain_id, {"last_event": "", "event_count": 0})
        stats["last_event"] = datetime.now(UTC).isoformat()
        stats["event_count"] = stats.get("event_count", 0) + 1

        if event.event_type == OfferEventType.DELETED.value:
            self._cache.delete_offer(event.offer_id, event.chain_id)
            logger.debug("Deleted offer %s from cache (chain %s)", event.offer_id, event.chain_id)
        elif event.offer is not None:
            self._cache.set_offer(event.offer, ttl=settings.offer_cache_ttl_seconds)
            logger.debug("Updated offer %s in cache (chain %s, event=%s)", event.offer_id, event.chain_id, event.event_type)

        if self._on_event is not None:
            try:
                result = self._on_event(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("Event callback error: %s", e)

    def publish_event(self, event: OfferEvent) -> None:
        """Publish an offer event to the in-memory queue for a chain.

        This is used by tests and by the gossip integration layer to
        inject events into the subscription pipeline without a real
        gossip broker.
        """
        queue = self._gossip_subscriptions.get(event.chain_id)
        if queue is not None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Offer event queue full for chain %s, dropping event", event.chain_id)

    async def inject_event(self, event: OfferEvent) -> None:
        """Async inject an event directly into the handler (bypass queue).

        Used by tests and by the WebSocket endpoint to process events
        without going through the gossip subscription loop.
        """
        await self._handle_event(event)
