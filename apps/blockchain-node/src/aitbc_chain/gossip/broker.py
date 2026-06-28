from __future__ import annotations

import asyncio
import warnings
from collections import defaultdict
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

from aitbc.gossip import PriorityMessageQueue, PrioritizedMessage

from ..config import settings
from ..metrics import metrics_registry

warnings.filterwarnings("ignore", message="coroutine.* was never awaited", category=RuntimeWarning)
try:
    from broadcaster import Broadcast  # type: ignore[import-not-found]
except ImportError:
    Broadcast = None


def _increment_publication(metric_prefix: str, topic: str) -> None:
    metrics_registry.increment(f"{metric_prefix}_total")
    metrics_registry.increment(f"{metric_prefix}_topic_{topic}")


def _set_queue_gauge(topic: str, size: int) -> None:
    metrics_registry.set_gauge(f"gossip_queue_size_{topic}", float(size))


def _update_subscriber_metrics(topics: dict[str, list[asyncio.Queue[Any]]]) -> None:
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
    queue: asyncio.Queue[Any]
    _unsubscribe: Callable[[], None]

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

    async def shutdown(self) -> None:
        return None


class InMemoryGossipBackend(GossipBackend):
    def __init__(self) -> None:
        self._topics: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: Any) -> None:
        async with self._lock:
            queues = list(self._topics.get(topic, []))
        for queue in queues:
            await queue.put(message)
            _set_queue_gauge(topic, queue.qsize())
        _increment_publication("gossip_publications", topic)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        for message in messages:
            await self.publish(topic, message)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
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
    """Redis pub/sub backend for cross-process gossip.

    Uses redis-py directly instead of the broadcaster library for
    compatibility with redis-py 8.x.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._redis: Any = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        if not self._running:
            import redis.asyncio as aioredis

            self._redis = aioredis.Redis.from_url(self._url, socket_timeout=None, socket_connect_timeout=5)
            self._running = True

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Broadcast backend not started")
        payload = _encode_message(message)
        await self._redis.publish(topic, payload)
        _increment_publication("gossip_broadcast_publications", topic)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        """Publish a batch of messages as a single compressed Redis frame."""
        if not self._running:
            raise RuntimeError("Broadcast backend not started")
        if not messages:
            return
        payload = _encode_batch(messages)
        await self._redis.publish(topic, payload)
        _increment_publication("gossip_broadcast_publications", topic)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        logger.info("BroadcastGossipBackend.subscribe called for topic: %s, running=%s", topic, self._running)
        if not self._running:
            raise RuntimeError("Broadcast backend not started")
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        stop_event = asyncio.Event()

        async def _run_subscription() -> None:
            from aitbc.aitbc_logging import get_logger

            logger = get_logger(__name__)
            logger.info("[BROKER SUB] Starting redis subscription for topic: %s", topic)
            try:
                import redis.asyncio as aioredis

                # Use a dedicated connection with no socket timeout for pubsub
                # (listen() blocks indefinitely waiting for messages)
                sub_redis = aioredis.Redis.from_url(self._url, socket_timeout=None, socket_connect_timeout=5)
                pubsub = sub_redis.pubsub()
                await pubsub.subscribe(topic)
                logger.info("[BROKER SUB] Successfully subscribed to redis topic: %s", topic)
                async for message in pubsub.listen():
                    if stop_event.is_set():
                        logger.info("[BROKER SUB] Stop event set for topic: %s", topic)
                        break
                    if message["type"] != "message":
                        continue
                    logger.info("[BROKER SUB] Received message from redis for topic %s", topic)
                    try:
                        for decoded in _decode_batch(message["data"]):
                            await queue.put(decoded)
                            _set_queue_gauge(topic, queue.qsize())
                    except asyncio.CancelledError:
                        logger.warning("[BROKER SUB] Subscription cancelled for topic: %s", topic)
                        break
                await pubsub.aclose()
                await sub_redis.aclose()
            except Exception as e:
                logger.error("[BROKER SUB ERROR] Redis subscription error for topic %s: %s", topic, e)
            logger.info("[BROKER SUB] Redis subscription ended for topic: %s", topic)

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
        if self._running and self._redis:
            await self._redis.aclose()
            self._running = False


class GossipBroker:
    def __init__(self, backend: GossipBackend) -> None:
        self._backend = backend
        self._lock = asyncio.Lock()
        self._started = False
        self._priority_enabled: bool = settings.gossip_priority_enabled
        self._priority_queue: PriorityMessageQueue | None = None
        self._priority_task: asyncio.Task[None] | None = None
        if self._priority_enabled:
            self._priority_queue = PriorityMessageQueue()
            self._start_priority_drain()

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
            assert self._priority_queue is not None
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

        self._priority_task = asyncio.create_task(_drain(), name="gossip-priority-drain")

    async def publish(self, topic: str, message: Any) -> None:
        if not self._started:
            await self._backend.start()
            self._started = True
        if self._priority_enabled and self._priority_queue is not None:
            priority = self._priority_for_topic(topic)
            self._priority_queue.put(topic, message, priority)
            return
        await self._backend.publish(topic, message)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        if not self._started:
            await self._backend.start()
            self._started = True
        await self._backend.publish_batch(topic, messages)

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
        if self._priority_task is not None:
            self._priority_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._priority_task
            self._priority_task = None
        await self._backend.shutdown()


class _InProcessSubscriber:
    def __init__(self, queue: asyncio.Queue[Any]):
        self._queue = queue

    def __aiter__(self) -> Any:
        return self._iterator()

    async def _iterator(self) -> Any:
        while True:
            yield (await self._queue.get())


class _InProcessBroadcast:
    """Minimal in-memory broadcast substitute for tests when Starlette Broadcast is absent."""

    def __init__(self) -> None:
        self._topics: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._running = False

    async def connect(self) -> None:
        self._running = True

    async def disconnect(self) -> None:
        async with self._lock:
            self._topics.clear()
        self._running = False

    @asynccontextmanager
    async def subscribe(self, topic: str) -> Any:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            self._topics[topic].append(queue)
        try:
            yield _InProcessSubscriber(queue)
        finally:
            async with self._lock:
                queues = self._topics.get(topic)
                if queues and queue in queues:
                    queues.remove(queue)

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Broadcast backend not started")
        async with self._lock:
            queues = list(self._topics.get(topic, []))
        for queue in queues:
            await queue.put(message)


def create_backend(backend_type: str, *, broadcast_url: str | None = None) -> GossipBackend:
    backend = backend_type.lower()
    if backend in {"memory", "inmemory", "local"}:
        return InMemoryGossipBackend()
    if backend in {"broadcast", "starlette", "redis"}:
        if not broadcast_url:
            raise ValueError("Broadcast backend requires a gossip_broadcast_url setting")
        return BroadcastGossipBackend(broadcast_url)
    raise ValueError(f"Unsupported gossip backend '{backend_type}'")


def _encode_message(message: Any) -> Any:
    """Serialize a message for transport, compressing when enabled."""
    from ..network.compression import encode_payload

    if isinstance(message, str | bytes | bytearray):
        return message
    return encode_payload(message)


def _decode_message(message: Any) -> Any:
    """Decode a transport payload, transparently decompressing if needed."""
    from ..network.compression import decode_payload

    if isinstance(message, str | bytes | bytearray):
        return decode_payload(message)
    return message


def _encode_batch(messages: list[Any]) -> str:
    """Serialize a list of messages as a single compressed batch frame.

    The list is JSON-serialized then compressed with the ``GZ:`` prefix, so
    receivers can transparently detect and decompress it.
    """
    from ..network.compression import encode_payload

    return encode_payload(messages)


def _decode_batch(data: Any) -> list[Any]:
    """Decode a transport payload into a list of messages.

    Handles three cases transparently for backward compatibility:

    * Batched messages (a JSON array after decompression) -> returned as-is.
    * Single messages (a JSON object after decompression) -> wrapped in a list.
    * Raw strings/bytes (no ``GZ:`` prefix) -> decoded and wrapped in a list.
    """
    from ..network.compression import decode_payload

    decoded = decode_payload(data) if isinstance(data, str | bytes | bytearray) else data
    if isinstance(decoded, list):
        return decoded
    return [decoded]


gossip_broker = GossipBroker(InMemoryGossipBackend())
