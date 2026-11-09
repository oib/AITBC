"""#1308 WS-GOSSIP-CHURN-1 observability instrumentation tests.

Injection tests proving the telemetry works: peer-attributed ack timing,
missing-vs-late ack distinction, retry/terminal outcomes, reconnect metrics,
event-loop lag sampling, and mesh publish/forward event-id correlation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from aitbc_chain.gossip.backends.mesh import MeshGossipBackend
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.gossip.broker import create_backend
from aitbc_chain.gossip.telemetry import (
    EventLoopLagMonitor,
    close_code_class,
    ensure_event_loop_lag_monitor,
    event_loop_lag_monitor_for_tests,
    gossip_event_loop_lag_max_seconds,
    gossip_mesh_message_forward_total,
    gossip_peer_ack_late_total,
    gossip_peer_publish_ack_seconds,
    gossip_peer_publish_attempts_total,
    gossip_peer_publish_terminal_total,
    gossip_peer_reconnect_attempts_total,
    gossip_peer_reconnect_delay_seconds,
)

TOPIC = "status"


def _counter(name, **labels):
    return name.labels(**labels)._value.get()


def _hist_sample(name, suffix, **labels):
    """Read a histogram _count/_sum sample matching the given labels via
    collect() — the child object's internal bucket storage is not stable
    across prometheus_client versions."""
    for family in name.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix) and all(sample.labels.get(k) == str(v) for k, v in labels.items()):
                return sample.value
    return 0.0


def _hist_sum(name, **labels):
    return _hist_sample(name, "_sum", **labels)


def _hist_count(name, **labels):
    return _hist_sample(name, "_count", **labels)


class _FakeWS:
    """Minimal websocket stand-in: records sends, optionally echoes the
    message back through the backend's real ``_is_echo`` path after a delay."""

    def __init__(self, backend: WebsocketGossipBackend, topic: str, echo_delay: float | None):
        self._backend = backend
        self._topic = topic
        self._echo_delay = echo_delay
        self.sent: list[dict] = []

    async def send(self, payload: str) -> None:
        message = json.loads(payload)
        self.sent.append(message)
        if self._echo_delay is None:
            return

        async def _echo() -> None:
            await asyncio.sleep(self._echo_delay)
            await self._backend._is_echo(self._topic, message)

        asyncio.get_running_loop().create_task(_echo())

    async def close(self, close_timeout: float | None = None) -> None:
        return None


def _backend(peer: str, ack_timeout: float = 5.0, echo_delay: float | None = None) -> WebsocketGossipBackend:
    backend = WebsocketGossipBackend("ws://127.0.0.1:9/rpc/gossip/ws", ack_timeout=ack_timeout, peer_name=peer)
    backend._running = True

    async def fake_ensure(topic: str) -> None:
        backend._websockets[topic] = _FakeWS(backend, topic, echo_delay)

    backend._ensure_connection_unsafe = fake_ensure  # type: ignore[method-assign]
    return backend


@pytest.mark.asyncio
async def test_publish_ack_timing_and_peer_attribution(caplog):
    peer = "ack-peer-1"
    backend = _backend(peer, ack_timeout=2.0, echo_delay=0.01)
    message = {"type": "attest", "n": 1}
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        await backend._publish_with_ack(TOPIC, message, retry=False)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _hist_count(gossip_peer_publish_ack_seconds, **labels) == 1
    assert _hist_sum(gossip_peer_publish_ack_seconds, **labels) > 0
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="acked") == 1
    events = [r.getMessage() for r in caplog.records if "gossip_evt" in r.getMessage()]
    ack_events = [e for e in events if "event=publish_ack" in e]
    assert ack_events, events
    assert f"peer={peer}" in ack_events[0]
    assert "ack_latency_ms=" in ack_events[0]


@pytest.mark.asyncio
async def test_ack_timeout_then_late_echo_is_distinguishable(caplog):
    """Attempt 1 times out; the echo lands during attempt 2 — must be counted
    as a LATE ack (timeout marker present), not a clean ack."""
    peer = "late-peer-1"
    # attempt1 window 0.05s; echo at 0.09s lands inside attempt2's window.
    backend = _backend(peer, ack_timeout=0.05, echo_delay=0.09)
    # Only echo on the FIRST send; second attempt acks via the same late echo.
    sends = {"n": 0}
    orig_send = _FakeWS.send

    class _EchoOnceWS(_FakeWS):
        async def send(self, payload: str) -> None:
            sends["n"] += 1
            if sends["n"] == 1:
                message = json.loads(payload)
                self.sent.append(message)

                async def _echo() -> None:
                    await asyncio.sleep(0.09)
                    await self._backend._is_echo(self._topic, message)

                asyncio.get_running_loop().create_task(_echo())
            else:
                await orig_send(self, payload)

    async def fake_ensure(topic: str) -> None:
        backend._websockets[topic] = _EchoOnceWS(backend, topic, None)

    backend._ensure_connection_unsafe = fake_ensure  # type: ignore[method-assign]
    message = {"type": "attest", "n": 2}
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        await backend._publish_with_ack(TOPIC, message, retry=True)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="2", outcome="ack") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="acked") == 1
    # The echo arrived after attempt 1's timeout → late-ack counter fired.
    assert _counter(gossip_peer_ack_late_total, **labels) == 1
    assert any("event=ack_late" in e and f"peer={peer}" in e for e in events)


