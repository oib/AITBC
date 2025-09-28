from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from starlette.broadcast import Broadcast
except ImportError:  # pragma: no cover - Starlette is an indirect dependency of FastAPI
    Broadcast = None  # type: ignore[assignment]

from ..metrics import metrics_registry


def _increment_publication(metric_prefix: str, topic: str) -> None:
    metrics_registry.increment(f"{metric_prefix}_total")
    metrics_registry.increment(f"{metric_prefix}_topic_{topic}")


def _set_queue_gauge(topic: str, size: int) -> None:
    metrics_registry.set_gauge(f"gossip_queue_size_{topic}", float(size))


def _update_subscriber_metrics(topics: Dict[str, List["asyncio.Queue[Any]"]]) -> None:
    for topic, queues in topics.items():
        metrics_registry.set_gauge(f"gossip_subscribers_topic_{topic}", float(len(queues)))
    total = sum(len(queues) for queues in topics.values())
    metrics_registry.set_gauge("gossip_subscribers_total", float(total))


def _clear_topic_metrics(topic: str) -> None:
    metrics_registry.set_gauge(f"gossip_subscribers_topic_{topic}", 0.0)
    _set_queue_gauge(topic, 0)

@dataclass
class TopicSubscription:
    topic: str
    queue: "asyncio.Queue[Any]"
    _unsubscribe: Callable[[], None]

    def close(self) -> None:
        self._unsubscribe()

    async def get(self) -> Any:
        return await self.queue.get()

    async def __aiter__(self):  # type: ignore[override]
        try:
            while True:
                yield await self.queue.get()
        finally:
            self.close()


class GossipBackend:
    async def start(self) -> None:  # pragma: no cover - overridden as needed
        return None

    async def publish(self, topic: str, message: Any) -> None:
        raise NotImplementedError

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        raise NotImplementedError

    async def shutdown(self) -> None:
        return None


class InMemoryGossipBackend(GossipBackend):
    def __init__(self) -> None:
        self._topics: Dict[str, List["asyncio.Queue[Any]"]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: Any) -> None:
        async with self._lock:
            queues = list(self._topics.get(topic, []))
        for queue in queues:
            await queue.put(message)
            _set_queue_gauge(topic, queue.qsize())
        _increment_publication("gossip_publications", topic)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=max_queue_size)

        async with self._lock:
            self._topics[topic].append(queue)
            _update_subscriber_metrics(self._topics)

        _set_queue_gauge(topic, queue.qsize())

        def _unsubscribe() -> None:
            async def _remove() -> None:
                async with self._lock:
                    queues = self._topics.get(topic)
                    if queues is None:
                        return
                    if queue in queues:
                        queues.remove(queue)
                        if not queues:
                            self._topics.pop(topic, None)
                            _clear_topic_metrics(topic)
                        _update_subscriber_metrics(self._topics)

            asyncio.create_task(_remove())

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        async with self._lock:
            topics = list(self._topics.keys())
            self._topics.clear()
        for topic in topics:
            _clear_topic_metrics(topic)
        _update_subscriber_metrics(self._topics)


class BroadcastGossipBackend(GossipBackend):
    def __init__(self, url: str) -> None:
        if Broadcast is None:  # pragma: no cover - dependency is optional
            raise RuntimeError("Starlette Broadcast backend requested but starlette is not available")
        self._broadcast = Broadcast(url)  # type: ignore[arg-type]
        self._tasks: Set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        if not self._running:
            await self._broadcast.connect()  # type: ignore[union-attr]
            self._running = True

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Broadcast backend not started")
        payload = _encode_message(message)
        await self._broadcast.publish(topic, payload)  # type: ignore[union-attr]
        _increment_publication("gossip_broadcast_publications", topic)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        if not self._running:
            raise RuntimeError("Broadcast backend not started")

        queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=max_queue_size)
        stop_event = asyncio.Event()

        async def _run_subscription() -> None:
            async with self._broadcast.subscribe(topic) as subscriber:  # type: ignore[attr-defined,union-attr]
                async for event in subscriber:  # type: ignore[union-attr]
                    if stop_event.is_set():
                        break
                    data = _decode_message(getattr(event, "message", event))
                    try:
                        await queue.put(data)
                        _set_queue_gauge(topic, queue.qsize())
                    except asyncio.CancelledError:
                        break

        task = asyncio.create_task(_run_subscription(), name=f"broadcast-sub:{topic}")
        async with self._lock:
            self._tasks.add(task)
            metrics_registry.set_gauge("gossip_broadcast_subscribers_total", float(len(self._tasks)))

        def _unsubscribe() -> None:
            async def _stop() -> None:
                stop_event.set()
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                async with self._lock:
                    self._tasks.discard(task)
                    metrics_registry.set_gauge("gossip_broadcast_subscribers_total", float(len(self._tasks)))

            asyncio.create_task(_stop())

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks)
            self._tasks.clear()
            metrics_registry.set_gauge("gossip_broadcast_subscribers_total", 0.0)
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._running:
            await self._broadcast.disconnect()  # type: ignore[union-attr]
            self._running = False


class GossipBroker:
    def __init__(self, backend: GossipBackend) -> None:
        self._backend = backend
        self._lock = asyncio.Lock()
        self._started = False

    async def publish(self, topic: str, message: Any) -> None:
        if not self._started:
            await self._backend.start()
            self._started = True
        await self._backend.publish(topic, message)

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

    async def shutdown(self) -> None:
        await self._backend.shutdown()
        self._started = False
        metrics_registry.set_gauge("gossip_subscribers_total", 0.0)


def create_backend(backend_type: str, *, broadcast_url: Optional[str] = None) -> GossipBackend:
    backend = backend_type.lower()
    if backend in {"memory", "inmemory", "local"}:
        return InMemoryGossipBackend()
    if backend in {"broadcast", "starlette", "redis"}:
        if not broadcast_url:
            raise ValueError("Broadcast backend requires a gossip_broadcast_url setting")
        return BroadcastGossipBackend(broadcast_url)
    raise ValueError(f"Unsupported gossip backend '{backend_type}'")


def _encode_message(message: Any) -> Any:
    if isinstance(message, (str, bytes, bytearray)):
        return message
    return json.dumps(message, separators=(",", ":"))


def _decode_message(message: Any) -> Any:
    if isinstance(message, (bytes, bytearray)):
        message = message.decode("utf-8")
    if isinstance(message, str):
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return message
    return message


gossip_broker = GossipBroker(InMemoryGossipBackend())

