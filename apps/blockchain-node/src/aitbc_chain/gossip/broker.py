from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import time
import uuid
import warnings
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any

from aitbc.async_tasks import create_task_with_logging
from aitbc.gossip import PriorityMessageQueue, PrioritizedMessage

from ..config import settings
from ..metrics import metrics_registry

warnings.filterwarnings("ignore", message="coroutine.* was never awaited", category=RuntimeWarning)


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
            queues = self._topics.get(topic)
            if queues is None or queue not in queues:
                return
            queues.remove(queue)
            if not queues:
                self._topics.pop(topic, None)
                _clear_topic_metrics(topic)
            _update_subscriber_metrics(self._topics)

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
            sub_redis: Any = None
            pubsub: Any = None
            try:
                import redis.asyncio as aioredis

                # Use a dedicated connection with a short read timeout for pubsub.
                # A blocking listen() cannot be interrupted by task.cancel() until a
                # message arrives, so we poll with get_message(timeout=0.5) instead.
                # This makes shutdown responsive and prevents 60-90s systemd stop hangs.
                sub_redis = aioredis.Redis.from_url(
                    self._url,
                    socket_timeout=None,
                    socket_connect_timeout=5,
                )
                pubsub = sub_redis.pubsub()
                await pubsub.subscribe(topic)
                logger.info("[BROKER SUB] Successfully subscribed to redis topic: %s", topic)
                while not stop_event.is_set():
                    try:
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                    except asyncio.CancelledError:
                        logger.info("[BROKER SUB] Subscription cancelled for topic: %s", topic)
                        break
                    if stop_event.is_set():
                        logger.info("[BROKER SUB] Stop event set for topic: %s", topic)
                        break
                    if message is None:
                        continue
                    if message["type"] != "message":
                        continue
                    logger.info("[BROKER SUB] Received message from redis for topic %s", topic)
                    try:
                        for decoded in _decode_batch(message["data"]):
                            await queue.put(decoded)
                            _set_queue_gauge(topic, queue.qsize())
                    except asyncio.CancelledError:
                        logger.warning("[BROKER SUB] Decode/queue cancelled for topic: %s", topic)
                        break
            except Exception as e:
                logger.error("[BROKER SUB ERROR] Redis subscription error for topic %s: %s", topic, e)
            finally:
                try:
                    if pubsub is not None:
                        await pubsub.aclose()
                except Exception:
                    pass
                try:
                    if sub_redis is not None:
                        await sub_redis.aclose()
                except Exception:
                    pass
            logger.info("[BROKER SUB] Redis subscription ended for topic: %s", topic)

        task = create_task_with_logging(_run_subscription(), name=f"broadcast-sub:{topic}")
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

            create_task_with_logging(_stop(), name="broadcast_unsubscribe_stop")

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        self._running = False
        async with self._lock:
            tasks = list(self._tasks)
            self._tasks.clear()
            metrics_registry.set_gauge("gossip_broadcast_subscribers_total", 0.0)
        for task in tasks:
            task.cancel()
            try:
                # The get_message(timeout=0.5) loop in _run_subscription should
                # respond to cancellation within one timeout, but cap the wait
                # so the RPC process can exit even if a Redis read is stuck.
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Broadcast subscription task did not stop in time")
            except asyncio.CancelledError:
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception as e:
                logger.warning("Failed to close broadcast redis connection: %s", e)


