from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from contextlib import suppress
from typing import Any

from aitbc.async_tasks import create_task_with_logging

from .._internal import _message_id
from .base import GossipBackend, TopicSubscription


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
