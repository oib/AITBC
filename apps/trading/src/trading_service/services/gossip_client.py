"""Minimal gossip client for the trading service (v0.8.2 §B18).

Subscribes to Redis pub/sub topics (``offers.{chain_id}``) to receive
offer events published by the blockchain-node gossip broker.

The blockchain-node's ``GossipBroker`` / ``BroadcastGossipBackend``
(``apps/blockchain-node/src/aitbc_chain/gossip/broker.py``) lives in a
separate app package and imports blockchain-node-specific config/metrics,
so it cannot be imported directly here.  Instead, this module implements
a minimal Redis pub/sub subscriber that is wire-compatible with the
blockchain-node's message encoding (``GZ:``-prefixed base64 gzip, or
plain JSON — see ``aitbc_chain/network/compression.py``).

When Redis is unavailable the client gracefully degrades to an in-memory
``asyncio.Queue`` so the service keeps running (and tests pass without a
Redis instance).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections import defaultdict
from typing import Any

from aitbc.network import decompress_json

logger = logging.getLogger(__name__)

# Magic prefix that marks a compressed payload (mirrors blockchain-node).
COMPRESSION_PREFIX = "GZ:"


def _decode_payload(data: Any) -> Any:
    """Decode a Redis pub/sub message into a Python object.

    Handles the ``GZ:``-prefixed base64 gzip format used by the
    blockchain-node gossip broker, as well as plain JSON and raw strings.
    """
    if isinstance(data, bytes | bytearray):
        data = data.decode("utf-8")
    if isinstance(data, str):
        if data.startswith(COMPRESSION_PREFIX):
            try:
                compressed = base64.b64decode(data[len(COMPRESSION_PREFIX) :])
                return decompress_json(compressed)
            except Exception:
                pass  # fall through to JSON parse
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data
    return data


class GossipSubscription:
    """A handle to a gossip topic subscription.

    Wraps an ``asyncio.Queue`` that receives decoded messages.  Call
    ``close()`` to unsubscribe and stop the background Redis listener.
    """

    def __init__(self, topic: str, queue: asyncio.Queue[Any], close_fn: Any) -> None:
        self.topic = topic
        self._queue = queue
        self._close_fn = close_fn

    @property
    def queue(self) -> asyncio.Queue[Any]:
        return self._queue

    async def get(self, timeout: float | None = None) -> Any:
        """Get the next message, optionally with a timeout."""
        if timeout is not None:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        return await self._queue.get()

    def close(self) -> None:
        """Unsubscribe and release resources."""
        try:
            self._close_fn()
        except Exception:
            logger.debug("Error closing gossip subscription for %s", self.topic, exc_info=True)


class GossipClient:
    """Minimal Redis pub/sub gossip client for the trading service.

    On startup, attempts to connect to Redis.  If the connection fails,
    falls back to an in-memory backend so the service remains functional
    (events can be injected via ``publish_local``).
    """

    def __init__(self, backend: str = "broadcast", redis_url: str = "redis://localhost:6379") -> None:
        self._backend = backend.lower()
        self._redis_url = redis_url
        self._redis: Any = None
        self._started = False
        # In-memory fallback topics (used when Redis is unavailable)
        self._mem_topics: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._mem_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def using_redis(self) -> bool:
        """True if the Redis backend is active (not in-memory fallback)."""
        return self._redis is not None

    async def start(self) -> None:
        """Start the gossip client — connect to Redis if configured."""
        if self._started:
            return
        if self._backend in {"broadcast", "redis"}:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.Redis.from_url(self._redis_url, socket_timeout=5, socket_connect_timeout=5)
                await asyncio.to_thread(lambda: None)  # yield
                pong = await self._redis.ping()
                logger.info("GossipClient connected to Redis (%s): ping=%s", self._redis_url, pong)
            except Exception as e:
                logger.warning("GossipClient Redis connection failed (%s), using in-memory fallback: %s", self._redis_url, e)
                self._redis = None
        self._started = True

    async def stop(self) -> None:
        """Stop the gossip client and release resources."""
        self._started = False
        for task in list(self._tasks):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
        async with self._mem_lock:
            self._mem_topics.clear()
        logger.info("GossipClient stopped")

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> GossipSubscription:
        """Subscribe to a gossip topic.

        Returns a ``GossipSubscription`` whose queue receives decoded
        messages.  When Redis is active, a background task listens to the
        Redis pub/sub channel and pushes decoded messages.  When in
        fallback mode, messages arrive via ``publish_local``.
        """
        if not self._started:
            await self.start()
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)

        if self._redis is not None:
            stop_event = asyncio.Event()

            async def _listen() -> None:
                try:
                    import redis.asyncio as aioredis

                    sub_redis = aioredis.Redis.from_url(self._redis_url, socket_timeout=None, socket_connect_timeout=5)
                    pubsub = sub_redis.pubsub()
                    await pubsub.subscribe(topic)
                    logger.info("GossipClient subscribed to Redis topic: %s", topic)
                    async for message in pubsub.listen():
                        if stop_event.is_set():
                            break
                        if message["type"] != "message":
                            continue
                        try:
                            decoded = _decode_payload(message["data"])
                            # Handle batched messages (list) or single (dict)
                            if isinstance(decoded, list):
                                for item in decoded:
                                    await queue.put(item)
                            else:
                                await queue.put(decoded)
                        except Exception:
                            logger.debug("Error decoding gossip message for %s", topic, exc_info=True)
                    try:
                        await pubsub.unsubscribe(topic)
                        await sub_redis.aclose()
                    except Exception:
                        pass
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning("GossipClient Redis subscription error for %s: %s", topic, e)

            task = asyncio.create_task(_listen(), name=f"gossip-sub-{topic}")
            self._tasks.add(task)

            def _close() -> None:
                stop_event.set()
                task.cancel()

            return GossipSubscription(topic=topic, queue=queue, close_fn=_close)

        # In-memory fallback
        async with self._mem_lock:
            self._mem_topics[topic].append(queue)

        def _close_mem() -> None:
            async def _remove() -> None:
                async with self._mem_lock:
                    queues = self._mem_topics.get(topic)
                    if queues and queue in queues:
                        queues.remove(queue)
                        if not queues:
                            self._mem_topics.pop(topic, None)

            asyncio.create_task(_remove())

        return GossipSubscription(topic=topic, queue=queue, close_fn=_close_mem)

    async def publish_local(self, topic: str, message: Any) -> None:
        """Publish a message to in-memory subscribers (fallback mode only).

        This is used by tests and by ``publish_event`` to inject events
        without a real Redis backend.
        """
        async with self._mem_lock:
            queues = list(self._mem_topics.get(topic, []))
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Gossip in-memory queue full for topic %s, dropping", topic)
