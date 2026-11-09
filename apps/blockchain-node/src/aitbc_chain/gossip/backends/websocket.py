from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from contextlib import suppress
from typing import Any

from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

from ...config import settings
from .._internal import _message_id, _peer_name, bounded_topic_label
from ..gossip_auth import build_auth_message, channel_scope
from ..telemetry import (
    close_code_class,
    ensure_event_loop_lag_monitor,
    gossip_event,
    gossip_peer_ack_late_total,
    gossip_peer_connection_events_total,
    gossip_peer_publish_ack_seconds,
    gossip_peer_publish_attempts_total,
    gossip_peer_publish_terminal_total,
    gossip_peer_reconnect_attempts_total,
    gossip_peer_reconnect_delay_seconds,
)
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
        chain_id: str | None = None,
        suppress_echo_ttl: float = 5.0,
        ack_timeout: float = 10.0,
        peer_name: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # #1308: peer attribution for telemetry — mesh passes the configured
        # peer name; a bare websocket backend derives host[:port] from the URL.
        self._peer_name = peer_name or _peer_name(self._base_url)
        self._client_id = uuid.uuid4().hex
        # Chain demux (#1159): an explicit chain_id wins; otherwise a
        # ``?chain=<id>`` already present in base_url is preserved. Neither
        # means a legacy single-chain dial with no chain param.
        from urllib.parse import parse_qs, urlsplit

        base_parts = urlsplit(self._base_url)
        self._base_parts = base_parts
        query_chain = parse_qs(base_parts.query).get("chain", [None])[0]
        self._chain_id = chain_id or (query_chain.strip() if query_chain else None)
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
        # Per-worker echo dedupe (Refs #745): the same message CAN be
        # delivered once per worker — downstream tx-hash dedupe in the
        # mempool is the authority, so this map only trims the common
        # same-worker echo case.
        self._sent_message_ids: dict[str, float] = {}
        self._sent_lock = asyncio.Lock()
        self._reconnecting: set[str] = set()
        self._reconnect_backoff: dict[str, float] = {}
        self._ack_timeout = ack_timeout
        self._ack_events: dict[str, asyncio.Event] = {}
        self._ack_lock = asyncio.Lock()
        self._connect_locks: dict[str, asyncio.Lock] = {}
        # #1308: msg_ids whose ack wait already timed out, so a later echo is
        # distinguishable as a LATE ack rather than a missing one.
        self._ack_timeouts: dict[str, float] = {}

    async def start(self) -> None:
        self._running = True
        # #1308: event-loop lag sampler — the starvation signal behind the
        # synchronized 1011 bursts. Idempotent per running loop.
        ensure_event_loop_lag_monitor()

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
        late_ack = False
        async with self._ack_lock:
            ack_event = self._ack_events.get(msg_id)
            if ack_event is not None and msg_id in self._ack_timeouts:
                # #1308: this msg_id already timed out on an earlier attempt —
                # the echo is a LATE (likely cross-attempt) ack, distinguishable
                # from a missing one.
                late_ack = True
                del self._ack_timeouts[msg_id]
            now = time.monotonic()
            for k, ts in list(self._ack_timeouts.items()):
                if now - ts > self._echo_ttl:
                    del self._ack_timeouts[k]
        if ack_event is not None:
            if late_ack:
                gossip_peer_ack_late_total.labels(peer=self._peer_name, topic_class=bounded_topic_label(topic)).inc()
                gossip_event(
                    "ack_late",
                    peer=self._peer_name,
                    topic=topic,
                    event_id=msg_id,
                    _level="info",
                )
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

    def _auth_scope(self, topic: str) -> str:
        """Auth scope this dialer signs for ``topic`` (#1159, #1255).

        Neither ``gossip_auth_sign_chain_scope`` nor
        ``gossip_auth_require_chain_scope`` set → legacy chain-less scope
        (accepted by old and new servers mid-rollout). Either set → the
        canonical ``channel:<chain>:<topic>`` scope; an unbound dial falls
        back to this node's own ``settings.chain_id``, matching how the
        server resolves a missing ``?chain=`` on a single-chain host.

        ``require`` implies ``sign``: a host whose own server side rejects
        legacy signatures must not hand legacy signatures to its peers.
        """
        if not (settings.gossip_auth_sign_chain_scope or settings.gossip_auth_require_chain_scope):
            return channel_scope(topic)
        return channel_scope(topic, self._chain_id or settings.chain_id)

    def _build_url(self, topic: str) -> str:
        """Dial URL for ``topic`` — base query params preserved, ``chain``
        included when the backend is chain-bound (#1159)."""
        from urllib.parse import parse_qsl, urlencode, urlunsplit

        query = dict(parse_qsl(self._base_parts.query))
        if self._chain_id:
            query["chain"] = self._chain_id
        query["topic"] = topic
        query["client_id"] = self._client_id
        return urlunsplit(
            (
                self._base_parts.scheme,
                self._base_parts.netloc,
                self._base_parts.path,
                urlencode(query),
                self._base_parts.fragment,
            )
        )

    async def _ensure_connection_unsafe(self, topic: str) -> None:
        import websockets

        existing = self._websockets.get(topic)
        if existing is not None and self._is_websocket_open(existing):
            return
        if existing is not None:
            await self._cleanup_websocket_unsafe(topic)

        url = self._build_url(topic)
        connect_t0 = time.monotonic()
        try:
            ws = await websockets.connect(
                url,
                ssl=self._ssl_context,
                ping_interval=20,
                ping_timeout=10,
            )
        except Exception as e:
            gossip_peer_connection_events_total.labels(
                peer=self._peer_name,
                topic_class=bounded_topic_label(topic),
                event="connect_failed",
                code_class="none",
            ).inc()
            gossip_event(
                "connect_failed",
                peer=self._peer_name,
                topic=topic,
                latency_ms=round((time.monotonic() - connect_t0) * 1000.0, 1),
                error=str(e)[:120],
                _level="info",
            )
            raise RuntimeError(f"Failed to connect to gossip websocket for {topic}: {e}") from e

        try:
            await self._authenticate(topic, ws)
        except Exception as e:
            with suppress(Exception):
                await ws.close()
            raise RuntimeError(f"Gossip websocket auth failed for {topic}: {e}") from e

        self._websockets[topic] = ws
        self._readers[topic] = create_task_with_logging(
            self._reader(topic, ws),
            name=f"ws-gossip-reader:{topic}",
        )
        self._reconnect_backoff[topic] = 0.5
        gossip_peer_connection_events_total.labels(
            peer=self._peer_name,
            topic_class=bounded_topic_label(topic),
            event="connected",
            code_class="none",
        ).inc()
        gossip_event(
            "connected",
            peer=self._peer_name,
            topic=topic,
            latency_ms=round((time.monotonic() - connect_t0) * 1000.0, 1),
        )

    async def _authenticate(self, topic: str, ws: Any) -> None:
        """Perform the validator challenge/response handshake if the server requires it."""
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        proposer_id = settings.proposer_id
        proposer_key = settings.proposer_key

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=settings.gossip_auth_timeout)
        except asyncio.TimeoutError:
            # Server did not send a challenge; proceed without auth.
            logger.debug("No auth challenge from server for %s; proceeding", topic)
            return

        if not raw:
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # If the first message is not JSON, it is real data. We cannot process
            # it here (queue may not exist), but the reader will handle subsequent
            # messages. This preserves backward compatibility.
            logger.debug("Non-JSON first message on %s; skipping auth", topic)
            return

        if data.get("type") != "auth_challenge":
            # Server did not require auth; this is real traffic.
            logger.debug("No auth challenge for %s (got %s); proceeding", topic, data.get("type"))
            return

        if not proposer_id or not proposer_key:
            raise RuntimeError("Server required validator auth but PROPOSER_ID/PROPOSER_KEY not set")

        challenge = data.get("challenge", "")
        timestamp = data.get("timestamp", 0.0)
        # Scope-bound signature (#1128): this auth covers exactly this
        # connection's topic — it cannot be replayed for another. While
        # ``gossip_auth_require_chain_scope`` is off the signature stays on
        # the legacy chain-less scope so pre-#1159 servers keep accepting
        # it; once the Phase-B gate flips, every dialer signs the canonical
        # chain-bound scope matching the server's verification (#1159).
        message = build_auth_message(challenge, proposer_id, timestamp, self._auth_scope(topic))
        signature = sign_consensus_message(message, proposer_key)

        await ws.send(
            json.dumps(
                {
                    "type": "auth_response",
                    "address": canonical_address(proposer_id),
                    "signature": signature,
                    "timestamp": timestamp,
                    "challenge": challenge,
                },
                default=str,
            )
        )

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=settings.gossip_auth_timeout)
        except asyncio.TimeoutError as e:
            raise RuntimeError("Timeout waiting for auth_ok") from e

        if not raw:
            raise RuntimeError("Empty auth response")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid auth response: {e}") from e

        if data.get("type") != "auth_ok":
            raise RuntimeError(f"Auth rejected: {data}")

        logger.debug("Authenticated gossip websocket for %s as %s", topic, proposer_id)

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
            # #1308: peer-attributed close record — the churn bursts were
            # unattributable because only the topic was logged.
            gossip_peer_connection_events_total.labels(
                peer=self._peer_name,
                topic_class=bounded_topic_label(topic),
                event="closed",
                code_class=close_code_class(exc.code),
            ).inc()
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).info(
                "WebSocket gossip connection closed for %s peer=%s: code=%s reason=%s",
                topic,
                self._peer_name,
                exc.code,
                exc.reason,
            )
            gossip_event(
                "closed",
                peer=self._peer_name,
                topic=topic,
                code=exc.code,
                reason=str(exc.reason)[:120],
            )
        except Exception as e:
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).warning("WebSocket gossip reader error for %s peer=%s: %s", topic, self._peer_name, e)
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
        reschedule = False
        try:
            if not self._running or self._ref_counts.get(topic, 0) <= 0:
                return
            delay = self._reconnect_backoff.get(topic, 0.5)
            # #1308: reconnect attempt telemetry — attempts/delay/outcome per peer.
            gossip_peer_reconnect_delay_seconds.labels(peer=self._peer_name, topic_class=bounded_topic_label(topic)).observe(
                delay
            )
            gossip_peer_reconnect_attempts_total.labels(
                peer=self._peer_name, topic_class=bounded_topic_label(topic), outcome="attempt"
            ).inc()
            logger.info("WebSocket gossip reconnect for %s peer=%s after %ss", topic, self._peer_name, delay)
            gossip_event(
                "reconnect_attempt",
                peer=self._peer_name,
                topic=topic,
                delay_s=delay,
                _level="info",
            )
            sleep_t0 = time.monotonic()
            await asyncio.sleep(delay)
            sleep_overshoot = time.monotonic() - sleep_t0 - delay
            if self._ref_counts.get(topic, 0) <= 0:
                return
            await self._ensure_connection(topic)
            self._reconnect_backoff[topic] = 0.5
            gossip_peer_reconnect_attempts_total.labels(
                peer=self._peer_name, topic_class=bounded_topic_label(topic), outcome="success"
            ).inc()
            gossip_event(
                "reconnect_ok",
                peer=self._peer_name,
                topic=topic,
                sleep_overshoot_s=round(max(sleep_overshoot, 0.0), 3),
                _level="info",
            )
        except Exception as e:
            current = self._reconnect_backoff.get(topic, 0.5)
            self._reconnect_backoff[topic] = min(current * 2, 30.0)
            gossip_peer_reconnect_attempts_total.labels(
                peer=self._peer_name, topic_class=bounded_topic_label(topic), outcome="failed"
            ).inc()
            logger.warning("WebSocket gossip reconnect failed for %s peer=%s: %s", topic, self._peer_name, e)
            gossip_event(
                "reconnect_failed",
                peer=self._peer_name,
                topic=topic,
                next_delay_s=self._reconnect_backoff[topic],
                error=str(e)[:120],
                _level="info",
            )
            reschedule = True
        finally:
            # Discard before scheduling: the next task must own the marker,
            # otherwise the nested schedule is suppressed and retries stop.
            self._reconnecting.discard(topic)
            if reschedule:
                self._schedule_reconnect(topic)

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
        _attempt: int = 1,
    ) -> None:
        """Publish a message and wait for the server echo (ack).

        If the ack does not arrive within ``_ack_timeout`` seconds the send is
        considered lost, the connection is torn down and (for ``retry=True``)
        the message is resent once.

        #1308: every attempt is measured — send→ack latency, timeout vs late
        ack, retry/terminal outcome — all keyed by the deterministic message
        id so a single publish is reconstructable across attempts and nodes.
        """
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        msg_id = self._compute_message_id(topic, message)
        topic_class = bounded_topic_label(topic)
        ack_event = asyncio.Event()
        async with self._ack_lock:
            self._ack_events[msg_id] = ack_event
        outcome = "error"
        ack_latency: float | None = None
        failure: BaseException | None = None
        ack_wait_reached = False
        try:
            async with self._connect_lock(topic):
                await self._ensure_connection_unsafe(topic)
                await self._record_sent(topic, message)
                ws = self._websockets[topic]
                send_t0 = time.monotonic()
                await ws.send(json.dumps(message, default=str))
                logger.debug("Published websocket message for %s; awaiting ack", topic)
                ack_wait_reached = True
                await asyncio.wait_for(ack_event.wait(), timeout=self._ack_timeout)
                ack_latency = time.monotonic() - send_t0
                outcome = "ack"
        except asyncio.TimeoutError as e:
            # Only the ack wait counts as ack_timeout — a connect/send timeout
            # is a transport error, not a missing echo.
            outcome = "ack_timeout" if ack_wait_reached else "error"
            failure = e
        except Exception as e:
            outcome = "error"
            failure = e
        finally:
            async with self._ack_lock:
                self._ack_events.pop(msg_id, None)

        # --- telemetry (outside the connect lock; never blocks the send path)
        gossip_peer_publish_attempts_total.labels(
            peer=self._peer_name, topic_class=topic_class, attempt=str(_attempt), outcome=outcome
        ).inc()
        if outcome == "ack":
            if ack_latency is not None:
                gossip_peer_publish_ack_seconds.labels(peer=self._peer_name, topic_class=topic_class).observe(ack_latency)
            gossip_peer_publish_terminal_total.labels(peer=self._peer_name, topic_class=topic_class, outcome="acked").inc()
            gossip_event(
                "publish_ack",
                peer=self._peer_name,
                topic=topic,
                event_id=msg_id,
                attempt=_attempt,
                ack_latency_ms=round(ack_latency * 1000.0, 1),
                late=msg_id in self._ack_timeouts or None,
            )
            return

        # Missing-vs-late bookkeeping: a timed-out ack may still echo later —
        # _is_echo flags it via _ack_timeouts. Errors tear the connection down
        # so no late echo is expected on that socket.
        if outcome == "ack_timeout":
            async with self._ack_lock:
                self._ack_timeouts[msg_id] = time.monotonic()
        gossip_event(
            "publish_attempt_failed",
            peer=self._peer_name,
            topic=topic,
            event_id=msg_id,
            attempt=_attempt,
            outcome=outcome,
            error=str(failure)[:120] if failure else None,
            _level="info",
        )
        if not retry:
            gossip_peer_publish_terminal_total.labels(peer=self._peer_name, topic_class=topic_class, outcome="failed").inc()
            gossip_event(
                "publish_failed",
                peer=self._peer_name,
                topic=topic,
                event_id=msg_id,
                attempts=_attempt,
                outcome=outcome,
                _level="warning",
            )
            raise RuntimeError(f"WebSocket gossip publish/ack failed for {topic}: {failure}") from failure
        logger.info(
            "WebSocket gossip publish/ack failed for %s peer=%s attempt=%s (will retry once): %s",
            topic,
            self._peer_name,
            _attempt,
            failure,
        )
        await self._cleanup_websocket(topic)
        await self._publish_with_ack(topic, message, retry=False, _attempt=_attempt + 1)

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
