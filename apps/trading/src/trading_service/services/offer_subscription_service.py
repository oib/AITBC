"""Offer subscription service for real-time offer sync (v0.8.2 §B3, §B18, §B19, §B20).

Subscribes to gossip topics ``offers.{chain_id}`` for each registered chain,
processes incoming ``OfferEvent`` messages, updates the OfferCache, and
forwards events to WebSocket subscribers via the notification service.

v0.10.1 §B18: Replaces the in-memory ``asyncio.Queue`` mock with an actual
Redis pub/sub subscription via :class:`GossipClient`.  Falls back to the
in-memory queue when Redis is unavailable.

v0.10.1 §B19: Integrates :class:`OfferLeaseTracker` for subscription auth.
On subscribe a lease is created in Redis; on heartbeat it is renewed; on
WebSocket receive the lease is validated.

v0.10.1 §B20: Implements automatic fallback to :class:`OfferSyncService`
polling when the gossip subscription disconnects or is silent for
``subscription_silent_threshold_multiplier`` × heartbeat interval.  A
background task periodically attempts to re-establish the gossip
subscription (every 60s) and switches back to subscription mode on
success.  All mode transitions are logged for observability.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from aitbc.trading.offer_cache import OfferCache
from aitbc.trading.offer_types import OfferEventType
from aitbc.trading.subscription_types import OfferEvent, SubscriptionStatus

from ..config import settings
from .gossip_client import GossipClient
from .lease_tracker import OfferLeaseTracker

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
        gossip_client: GossipClient | None = None,
        lease_tracker: OfferLeaseTracker | None = None,
        offer_sync_factory: Any | None = None,
    ) -> None:
        self._cache = cache or OfferCache()
        self._on_event = on_event_callback
        self._subscription_tasks: dict[str, asyncio.Task[None]] = {}
        self._chain_status: dict[str, SubscriptionStatus] = {}
        self._chain_stats: dict[str, dict[str, Any]] = {}
        self._running = False
        self._gossip_subscriptions: dict[str, Any] = {}
        # B18: Gossip client (lazily created if not provided)
        self._gossip_client = gossip_client
        # B19: Lease tracker (lazily created if not provided)
        self._lease_tracker = lease_tracker
        # B20: Polling fallback — factory that returns an OfferSyncService-like
        # object with a ``sync_chain(chain_id)`` coroutine.  When None, polling
        # fallback is disabled (events still flow via gossip/in-memory).
        self._offer_sync_factory = offer_sync_factory
        # B20: Per-chain mode tracking and reconnect tasks
        self._reconnect_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_event_time: dict[str, float] = {}

    @property
    def cache(self) -> OfferCache:
        return self._cache

    @property
    def running(self) -> bool:
        return self._running

    def set_gossip_client(self, client: GossipClient) -> None:
        """Set the gossip client (called by main.py on startup)."""
        self._gossip_client = client

    def set_lease_tracker(self, tracker: OfferLeaseTracker) -> None:
        """Set the lease tracker (called by main.py on startup)."""
        self._lease_tracker = tracker

    def set_offer_sync_factory(self, factory: Any) -> None:
        """Set the factory used to create OfferSyncService instances for polling fallback.

        ``factory`` must be a callable (sync or async) that returns an object
        with an ``async sync_chain(chain_id: str)`` method.
        """
        self._offer_sync_factory = factory

    def _get_gossip_client(self) -> GossipClient:
        if self._gossip_client is None:
            self._gossip_client = GossipClient(
                backend=settings.gossip_backend,
                redis_url=settings.gossip_broadcast_url,
            )
        return self._gossip_client

    def _get_lease_tracker(self) -> OfferLeaseTracker:
        if self._lease_tracker is None:
            self._lease_tracker = OfferLeaseTracker(redis_url=settings.lease_tracker_redis_url)
        return self._lease_tracker

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
        self._last_event_time[chain_id] = time.monotonic()
        task = asyncio.create_task(self._subscribe_loop(chain_id), name=f"offer-sub-{chain_id}")
        self._subscription_tasks[chain_id] = task
        logger.info("Started offer subscription for chain %s", chain_id)

    async def stop_chain(self, chain_id: str) -> None:
        """Stop subscribing to a chain."""
        # Cancel reconnect task if running
        reconnect = self._reconnect_tasks.pop(chain_id, None)
        if reconnect:
            reconnect.cancel()
            try:
                await reconnect
            except asyncio.CancelledError:
                pass
        task = self._subscription_tasks.pop(chain_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Close gossip subscription
        sub = self._gossip_subscriptions.pop(chain_id, None)
        if sub is not None:
            try:
                sub.close()
            except Exception:
                pass
        self._chain_status[chain_id] = SubscriptionStatus.DISCONNECTED
        logger.info("Stopped offer subscription for chain %s", chain_id)

    async def stop_all(self) -> None:
        """Stop all subscription tasks."""
        self._running = False
        for chain_id in list(self._subscription_tasks):
            await self.stop_chain(chain_id)

    # -- B19: Lease management ------------------------------------------------

    async def register_lease(self, node_id: str, chain_id: str) -> float:
        """Create a subscriber lease in Redis (B19).

        TTL = heartbeat interval × 3.  Returns the expiry timestamp.
        """
        tracker = self._get_lease_tracker()
        duration = settings.offer_subscription_heartbeat_seconds * 3
        return await tracker.register_subscriber(node_id=node_id, chain_id=chain_id, duration=duration)

    async def renew_lease(self, node_id: str) -> float:
        """Renew a subscriber lease (B19).  Returns new expiry or 0.0."""
        tracker = self._get_lease_tracker()
        duration = settings.offer_subscription_heartbeat_seconds * 3
        return await tracker.extend_lease(node_id=node_id, duration=duration)

    async def validate_lease(self, node_id: str) -> bool:
        """Validate that a subscriber lease is still active (B19)."""
        tracker = self._get_lease_tracker()
        return await tracker.validate_lease(node_id=node_id)

    async def revoke_lease(self, node_id: str) -> bool:
        """Revoke a subscriber lease (B19)."""
        tracker = self._get_lease_tracker()
        return await tracker.revoke_lease(node_id=node_id)

    # -- B18/B20: Subscription loop -------------------------------------------

    async def _subscribe_loop(self, chain_id: str) -> None:
        """Subscribe to gossip topic and process events (B18 + B20).

        Uses the :class:`GossipClient` to subscribe to ``offers.{chain_id}``.
        If the subscription disconnects or is silent beyond the threshold,
        switches to polling fallback (B20).  A reconnect task periodically
        attempts to re-establish the gossip subscription.
        """
        topic = f"offers.{chain_id}"
        client = self._get_gossip_client()
        if not client.started:
            await client.start()

        subscription: Any = None
        queue: asyncio.Queue[Any]

        try:
            subscription = await client.subscribe(topic, max_queue_size=100)
            queue = subscription.queue
            self._gossip_subscriptions[chain_id] = subscription
            self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
            logger.info("Gossip subscription active for topic %s (chain %s)", topic, chain_id)
        except Exception as e:
            logger.warning("Failed to subscribe to gossip topic %s: %s — using in-memory fallback", topic, e)
            # In-memory fallback: create a bare queue so publish_event still works
            queue = asyncio.Queue(maxsize=100)
            self._gossip_subscriptions[chain_id] = queue

        # B20: Start reconnect task (attempts to re-establish gossip every 60s)
        if settings.offer_subscription_fallback_to_polling:
            reconnect_task = asyncio.create_task(self._reconnect_loop(chain_id), name=f"offer-reconnect-{chain_id}")
            self._reconnect_tasks[chain_id] = reconnect_task

        silent_threshold = settings.subscription_silent_threshold_multiplier * settings.offer_subscription_heartbeat_seconds

        try:
            while self._running:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=settings.offer_subscription_heartbeat_seconds)
                    # B18: Decode gossip message into OfferEvent
                    event = self._decode_gossip_message(raw, chain_id)
                    if event is not None:
                        self._last_event_time[chain_id] = time.monotonic()
                        # B20: If we were in polling fallback, switch back to subscribed
                        if self._chain_status[chain_id] == SubscriptionStatus.POLLING_FALLBACK:
                            self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
                            logger.info(
                                "Chain %s switched from polling_fallback to subscribed (gossip event received)", chain_id
                            )
                        await self._handle_event(event)
                except asyncio.TimeoutError:
                    # B20: Check for silence → switch to polling fallback
                    if self._chain_status[chain_id] == SubscriptionStatus.SUBSCRIBED:
                        silent_for = time.monotonic() - self._last_event_time.get(chain_id, time.monotonic())
                        if silent_for >= silent_threshold:
                            self._switch_to_polling(chain_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Subscription loop error for chain %s: %s", chain_id, e)
            self._chain_status[chain_id] = SubscriptionStatus.RECONNECTING
        finally:
            self._gossip_subscriptions.pop(chain_id, None)
            if subscription is not None and hasattr(subscription, "close"):
                try:
                    subscription.close()
                except Exception:
                    pass

    def _decode_gossip_message(self, raw: Any, chain_id: str) -> OfferEvent | None:
        """Decode a raw gossip message into an :class:`OfferEvent`.

        The blockchain-node publishes ``OfferEvent`` dicts (via
        ``OfferEvent.to_dict()``).  This method tolerates dicts, raw
        ``OfferEvent`` instances, and unexpected payloads.
        """
        if isinstance(raw, OfferEvent):
            return raw
        if isinstance(raw, dict):
            try:
                return OfferEvent.from_dict(raw)
            except Exception:
                logger.debug("Failed to decode gossip dict as OfferEvent for chain %s", chain_id, exc_info=True)
                return None
        logger.debug("Unexpected gossip message type for chain %s: %s", chain_id, type(raw).__name__)
        return None

    # -- B20: Polling fallback ------------------------------------------------

    def _switch_to_polling(self, chain_id: str) -> None:
        """Switch a chain from subscription mode to polling fallback (B20)."""
        if self._chain_status[chain_id] == SubscriptionStatus.POLLING_FALLBACK:
            return
        if not settings.offer_subscription_fallback_to_polling:
            return
        self._chain_status[chain_id] = SubscriptionStatus.POLLING_FALLBACK
        logger.warning("Chain %s gossip subscription silent — switching to polling fallback", chain_id)

    async def _reconnect_loop(self, chain_id: str) -> None:
        """Periodically attempt to re-establish gossip subscription (B20).

        Runs every ``subscription_reconnect_interval_seconds`` (default 60s).
        On successful reconnection, switches back to subscription mode.
        Also performs a polling sync when in polling fallback mode.
        """
        try:
            while self._running:
                await asyncio.sleep(settings.subscription_reconnect_interval_seconds)
                if not self._running:
                    break

                # B20: When in polling fallback, perform a poll sync
                if self._chain_status.get(chain_id) == SubscriptionStatus.POLLING_FALLBACK:
                    await self._poll_chain(chain_id)

                # B20: Attempt to re-establish gossip subscription
                await self._attempt_reconnect(chain_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Reconnect loop error for chain %s: %s", chain_id, e)

    async def _poll_chain(self, chain_id: str) -> None:
        """Perform a single polling sync for a chain (B20 fallback)."""
        if self._offer_sync_factory is None:
            logger.debug("No offer_sync_factory configured — skipping poll for chain %s", chain_id)
            return
        try:
            factory = self._offer_sync_factory
            result = factory() if not asyncio.iscoroutinefunction(factory) else await factory()
            sync_svc = result
            await sync_svc.sync_chain(chain_id)
            logger.info("Polling fallback sync completed for chain %s", chain_id)
        except Exception as e:
            logger.warning("Polling fallback sync failed for chain %s: %s", chain_id, e)

    async def _attempt_reconnect(self, chain_id: str) -> None:
        """Attempt to re-establish the gossip subscription for a chain (B20)."""
        topic = f"offers.{chain_id}"
        client = self._get_gossip_client()
        if not client.started:
            try:
                await client.start()
            except Exception:
                return

        # If we already have an active Redis subscription, nothing to do
        if client.using_redis and chain_id in self._gossip_subscriptions:
            sub = self._gossip_subscriptions[chain_id]
            if hasattr(sub, "queue") and not isinstance(sub, asyncio.Queue):
                # Active GossipSubscription — still connected
                return

        try:
            new_sub = await client.subscribe(topic, max_queue_size=100)
            # Replace the old subscription/queue
            old = self._gossip_subscriptions.pop(chain_id, None)
            if old is not None and hasattr(old, "close"):
                try:
                    old.close()
                except Exception:
                    pass
            self._gossip_subscriptions[chain_id] = new_sub
            self._last_event_time[chain_id] = time.monotonic()
            if self._chain_status[chain_id] == SubscriptionStatus.POLLING_FALLBACK:
                self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
                logger.info("Chain %s reconnected to gossip — switched back to subscription mode", chain_id)
            elif self._chain_status[chain_id] == SubscriptionStatus.RECONNECTING:
                self._chain_status[chain_id] = SubscriptionStatus.SUBSCRIBED
                logger.info("Chain %s gossip subscription re-established", chain_id)
        except Exception as e:
            logger.debug("Reconnect attempt failed for chain %s: %s", chain_id, e)

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
        sub = self._gossip_subscriptions.get(event.chain_id)
        if sub is not None:
            queue = sub.queue if hasattr(sub, "queue") else sub
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Offer event queue full for chain %s, dropping event", event.chain_id)
        else:
            # No active subscription — publish via gossip client in-memory backend
            client = self._get_gossip_client()
            try:
                # publish_local is async but we are sync here; schedule it
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(client.publish_local(f"offers.{event.chain_id}", event))
                else:
                    loop.run_until_complete(client.publish_local(f"offers.{event.chain_id}", event))
            except Exception:
                logger.debug("publish_event fallback failed for chain %s", event.chain_id, exc_info=True)

    async def inject_event(self, event: OfferEvent) -> None:
        """Async inject an event directly into the handler (bypass queue).

        Used by tests and by the WebSocket endpoint to process events
        without going through the gossip subscription loop.
        """
        await self._handle_event(event)
