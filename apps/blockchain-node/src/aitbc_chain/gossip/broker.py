from __future__ import annotations

import asyncio
import time
import warnings
from collections import OrderedDict
from contextlib import suppress
from typing import Any

from aitbc.async_tasks import create_task_with_logging
from aitbc.gossip import PriorityMessageQueue, PrioritizedMessage

from ..config import settings
from ..metrics import metrics_registry

from ._internal import (
    _message_id,  # noqa: F401
    _peer_name,
)
from ._internal import (  # noqa: F401
    _clear_topic_metrics,
    _decode_batch,
    _decode_message,
    _encode_batch,
    _encode_message,
    _increment_publication,
    _set_queue_gauge,
    _update_subscriber_metrics,
)
from .backends.base import GossipBackend, TopicSubscription
from .backends.broadcast import BroadcastGossipBackend, _InProcessBroadcast  # noqa: F401
from .backends.in_memory import InMemoryGossipBackend
from .backends.mesh import MeshGossipBackend
from .backends.websocket import WebsocketGossipBackend

warnings.filterwarnings("ignore", message="coroutine.* was never awaited", category=RuntimeWarning)


__all__ = [
    "BroadcastGossipBackend",
    "GossipBackend",
    "GossipBroker",
    "InMemoryGossipBackend",
    "MeshGossipBackend",
    "TopicSubscription",
    "WebsocketGossipBackend",
    "create_backend",
    "gossip_broker",
]


class GossipBroker:
    def __init__(self, backend: GossipBackend) -> None:
        self._backend = backend
        self._lock = asyncio.Lock()
        self._started = False
        self._priority_enabled: bool = settings.gossip_priority_enabled
        self._priority_queue: PriorityMessageQueue | None = None
        self._priority_task: asyncio.Task[None] | None = None
        self._seen_messages: OrderedDict[str, float] = OrderedDict()
        self._dedup_max_size: int = 10000
        self._dedup_ttl: float = 300.0
        self._dedup_lock: asyncio.Lock = asyncio.Lock()
        if self._priority_enabled:
            self._priority_queue = PriorityMessageQueue()
            # _start_priority_drain() is deferred to first start()/publish()
            # call to avoid "no running event loop" at import time.

    def _compute_message_id(self, topic: str, message: Any) -> str:
        """Compute a deterministic identifier for a (topic, message) pair (see ``_message_id``)."""
        return _message_id(topic, message)

    async def _is_duplicate(self, message_id: str) -> bool:
        """Return True if ``message_id`` was seen recently, otherwise record it."""
        now = time.monotonic()
        async with self._dedup_lock:
            # Evict expired entries (oldest first since OrderedDict preserves insertion order).
            ttl = self._dedup_ttl
            seen = self._seen_messages
            while seen:
                oldest_id, oldest_ts = next(iter(seen.items()))
                if now - oldest_ts <= ttl:
                    break
                seen.pop(oldest_id, None)
            if message_id in seen:
                return True
            seen[message_id] = now
            if len(seen) > self._dedup_max_size:
                seen.popitem(last=False)
            return False

    def clear_dedup_cache(self) -> None:
        """Clear the seen-message cache (used for testing/cleanup)."""
        self._seen_messages.clear()

    def _priority_for_topic(self, topic: str) -> int:
        """Determine the priority level for a topic.

        Blocks (and block headers) are highest priority, then transactions,
        then status messages. Anything else defaults to status priority.
        """
        if topic.startswith("blocks"):
            return PriorityMessageQueue.PRIORITY_BLOCK
        if topic.startswith("transactions"):
            return PriorityMessageQueue.PRIORITY_TRANSACTION
        return PriorityMessageQueue.PRIORITY_STATUS

    def _start_priority_drain(self) -> None:
        """Start the background task that drains the priority queue."""

        async def _drain() -> None:
            batch_size = settings.gossip_message_batch_size
            if self._priority_queue is None:
                raise RuntimeError("Priority queue not initialized")
            while True:
                try:
                    messages: list[PrioritizedMessage] = self._priority_queue.get_batch(max_count=batch_size)
                    if not messages:
                        await asyncio.sleep(0.001)
                        continue
                    for msg in messages:
                        await self._backend.publish(msg.topic, msg.message)
                except asyncio.CancelledError:
                    break
                except Exception:
                    # Avoid crashing the drain loop on transient backend errors
                    await asyncio.sleep(0.001)

        self._priority_task = create_task_with_logging(_drain(), name="gossip-priority-drain")

    async def publish(self, topic: str, message: Any) -> None:
        if not self._started:
            await self._backend.start()
            self._started = True
        if self._priority_enabled and self._priority_task is None:
            self._start_priority_drain()
        message_id = self._compute_message_id(topic, message)
        if await self._is_duplicate(message_id):
            metrics_registry.increment("gossip_dedup_skipped_total")
            return
        if self._priority_enabled and self._priority_queue is not None:
            priority = self._priority_for_topic(topic)
            self._priority_queue.put(topic, message, priority)
            return
        await self._backend.publish(topic, message)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        if not self._started:
            await self._backend.start()
            self._started = True
        if self._priority_enabled and self._priority_task is None:
            self._start_priority_drain()
        unique: list[Any] = []
        for message in messages:
            message_id = self._compute_message_id(topic, message)
            if await self._is_duplicate(message_id):
                metrics_registry.increment("gossip_dedup_skipped_total")
                continue
            unique.append(message)
        if not unique:
            return
        await self._backend.publish_batch(topic, unique)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        if not self._started:
            await self._backend.start()
            self._started = True
        return await self._backend.subscribe(topic, max_queue_size=max_queue_size)

    async def set_backend(self, backend: GossipBackend) -> None:
        await backend.start()
        async with self._lock:
            previous = self._backend
            self._backend = backend
            self._started = True
        await previous.shutdown()

    def is_running(self) -> bool:
        """Return whether the broker has been started."""
        return self._started

    async def shutdown(self) -> None:
        if self._priority_task is not None:
            self._priority_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._priority_task
            self._priority_task = None
        try:
            await asyncio.wait_for(self._backend.shutdown(), timeout=5.0)
        except asyncio.TimeoutError:
            pass


def create_backend(
    backend_type: str,
    *,
    broadcast_url: str | None = None,
    websocket_url: str | None = None,
    mesh_peer_urls: list[str] | None = None,
) -> GossipBackend:
    backend = backend_type.lower()
    if backend in {"memory", "inmemory", "local"}:
        return InMemoryGossipBackend()
    if backend in {"broadcast", "starlette", "redis"}:
        if not broadcast_url:
            raise ValueError("Broadcast backend requires a gossip_broadcast_url setting")
        return BroadcastGossipBackend(broadcast_url)
    if backend in {"websocket", "wss", "ws"}:
        if not websocket_url:
            raise ValueError("Websocket backend requires a gossip_websocket_url setting")
        return WebsocketGossipBackend(websocket_url)
    if backend == "mesh":
        if not broadcast_url:
            raise ValueError("Mesh backend requires a gossip_broadcast_url setting for the local bus")
        urls = [u.strip() for u in (mesh_peer_urls or []) if u and u.strip()]
        peers: dict[str, GossipBackend] = {}
        for url in urls:
            name = _peer_name(url)
            if name in peers:
                raise ValueError(f"Duplicate mesh peer URL: {url}")
            peers[name] = WebsocketGossipBackend(url)
        return MeshGossipBackend(BroadcastGossipBackend(broadcast_url), peers)
    raise ValueError(f"Unsupported gossip backend '{backend_type}'")


gossip_broker = GossipBroker(InMemoryGossipBackend())
