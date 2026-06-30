r"""Offer notification service for debounced batch notifications (v0.8.2 §B4).

Maintains saved query subscriptions from WebSocket clients, matches incoming
``OfferEvent`` s against saved queries, debounces batch notifications
(collects events for ``debounce_ms`` then sends), and pushes notifications
to WebSocket subscribers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aitbc.trading.subscription_types import OfferEvent, OfferNotification, OfferSubscription

logger = logging.getLogger(__name__)


class OfferNotificationService:
    r"""Manages saved query subscriptions and debounced batch notifications.

    Each WebSocket subscriber registers an ``OfferSubscription`` (saved query).
    Incoming ``OfferEvent`` s are matched against all subscriptions. Matching
    events are collected per-subscriber and flushed as ``OfferNotification``
    batches after the debounce window expires.
    """

    def __init__(self, debounce_ms: int = 1000) -> None:
        self._debounce_ms = debounce_ms
        self._subscribers: dict[str, OfferSubscription] = {}
        self._pending: dict[str, list[OfferEvent]] = {}
        self._flush_tasks: dict[str, asyncio.Task[None]] = {}
        self._notify_callbacks: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def get_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Get all active subscriptions for status reporting."""
        return {
            sub_id: {
                "filters": sub.to_filters_dict(),
                "pending_events": len(self._pending.get(sub_id, [])),
            }
            for sub_id, sub in self._subscribers.items()
        }

    async def register_subscriber(
        self,
        subscriber_id: str,
        subscription: OfferSubscription,
        notify_callback: Any | None = None,
    ) -> None:
        """Register a new subscriber with a saved query."""
        async with self._lock:
            self._subscribers[subscriber_id] = subscription
            self._pending[subscriber_id] = []
            if notify_callback is not None:
                self._notify_callbacks[subscriber_id] = notify_callback
            logger.info("Registered offer subscriber %s (filters=%s)", subscriber_id, subscription.to_filters_dict())

    async def unregister_subscriber(self, subscriber_id: str) -> None:
        """Remove a subscriber and cancel pending flush."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)
            self._pending.pop(subscriber_id, None)
            self._notify_callbacks.pop(subscriber_id, None)
            task = self._flush_tasks.pop(subscriber_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Unregistered offer subscriber %s", subscriber_id)

    async def process_event(self, event: OfferEvent) -> None:
        """Process an incoming offer event against all subscriptions.

        Matching events are added to the subscriber's pending list and
        a debounce timer is started (or reset) to flush the batch.
        """
        async with self._lock:
            for sub_id, subscription in self._subscribers.items():
                if subscription.matches(event):
                    self._pending.setdefault(sub_id, []).append(event)
                    self._start_debounce(sub_id)

    def _start_debounce(self, subscriber_id: str) -> None:
        """Start or reset the debounce timer for a subscriber."""
        existing = self._flush_tasks.get(subscriber_id)
        if existing and not existing.done():
            existing.cancel()

        async def _flush() -> None:
            try:
                await asyncio.sleep(self._debounce_ms / 1000.0)
                await self._flush_batch(subscriber_id)
            except asyncio.CancelledError:
                pass

        self._flush_tasks[subscriber_id] = asyncio.create_task(_flush(), name=f"offer-debounce-{subscriber_id}")

    async def _flush_batch(self, subscriber_id: str) -> None:
        """Flush pending events as a batch notification to the subscriber."""
        async with self._lock:
            events = self._pending.pop(subscriber_id, [])
            if not events:
                return
            self._pending[subscriber_id] = []

        chain_id = events[0].chain_id if events else ""
        notification = OfferNotification.build(events, chain_id=chain_id)
        callback = self._notify_callbacks.get(subscriber_id)
        if callback is not None:
            try:
                result = callback(notification)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("Notification callback error for %s: %s", subscriber_id, e)

        logger.debug("Flushed %d events to subscriber %s", notification.batch_size, subscriber_id)

    async def flush_all(self) -> None:
        """Flush all pending batches immediately (used on shutdown)."""
        for sub_id in list(self._pending):
            task = self._flush_tasks.pop(sub_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._flush_batch(sub_id)

    async def close(self) -> None:
        """Clean up all subscribers and pending tasks."""
        await self.flush_all()
        self._subscribers.clear()
        self._pending.clear()
        self._notify_callbacks.clear()
        self._flush_tasks.clear()
