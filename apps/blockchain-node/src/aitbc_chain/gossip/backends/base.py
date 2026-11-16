from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopicSubscription:
    topic: str
    queue: asyncio.Queue[Any]
    _unsubscribe: Callable[[], None]
    # #1998 H4: backend-filled counters (frames/items/decode_errors/ended/...) a
    # caller can log when a collect sees nothing. Empty for backends that do not
    # fill it; purely observational.
    stats: dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        self._unsubscribe()

    async def get(self) -> Any:
        return await self.queue.get()

    async def __aiter__(self) -> Any:
        try:
            while True:
                yield (await self.queue.get())
        finally:
            self.close()


class GossipBackend:
    """Abstract base class for gossip protocol backends.

    Concrete implementations must override publish() and subscribe().
    Examples: InMemoryGossipBackend, BroadcastGossipBackend.
    """

    async def start(self) -> None:
        return None

    async def publish(self, topic: str, message: Any) -> None:
        """Publish message to topic - must be overridden by concrete implementation"""
        raise NotImplementedError("GossipBackend.publish() must be overridden by concrete backend")

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        """Publish a batch of messages to topic.

        Default implementation loops over ``publish()``. Concrete backends
        (e.g. ``BroadcastGossipBackend``) may override this to send a single
        batched frame for efficiency.
        """
        for message in messages:
            await self.publish(topic, message)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        """Subscribe to topic - must be overridden by concrete implementation"""
        raise NotImplementedError("GossipBackend.subscribe() must be overridden by concrete backend")

    async def health(self) -> dict[str, Any]:
        """#1711: transport readiness probe for the node-engine heartbeat.

        Returns ``{"ok": bool, ...details}``. The default is optimistic —
        backends without a probeable transport (memory) report ok."""
        return {"ok": True}

    async def shutdown(self) -> None:
        return None
