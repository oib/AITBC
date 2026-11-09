"""Gossip transport observability (#1308 WS-GOSSIP-CHURN-1).

Peer-attributed metrics and event records for the mesh/websocket gossip
path, plus an event-loop lag sampler. Everything here is additive: no
consensus inputs, no blocking work on the measured path — counters,
histograms and bounded logs only.

Event identity: ``event_id`` is the deterministic ``_message_id(topic,
message)`` already used for echo suppression, publish ack matching and
mesh/broker dedup. Because it is a pure function of (topic, message) every
hop — publisher attempts, retries, acks, mesh first-delivery and remote
dedup — computes the same id, so a single publish is reconstructable across
nodes without any envelope change.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from ._internal import bounded_topic_label

logger = logging.getLogger(__name__)

# --- metric label helpers -------------------------------------------------

_ACK_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
_LAG_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
_DELAY_BUCKETS = (0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0)

_CLOSE_CODE_CLASSES = {
    1000: "normal",
    1001: "going_away",
    1005: "no_status",
    1006: "abnormal",
    1008: "policy",
    1009: "too_big",
    1010: "unsupported",
    1011: "keepalive",
    1012: "service_restart",
    1013: "try_again",
    1014: "bad_gateway",
    1015: "tls",
}


def close_code_class(code: int | None) -> str:
    """Bounded label class for a WebSocket close code."""
    if code is None:
        return "none"
    return _CLOSE_CODE_CLASSES.get(code, "other")


def _peer_label(peer: str | None) -> str:
    """Bounded peer label: configured peer names are URL netlocs; anything
    empty/unset collapses to ``unknown`` so label cardinality stays bounded."""
    return peer or "unknown"


# --- metrics ---------------------------------------------------------------

gossip_peer_publish_attempts_total = Counter(
    "blockchain_gossip_peer_publish_attempts_total",
    "Per-peer gossip publish attempts by outcome (ack, ack_timeout, error)",
    ["peer", "topic_class", "attempt", "outcome"],
)
gossip_peer_publish_terminal_total = Counter(
    "blockchain_gossip_peer_publish_terminal_total",
    "Terminal outcome of a peer publish after all retries",
    ["peer", "topic_class", "outcome"],
)
gossip_peer_publish_ack_seconds = Histogram(
    "blockchain_gossip_peer_publish_ack_seconds",
    "Peer publish send-to-echo-ack latency per attempt",
    ["peer", "topic_class"],
    buckets=_ACK_BUCKETS,
)
gossip_peer_ack_late_total = Counter(
    "blockchain_gossip_peer_ack_late_total",
    "Echo acks observed for a message id that already timed out (late/cross-attempt ack)",
    ["peer", "topic_class"],
)
gossip_peer_reconnect_attempts_total = Counter(
    "blockchain_gossip_peer_reconnect_attempts_total",
    "Peer websocket reconnect attempts by outcome",
    ["peer", "topic_class", "outcome"],
)
gossip_peer_reconnect_delay_seconds = Histogram(
    "blockchain_gossip_peer_reconnect_delay_seconds",
    "Backoff delay chosen before each peer reconnect attempt",
    ["peer", "topic_class"],
    buckets=_DELAY_BUCKETS,
)
gossip_peer_connection_events_total = Counter(
    "blockchain_gossip_peer_connection_events_total",
    "Peer websocket connection lifecycle events",
    ["peer", "topic_class", "event", "code_class"],
)
gossip_mesh_message_forward_total = Counter(
    "blockchain_gossip_mesh_message_forward_total",
    "First-delivery (non-duplicate) gossip messages forwarded into the merged subscription queue, by source link",
    ["source", "topic_class"],
)
gossip_event_loop_lag_seconds = Histogram(
    "blockchain_gossip_event_loop_lag_seconds",
    "Event-loop scheduling lag samples (sleep overshoot) — starvation detector",
    buckets=_LAG_BUCKETS,
)
gossip_event_loop_lag_max_seconds = Gauge(
    "blockchain_gossip_event_loop_lag_max_seconds",
    "Maximum event-loop lag observed since process start",
)
gossip_event_loop_lag_count = Gauge(
    "blockchain_gossip_event_loop_lag_samples_total",
    "Number of event-loop lag samples recorded",
)


# --- structured event log ---------------------------------------------------


def gossip_event(
    event: str, *, peer: str | None = None, topic: str | None = None, event_id: str | None = None, **fields: Any
) -> None:
    """Emit one greppable gossip telemetry event.

    Routine lifecycle events log at DEBUG; anomalous outcomes (timeouts,
    retries exhausted, connection failures) log at INFO/WARNING so journals
    stay readable at default level while full reconstruction stays possible
    at DEBUG.
    """
    level = fields.pop("_level", None)
    parts = [f"gossip_evt event={event}"]
    if peer:
        parts.append(f"peer={peer}")
    if topic:
        parts.append(f"topic={bounded_topic_label(topic)}")
    if event_id:
        # event ids are "topic:digest" — keep them whole for cross-node
        # correlation; they are already content-addressed and bounded.
        parts.append(f"id={event_id}")
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    msg = " ".join(parts)
    if level == "warning":
        logger.warning("%s", msg)
    elif level == "info":
        logger.info("%s", msg)
    else:
        logger.debug("%s", msg)


# --- event-loop lag monitor -------------------------------------------------


class EventLoopLagMonitor:
    """Samples ``asyncio.sleep`` overshoot — the starvation signal behind the
    synchronized 1011 keepalive bursts (#1308).

    Non-blocking by construction: one sleeping task, counter/histogram/gauge
    updates only. ``record_lag`` is separated from the loop so tests can
    inject arbitrary lag values.
    """

    def __init__(self, interval: float = 0.25, window: int = 2048) -> None:
        self._interval = interval
        self._samples: deque[float] = deque(maxlen=window)
        self._max = 0.0
        self._count = 0
        self._task: asyncio.Task[None] | None = None

    def record_lag(self, lag: float) -> None:
        """Record one lag sample (seconds). Cheap: deque append + gauge set."""
        if lag < 0:
            lag = 0.0
        self._samples.append(lag)
        self._count += 1
        if lag > self._max:
            self._max = lag
        gossip_event_loop_lag_seconds.observe(lag)
        gossip_event_loop_lag_max_seconds.set(self._max)
        gossip_event_loop_lag_count.set(float(self._count))

    def percentile(self, q: float) -> float | None:
        """Nearest-rank percentile over retained samples (for tests/diagnostics)."""
        if not self._samples:
            return None
        ordered = sorted(self._samples)
        idx = min(len(ordered) - 1, max(0, int(q * len(ordered) + 0.999999) - 1))
        return ordered[idx]

    @property
    def max_lag(self) -> float:
        return self._max

    @property
    def sample_count(self) -> int:
        return self._count

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        expected = loop.time() + self._interval
        while True:
            await asyncio.sleep(self._interval)
            now = loop.time()
            lag = now - expected
            expected = now + self._interval
            self.record_lag(lag)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="gossip-event-loop-lag")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


_monitors: dict[int, EventLoopLagMonitor] = {}


def ensure_event_loop_lag_monitor(interval: float = 0.25) -> EventLoopLagMonitor:
    """Return the lag monitor for the running loop, starting it if needed.

    Idempotent per event loop — safe to call from every backend ``start()``.
    """
    loop = asyncio.get_running_loop()
    key = id(loop)
    monitor = _monitors.get(key)
    if monitor is None:
        monitor = EventLoopLagMonitor(interval=interval)
        _monitors[key] = monitor
    monitor.start()
    return monitor


def event_loop_lag_monitor_for_tests() -> EventLoopLagMonitor | None:
    """Test hook: the monitor bound to the current loop, if any."""
    return _monitors.get(id(asyncio.get_running_loop()))