class WebsocketGossipBackend(GossipBackend):
    """Cross-node gossip over a WebSocket (wss) connection.

    Each topic is multiplexed over its own WebSocket to the endpoint
    ``<base_url>?topic=<topic>&client_id=<id>``. Messages are JSON-encoded.
    Outgoing messages are tracked for a short time so that the broker-level
    echo caused by the server re-broadcasting is ignored.

    v0.7.6+: publish() waits for the server echo (ack) before returning.
    This detects silent ``CLOSE-WAIT`` sockets where the OS accepts the send()
    but the peer is no longer reading, because the echo never comes back.
    """

    def __init__(
        self,
        base_url: str,
        *,
        suppress_echo_ttl: float = 5.0,
        ack_timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_id = uuid.uuid4().hex
        self._ssl_context: ssl.SSLContext | None = None
        if self._base_url.startswith("wss://"):
            self._ssl_context = ssl.create_default_context()
        self._websockets: dict[str, Any] = {}
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._readers: dict[str, asyncio.Task[None]] = {}
        self._ref_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._echo_ttl = suppress_echo_ttl
        self._sent_message_ids: dict[str, float] = {}
        self._sent_lock = asyncio.Lock()
        self._reconnecting: set[str] = set()
        self._reconnect_backoff: dict[str, float] = {}
        self._ack_timeout = ack_timeout
        self._ack_events: dict[str, asyncio.Event] = {}
        self._ack_lock = asyncio.Lock()
        self._connect_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        self._running = True

    def _connect_lock(self, topic: str) -> asyncio.Lock:
        """Return a per-topic lock used to serialize connection work."""
        if topic not in self._connect_locks:
            self._connect_locks[topic] = asyncio.Lock()
        return self._connect_locks[topic]

    def _is_websocket_open(self, ws: Any) -> bool:
        """Return True if a websockets connection is open.

        websockets >=14 replaced the ``open`` property with a ``state``
        attribute.  Check both so we work on the version in the venv.
        """
        if getattr(ws, "open", False):
            return True
        state = getattr(ws, "state", None)
        if state is None:
            return False
        # state may be an enum or an integer (State.OPEN == 1)
        return getattr(state, "name", None) == "OPEN" or state == 1

    def _compute_message_id(self, topic: str, message: Any) -> str:
        """Compute a stable message identifier for echo suppression and ack matching."""
        return _message_id(topic, message)

    async def _record_sent(self, topic: str, message: Any) -> None:
        msg_id = self._compute_message_id(topic, message)
        now = time.monotonic()
        async with self._sent_lock:
            self._sent_message_ids[msg_id] = now
            for k, ts in list(self._sent_message_ids.items()):
                if now - ts > self._echo_ttl:
                    del self._sent_message_ids[k]

    async def _is_echo(self, topic: str, message: Any) -> bool:
        msg_id = self._compute_message_id(topic, message)
        # If we are waiting for an ack, the echo sets the event and is suppressed.
        ack_event: asyncio.Event | None = None
        async with self._ack_lock:
            ack_event = self._ack_events.get(msg_id)
        if ack_event is not None:
            ack_event.set()
            return True
        now = time.monotonic()
        async with self._sent_lock:
            if msg_id in self._sent_message_ids:
                self._sent_message_ids[msg_id] = now
                return True
            for k, ts in list(self._sent_message_ids.items()):
                if now - ts > self._echo_ttl:
                    del self._sent_message_ids[k]
        return False

    async def _ensure_connection(self, topic: str) -> None:
        """Acquire the per-topic lock and open/reopen the websocket."""
        async with self._connect_lock(topic):
            await self._ensure_connection_unsafe(topic)

    async def _ensure_connection_unsafe(self, topic: str) -> None:
        import websockets

        existing = self._websockets.get(topic)
        if existing is not None and self._is_websocket_open(existing):
            return
        if existing is not None:
            await self._cleanup_websocket_unsafe(topic)

        url = f"{self._base_url}?topic={topic}&client_id={self._client_id}"
        try:
            ws = await websockets.connect(
                url,
                ssl=self._ssl_context,
                ping_interval=20,
                ping_timeout=10,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to connect to gossip websocket for {topic}: {e}") from e
        self._websockets[topic] = ws
        self._readers[topic] = create_task_with_logging(
            self._reader(topic, ws),
            name=f"ws-gossip-reader:{topic}",
        )
        self._reconnect_backoff[topic] = 0.5

    async def _reader(self, topic: str, ws: Any) -> None:
        import websockets

        try:
            async for raw in ws:
                if not raw:
                    continue
                try:
                    message = json.loads(raw)
                except Exception:
                    continue
                if await self._is_echo(topic, message):
                    continue
                queue = self._queues.get(topic)
                if queue:
                    await queue.put(message)
        except websockets.exceptions.ConnectionClosed as exc:
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).info(
                "WebSocket gossip connection closed for %s: code=%s reason=%s",
                topic,
                exc.code,
                exc.reason,
            )
        except Exception as e:
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).warning("WebSocket gossip reader error for %s: %s", topic, e)
        finally:
            keep_alive = self._running and self._ref_counts.get(topic, 0) > 0
            if keep_alive:
                await self._cleanup_websocket(topic)
                self._schedule_reconnect(topic)
            else:
                await self._cleanup(topic)

    async def _cleanup_websocket(self, topic: str) -> None:
        """Close the websocket and reader task but keep the subscriber queue."""
        async with self._connect_lock(topic):
            await self._cleanup_websocket_unsafe(topic)

    async def _cleanup_websocket_unsafe(self, topic: str) -> None:
        """Close the websocket and reader task; caller must hold the connect lock."""
        ws = self._websockets.pop(topic, None)
        task = self._readers.pop(topic, None)
        if ws:
            with suppress(Exception):
                await ws.close(close_timeout=2.0)
        if task and task is not asyncio.current_task():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    def _schedule_reconnect(self, topic: str) -> None:
        from aitbc.aitbc_logging import get_logger

        if topic in self._reconnecting:
            get_logger(__name__).debug("Reconnect already in progress for websocket gossip topic %s", topic)
            return
        get_logger(__name__).info("Scheduling reconnect for websocket gossip topic %s", topic)
        self._reconnecting.add(topic)
        create_task_with_logging(
            self._reconnect(topic),
            name=f"ws-gossip-reconnect:{topic}",
        )

    async def _reconnect(self, topic: str) -> None:
        """Reconnect a persistent subscriber topic with exponential backoff."""
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        if not self._running:
            return
        if self._ref_counts.get(topic, 0) <= 0:
            return
        try:
            delay = self._reconnect_backoff.get(topic, 0.5)
            logger.info("WebSocket gossip reconnect for %s after %ss", topic, delay)
            await asyncio.sleep(delay)
            if self._ref_counts.get(topic, 0) <= 0:
                return
            await self._ensure_connection(topic)
            self._reconnect_backoff[topic] = 0.5
        except Exception as e:
            current = self._reconnect_backoff.get(topic, 0.5)
            self._reconnect_backoff[topic] = min(current * 2, 30.0)
            logger.warning("WebSocket gossip reconnect failed for %s: %s", topic, e)
            self._schedule_reconnect(topic)
        finally:
            self._reconnecting.discard(topic)

    async def _cleanup(self, topic: str) -> None:
        async with self._connect_lock(topic):
            await self._cleanup_websocket_unsafe(topic)
        async with self._lock:
            self._queues.pop(topic, None)
            self._ref_counts.pop(topic, None)

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Websocket backend not started")
        await self._publish_with_ack(topic, message, retry=True)

    async def _publish_with_ack(
        self,
        topic: str,
        message: Any,
        *,
        retry: bool,
    ) -> None:
        """Publish a message and wait for the server echo (ack).

        If the ack does not arrive within ``_ack_timeout`` seconds the send is
        considered lost, the connection is torn down and (for ``retry=True``)
        the message is resent once.
        """
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        msg_id = self._compute_message_id(topic, message)
        ack_event = asyncio.Event()
        async with self._ack_lock:
            self._ack_events[msg_id] = ack_event
        try:
            async with self._connect_lock(topic):
                await self._ensure_connection_unsafe(topic)
                await self._record_sent(topic, message)
                ws = self._websockets[topic]
                await ws.send(json.dumps(message, default=str))
                logger.debug("Published websocket message for %s; awaiting ack", topic)
                await asyncio.wait_for(ack_event.wait(), timeout=self._ack_timeout)
                logger.debug("Received ack for websocket message on %s", topic)
        except Exception as e:
            if not retry:
                raise RuntimeError(f"WebSocket gossip publish/ack failed for {topic}: {e}") from e
            logger.info(
                "WebSocket gossip publish/ack failed for %s (will retry once): %s",
                topic,
                e,
            )
            await self._cleanup_websocket(topic)
            await self._publish_with_ack(topic, message, retry=False)
        finally:
            async with self._ack_lock:
                self._ack_events.pop(msg_id, None)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        if not self._running:
            raise RuntimeError("Websocket backend not started")
        await self._ensure_connection(topic)
        async with self._lock:
            self._ref_counts[topic] = self._ref_counts.get(topic, 0) + 1
            if topic not in self._queues:
                self._queues[topic] = asyncio.Queue(maxsize=max_queue_size)
            queue = self._queues[topic]

        def _unsubscribe() -> None:
            create_task_with_logging(
                self._do_unsubscribe(topic),
                name=f"ws-gossip-unsub:{topic}",
            )

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def _do_unsubscribe(self, topic: str) -> None:
        async with self._lock:
            self._ref_counts[topic] = max(0, self._ref_counts.get(topic, 0) - 1)
            if self._ref_counts.get(topic, 0) > 0:
                return
        await self._cleanup(topic)

    async def shutdown(self) -> None:
        self._running = False
        topics = list(self._websockets.keys())
        for topic in topics:
            try:
                await asyncio.wait_for(self._cleanup(topic), timeout=5.0)
            except asyncio.TimeoutError:
                from aitbc.aitbc_logging import get_logger

                logger = get_logger(__name__)
                logger.warning("WebSocket cleanup for %s timed out; leaving connection", topic)
            except Exception as e:
                from aitbc.aitbc_logging import get_logger

                logger = get_logger(__name__)
                logger.warning("WebSocket cleanup for %s raised: %s", topic, e)


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