@pytest.mark.asyncio
async def test_missing_ack_terminal_failure(caplog):
    """No echo ever → both attempts time out → terminal failure, no late ack."""
    peer = "miss-peer-1"
    backend = _backend(peer, ack_timeout=0.03, echo_delay=None)
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        with pytest.raises(RuntimeError):
            await backend._publish_with_ack(TOPIC, {"type": "x"}, retry=True)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="2", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="failed") == 1
    assert _counter(gossip_peer_ack_late_total, **labels) == 0
    assert any("event=publish_failed" in e for e in events)


@pytest.mark.asyncio
async def test_reconnect_attempt_metrics(caplog):
    peer = "recon-peer-1"
    backend = WebsocketGossipBackend("ws://127.0.0.1:9/rpc/gossip/ws", peer_name=peer)
    backend._running = True
    backend._ref_counts[TOPIC] = 1
    backend._queues[TOPIC] = asyncio.Queue()
    backend._reconnect_backoff[TOPIC] = 0.001
    attempts = {"n": 0}

    async def flaky_ensure(topic: str) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")

    backend._ensure_connection = flaky_ensure  # type: ignore[method-assign]
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        backend._schedule_reconnect(TOPIC)
        for _ in range(100):
            if attempts["n"] >= 2:
                break
            await asyncio.sleep(0.01)
        events = [r.getMessage() for r in caplog.records]
    backend._running = False
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_reconnect_attempts_total, **labels, outcome="failed") >= 1
    assert _counter(gossip_peer_reconnect_attempts_total, **labels, outcome="success") >= 1
    assert _hist_count(gossip_peer_reconnect_delay_seconds, **labels) >= 1
    assert any("event=reconnect_attempt" in e and f"peer={peer}" in e for e in events)


@pytest.mark.asyncio
async def test_event_loop_lag_monitor_samples_and_percentiles():
    monitor = EventLoopLagMonitor(interval=0.01)
    monitor.record_lag(0.05)
    monitor.record_lag(0.5)
    monitor.record_lag(0.1)
    assert monitor.sample_count == 3
    assert monitor.max_lag == 0.5
    assert monitor.percentile(1.0) == 0.5
    assert gossip_event_loop_lag_max_seconds._value.get() >= 0.5

    # Live sampler: starts on the running loop, records real overshoot.
    ensure_event_loop_lag_monitor(interval=0.01)
    monitor2 = event_loop_lag_monitor_for_tests()
    assert monitor2 is not None
    await asyncio.sleep(0.05)
    assert monitor2.sample_count >= 1
    monitor2.stop()


def test_close_code_class_bounded():
    assert close_code_class(1011) == "keepalive"
    assert close_code_class(1006) == "abnormal"
    assert close_code_class(4999) == "other"
    assert close_code_class(None) == "none"


@pytest.mark.asyncio
async def test_mesh_publish_spawn_attributes_peer_and_event_id(caplog):
    """Mesh peer publish carries peer name + deterministic event id."""
    from aitbc_chain.gossip.backends.base import GossipBackend, TopicSubscription

    class _Local(GossipBackend):
        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    published: list[tuple[str, Any]] = []

    class _Peer(GossipBackend):
        async def publish(self, topic, message):
            published.append((topic, message))

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    mesh = MeshGossipBackend(_Local(), {"peer-x:443": _Peer()})
    mesh._running = True
    message = {"type": "ping", "v": 7}
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        await mesh.publish(TOPIC, message)
        for _ in range(100):
            if published:
                break
            await asyncio.sleep(0.01)
        events = [r.getMessage() for r in caplog.records]
    assert published == [(TOPIC, message)]
    done = [e for e in events if "event=publish_done" in e]
    assert done and "peer=peer-x:443" in done[0]
    assert "id=" in done[0]


@pytest.mark.asyncio
async def test_mesh_forward_attributes_source_and_event_id(caplog):
    """Receiver side: first delivery logs source link + same event id."""
    from aitbc_chain.gossip.backends.base import GossipBackend, TopicSubscription

    class _Stub(GossipBackend):
        def __init__(self):
            self.queues: dict[str, asyncio.Queue] = {}

        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            q = self.queues.setdefault(topic, asyncio.Queue())
            return TopicSubscription(topic, q, lambda: None)

    local, peer = _Stub(), _Stub()
    mesh = MeshGossipBackend(local, {"peer-y:443": peer})
    mesh._running = True
    with caplog.at_level(logging.DEBUG, logger="aitbc_chain.gossip.telemetry"):
        sub = await mesh.subscribe(TOPIC, max_queue_size=10)
        message = {"type": "block", "hash": "0xabc"}
        peer.queues[TOPIC].put_nowait(message)
        got = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
        assert got == message
        # Second delivery of the same message is deduped — only one forward event.
        local.queues[TOPIC].put_nowait(message)
        await asyncio.sleep(0.05)
        events = [r.getMessage() for r in caplog.records]
    labels = {"source": "peer-y:443", "topic_class": TOPIC}
    assert _counter(gossip_mesh_message_forward_total, **labels) == 1
    fwd = [e for e in events if "event=message_forward" in e]
    assert fwd and "peer=peer-y:443" in fwd[0] and "id=" in fwd[0]
    sub.close()


def test_create_backend_passes_peer_name():
    mesh = create_backend(
        "mesh",
        broadcast_url="redis://127.0.0.1:6379",
        mesh_peer_urls=["ws://peer-one:8080/rpc/gossip/ws", "wss://peer-two:443/x"],
    )
    assert set(mesh.peer_names) == {"peer-one:8080", "peer-two:443"}
    for name, peer in mesh._peers.items():
        assert peer._peer_name == name  # type: ignore[attr-defined]
