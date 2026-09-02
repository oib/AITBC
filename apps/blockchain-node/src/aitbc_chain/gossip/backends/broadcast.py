from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from typing import Any

from aitbc.async_tasks import create_task_with_logging

from ...metrics import metrics_registry
from .._internal import (
    _decode_batch,
    _encode_batch,
    _encode_message,
    _increment_publication,
    _set_queue_gauge,
)
from .base import GossipBackend, TopicSubscription


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