def _message_id(topic: str, message: Any) -> str:
    """Deterministic identifier for a (topic, message) pair.

    Used for publish-side dedup in ``GossipBroker``, echo suppression in the
    websocket backend and receive-side dedup in the mesh backend, so the same
    message arriving over several links is recognised as one.

    * An explicit ``id`` field is always the identity.
    * ``hash`` is the identity only on ``blocks*`` topics, where it is the block
      hash. On other topics ``hash`` is a *reference* (attestation responses and
      PBFT messages all quote the block they vote on) and several distinct
      messages from different validators legitimately share it - keying on it
      there silently dropped all but the first attestation.
    * Everything else hashes its canonical JSON encoding.
    """
    if isinstance(message, dict):
        if "id" in message:
            return f"{topic}:{message['id']}"
        if "hash" in message and topic.split(".", 1)[0] == "blocks":
            return f"{topic}:{message['hash']}"
    payload = json.dumps(message, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{topic}:{digest}"


class MeshGossipBackend(GossipBackend):
    """Fan-out / merge gossip over a local bus plus direct links to every peer.

    Every validator runs this backend in its node process with:

    * ``local`` – the intra-host bus (normally Redis) shared with the node's own
      RPC process, whose ``/rpc/gossip/ws`` handler bridges inbound peer
      connections into that bus.
    * ``peers`` – one ``WebsocketGossipBackend`` per remote validator, pointing
      at that validator's ``/rpc/gossip/ws``.

    ``publish`` writes to the local bus synchronously and pushes to every peer
    best-effort in the background, so a slow or dead peer never blocks the
    caller (PBFT awaits its broadcasts). ``subscribe`` merges the local bus and
    all peer links into one queue and drops duplicates by message id, because
    the same message legitimately arrives over several links (direct push from
    the origin plus relay through each peer's RPC bridge). Peers that cannot be
    reached at subscribe time are retried in the background with backoff.

    The topology has no central relay: as long as a validator's node process
    can reach a quorum of peer RPC endpoints, consensus messages flow even when
    any single node (including the hub) is down.
    """

    def __init__(
        self,
        local: GossipBackend,
        peers: dict[str, GossipBackend],
        *,
        dedup_ttl: float = 300.0,
        dedup_max_size: int = 10000,
        peer_publish_timeout: float = 30.0,
        max_inflight_per_peer: int = 64,
        retry_min_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        self._local = local
        self._peers = dict(peers)
        self._dedup_ttl = dedup_ttl
        self._dedup_max_size = dedup_max_size
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._seen_lock = asyncio.Lock()
        self._peer_publish_timeout = peer_publish_timeout
        self._max_inflight_per_peer = max_inflight_per_peer
        self._inflight: dict[str, set[asyncio.Task[None]]] = defaultdict(set)
        self._retry_min_delay = retry_min_delay
        self._retry_max_delay = retry_max_delay
        self._subscriptions: set[_MeshSubscription] = set()
        self._running = False

    @property
    def peer_names(self) -> list[str]:
        return list(self._peers.keys())

    async def start(self) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        await self._local.start()
        for name, peer in self._peers.items():
            try:
                await peer.start()
            except Exception as e:
                logger.warning("Mesh gossip peer %s failed to start: %s", name, e)
        self._running = True
        metrics_registry.set_gauge("gossip_mesh_peers_configured", float(len(self._peers)))

    async def _remember(self, message_id: str) -> bool:
        """Record ``message_id``; return True if it was already seen recently."""
        now = time.monotonic()
        async with self._seen_lock:
            seen = self._seen
            while seen:
                oldest_id, oldest_ts = next(iter(seen.items()))
                if now - oldest_ts <= self._dedup_ttl:
                    break
                seen.pop(oldest_id, None)
            if message_id in seen:
                return True
            seen[message_id] = now
            if len(seen) > self._dedup_max_size:
                seen.popitem(last=False)
            return False

    def _spawn_peer_publish(self, name: str, coro_factory: Callable[[], Any], topic: str) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        inflight = self._inflight[name]
        if len(inflight) >= self._max_inflight_per_peer:
            metrics_registry.increment("gossip_mesh_peer_publish_dropped_total")
            logger.warning(
                "Mesh gossip peer %s has %d publishes in flight; dropping message on %s",
                name,
                len(inflight),
                topic,
            )
            return

        async def _run() -> None:
            try:
                await asyncio.wait_for(coro_factory(), timeout=self._peer_publish_timeout)
                metrics_registry.increment("gossip_mesh_peer_publish_total")
            except Exception as e:
                metrics_registry.increment("gossip_mesh_peer_publish_failed_total")
                logger.info("Mesh gossip publish to peer %s on %s failed: %s", name, topic, e)

        task = create_task_with_logging(_run(), name=f"mesh-gossip-publish:{name}:{topic}")
        inflight.add(task)
        task.add_done_callback(inflight.discard)

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        await self._local.publish(topic, message)
        for name, peer in self._peers.items():
            self._spawn_peer_publish(name, lambda p=peer: p.publish(topic, message), topic)
        _increment_publication("gossip_mesh_publications", topic)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        if not messages:
            return
        await self._local.publish_batch(topic, messages)
        for name, peer in self._peers.items():
            self._spawn_peer_publish(name, lambda p=peer: p.publish_batch(topic, messages), topic)
        _increment_publication("gossip_mesh_publications", topic)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        sub = _MeshSubscription(self, topic, queue, max_queue_size)
        # The local bus is mandatory: without it the node cannot even hear its
        # own RPC bridge, so a failure here is a real error.
        await sub.attach("local", self._local, retry=False)
        for name, peer in self._peers.items():
            await sub.attach(name, peer, retry=True)
        self._subscriptions.add(sub)

        def _unsubscribe() -> None:
            self._subscriptions.discard(sub)
            create_task_with_logging(sub.close(), name=f"mesh-gossip-unsub:{topic}")

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        self._running = False
        for sub in list(self._subscriptions):
            with suppress(Exception):
                await asyncio.wait_for(sub.close(), timeout=5.0)
        self._subscriptions.clear()
        for tasks in self._inflight.values():
            for task in list(tasks):
                task.cancel()
        self._inflight.clear()
        for name, peer in self._peers.items():
            try:
                await asyncio.wait_for(peer.shutdown(), timeout=5.0)
            except Exception as e:
                from aitbc.aitbc_logging import get_logger

                get_logger(__name__).warning("Mesh gossip peer %s shutdown raised: %s", name, e)
        await self._local.shutdown()


class _MeshSubscription:
    """One merged topic subscription across the local bus and all peer links."""

    def __init__(self, mesh: MeshGossipBackend, topic: str, queue: asyncio.Queue[Any], max_queue_size: int) -> None:
        self._mesh = mesh
        self._topic = topic
        self._queue = queue
        self._max_queue_size = max_queue_size
        self._sources: dict[str, TopicSubscription] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False

    async def attach(self, name: str, backend: GossipBackend, *, retry: bool) -> None:
        try:
            source = await backend.subscribe(self._topic, max_queue_size=self._max_queue_size)
        except Exception as e:
            if not retry:
                raise
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).warning("Mesh gossip peer %s unavailable for %s; will retry: %s", name, self._topic, e)
            metrics_registry.increment("gossip_mesh_peer_subscribe_failed_total")
            self._tasks[name] = create_task_with_logging(
                self._retry_attach(name, backend),
                name=f"mesh-gossip-retry:{name}:{self._topic}",
            )
            return
        self._sources[name] = source
        self._tasks[name] = create_task_with_logging(
            self._forward(name, source),
            name=f"mesh-gossip-forward:{name}:{self._topic}",
        )

    async def _retry_attach(self, name: str, backend: GossipBackend) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        delay = self._mesh._retry_min_delay
        while not self._closed:
            await asyncio.sleep(delay)
            if self._closed:
                return
            try:
                source = await backend.subscribe(self._topic, max_queue_size=self._max_queue_size)
            except Exception as e:
                delay = min(delay * 2, self._mesh._retry_max_delay)
                logger.info("Mesh gossip peer %s still unavailable for %s (retry in %ss): %s", name, self._topic, delay, e)
                continue
            logger.info("Mesh gossip peer %s attached for %s", name, self._topic)
            self._sources[name] = source
            # Replace ourselves with the forwarding loop for this source.
            self._tasks[name] = create_task_with_logging(
                self._forward(name, source),
                name=f"mesh-gossip-forward:{name}:{self._topic}",
            )
            return

    async def _forward(self, name: str, source: TopicSubscription) -> None:
        while not self._closed:
            message = await source.queue.get()
            if await self._mesh._remember(_message_id(self._topic, message)):
                metrics_registry.increment("gossip_mesh_dedup_skipped_total")
                continue
            await self._queue.put(message)
            _set_queue_gauge(self._topic, self._queue.qsize())

    async def close(self) -> None:
        self._closed = True
        for task in self._tasks.values():
            if task is not asyncio.current_task():
                task.cancel()
        for task in self._tasks.values():
            if task is asyncio.current_task():
                continue
            with suppress(asyncio.CancelledError, asyncio.TimeoutError, Exception):
                await asyncio.wait_for(task, timeout=2.0)
        self._tasks.clear()
        for source in self._sources.values():
            with suppress(Exception):
                source.close()
        self._sources.clear()


def _peer_name(url: str) -> str:
    """Short human-readable label for a peer URL (host[:port])."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc or url


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
