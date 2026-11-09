"""#1308 WS-GOSSIP-CHURN-1 observability instrumentation tests (respin).

Injection tests proving the telemetry works, per E's c22235-22248 review:
peer-attributed ack timing with magnitude, attempt-correlated late-ack
distinction, retry delay/age fields, peer-specific failure isolation,
real event-loop starvation during an ack wait, connect-error vs
ack-timeout classification, and stable event-id correlation across
publish/ack/receiver hops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.gossip._internal import _message_id, bounded_topic_label
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from aitbc_chain.gossip.backends.base import GossipBackend, TopicSubscription
from aitbc_chain.gossip.backends.mesh import MeshGossipBackend
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.gossip.broker import create_backend
from aitbc_chain.gossip.telemetry import (
    EventLoopLagMonitor,
    close_code_class,
    ensure_event_loop_lag_monitor,
    event_loop_lag_monitor_for_tests,
    gossip_event_loop_lag_max_seconds,
    gossip_mesh_cap_terminal_total,
    gossip_mesh_message_forward_total,
    gossip_peer_ack_late_total,
    gossip_peer_publish_ack_seconds,
    gossip_peer_publish_attempts_total,
    gossip_peer_publish_retry_delay_seconds,
    gossip_peer_publish_terminal_total,
    gossip_peer_reconnect_attempts_total,
    gossip_peer_reconnect_delay_seconds,
    gossip_ws_echo_forward_failed_total,
    gossip_ws_echo_forward_total,
    gossip_ws_rx_publish_total,
    gossip_ws_subscriber_queue_depth,
)

TOPIC = "status"
TELEMETRY_LOGGER = "aitbc_chain.gossip.telemetry"


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


def _events(caplog, name: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if f"event={name}" in r.getMessage()]


class _FakeWS:
    """Minimal websocket stand-in: records sends, optionally echoes the
    message back through the backend's real ``_is_echo`` path after a delay.

    ``echo_delays`` is consumed per send (last value repeats); ``on_send``
    runs extra injections (e.g. loop-blocking starvation) per send.
    """

    def __init__(
        self,
        backend: WebsocketGossipBackend,
        topic: str,
        echo_delays: list[float | None] | float | None,
        on_send=None,
    ):
        self._backend = backend
        self._topic = topic
        # Keep the LIST reference (not a copy): a reconnect builds a new
        # _FakeWS but the delay schedule must continue across attempts.
        self._echo_delays = echo_delays if isinstance(echo_delays, list) else [echo_delays]
        self._on_send = on_send
        self.sent: list[dict] = []

    async def send(self, payload: str) -> None:
        message = json.loads(payload)
        self.sent.append(message)
        delay = self._echo_delays.pop(0) if len(self._echo_delays) > 1 else self._echo_delays[0]
        if self._on_send is not None:
            self._on_send(self._backend, self._topic, message)
        if delay is None:
            return

        async def _echo() -> None:
            await asyncio.sleep(delay)
            await self._backend._is_echo(self._topic, message)

        asyncio.get_running_loop().create_task(_echo())

    async def close(self, close_timeout: float | None = None) -> None:
        return None


def _backend(
    peer: str,
    ack_timeout: float = 5.0,
    echo_delays: list[float | None] | float | None = 0.01,
    on_send=None,
) -> WebsocketGossipBackend:
    backend = WebsocketGossipBackend("ws://127.0.0.1:9/rpc/gossip/ws", ack_timeout=ack_timeout, peer_name=peer)
    backend._running = True
    # One shared schedule across reconnects: _ensure_connection_unsafe builds
    # a fresh _FakeWS per connection but pops continue the same list.
    delays = echo_delays if isinstance(echo_delays, list) else [echo_delays]

    async def fake_ensure(topic: str) -> None:
        backend._websockets[topic] = _FakeWS(backend, topic, delays, on_send)

    backend._ensure_connection_unsafe = fake_ensure  # type: ignore[method-assign]
    return backend


@pytest.mark.asyncio
async def test_publish_ack_timing_peer_attribution_and_event_id(caplog):
    peer = "ack-peer-1"
    backend = _backend(peer, ack_timeout=2.0, echo_delays=0.05)
    message = {"type": "attest", "n": 1}
    expected_id = _message_id(TOPIC, message)
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        await backend._publish_with_ack(TOPIC, message, retry=False)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _hist_count(gossip_peer_publish_ack_seconds, **labels) == 1
    # Magnitude, not just presence: a ~50 ms injected delay must show up.
    assert 0.03 <= _hist_sum(gossip_peer_publish_ack_seconds, **labels) <= 2.0
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="acked") == 1
    ack_events = _events(caplog, "publish_ack")
    assert ack_events, events
    assert f"peer={peer}" in ack_events[0]
    assert f"id={expected_id}" in ack_events[0]
    assert "ack_latency_ms=" in ack_events[0]
    assert "prior_timed_out_attempt=None" in ack_events[0]


@pytest.mark.asyncio
async def test_attempt2_normal_ack_is_not_a_late_ack(caplog):
    """E's c22240 killer case: attempt 1 times out, attempt 2 acks normally —
    that ack is attempt 2's OWN echo and must NOT count as late."""
    peer = "late-peer-1"
    # First send: no echo (timeout). Second send: timely echo.
    backend = _backend(peer, ack_timeout=0.05, echo_delays=[None, 0.01])
    message = {"type": "attest", "n": 2}
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        await backend._publish_with_ack(TOPIC, message, retry=True)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="2", outcome="ack") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="acked") == 1
    # The corrected semantics: no late ack — attempt 2's echo is its own.
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="1") == 0
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="2") == 0
    # Retry bookkeeping: delay histogram + publish_retry event + age fields.
    assert _hist_count(gossip_peer_publish_retry_delay_seconds, **labels) >= 1
    assert _events(caplog, "publish_retry")
    ack_events = _events(caplog, "publish_ack")
    assert ack_events and "attempt=2" in ack_events[0]
    # The ack followed a timed-out attempt 1 — recorded, not counted late.
    assert "prior_timed_out_attempt=1" in ack_events[0]
    assert any("attempt_age_ms=" in e for e in events)


@pytest.mark.asyncio
async def test_late_echo_after_terminal_timeout_is_attributed(caplog):
    """The only observable late ack: an echo arriving after the FINAL
    attempt timed out (socket stays open on terminal failure)."""
    peer = "late-peer-2"
    backend = _backend(peer, ack_timeout=0.03, echo_delays=None)
    message = {"type": "attest", "n": 3}
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        with pytest.raises(RuntimeError):
            await backend._publish_with_ack(TOPIC, message, retry=False)
        # Simulate the delayed echo arriving on the still-open socket.
        await backend._is_echo(TOPIC, message)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="failed") == 1
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="1") == 1
    late_events = _events(caplog, "ack_late")
    assert late_events
    assert "attempt=1" in late_events[0]
    assert f"id={_message_id(TOPIC, message)}" in late_events[0]
    assert any("event=publish_failed" in e for e in events)


@pytest.mark.asyncio
async def test_missing_ack_terminal_failure(caplog):
    """No echo ever → both attempts time out → terminal failure, no late ack."""
    peer = "miss-peer-1"
    backend = _backend(peer, ack_timeout=0.03, echo_delays=None)
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        with pytest.raises(RuntimeError):
            await backend._publish_with_ack(TOPIC, {"type": "x"}, retry=True)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="2", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="failed") == 1
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="1") == 0
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="2") == 0
    assert any("event=publish_failed" in e for e in events)


@pytest.mark.asyncio
async def test_connect_failure_is_error_not_ack_timeout(caplog):
    """Kills the ack_wait_reached mutant: a connect failure must be outcome
    'error', never 'ack_timeout'."""
    peer = "connfail-peer"
    backend = WebsocketGossipBackend("ws://127.0.0.1:9/rpc/gossip/ws", ack_timeout=0.05, peer_name=peer)
    backend._running = True

    async def fail_ensure(topic: str) -> None:
        raise RuntimeError("connection refused")

    backend._ensure_connection_unsafe = fail_ensure  # type: ignore[method-assign]
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        with pytest.raises(RuntimeError):
            await backend._publish_with_ack(TOPIC, {"type": "x"}, retry=True)
        events = [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="error") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="2", outcome="error") == 1
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 0
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="failed") == 1
    assert any("event=publish_attempt_failed" in e and "outcome=error" in e for e in events)


@pytest.mark.asyncio
async def test_peer_specific_failure_isolation(caplog):
    """Two peers, one failing: the healthy peer's series must be untouched."""
    good_peer, bad_peer = "iso-good", "iso-bad"
    good = _backend(good_peer, ack_timeout=2.0, echo_delays=0.01)
    bad = _backend(bad_peer, ack_timeout=0.03, echo_delays=None)
    message = {"type": "attest", "n": 42}
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        await good._publish_with_ack(TOPIC, message, retry=False)
        with pytest.raises(RuntimeError):
            await bad._publish_with_ack(TOPIC, {"type": "attest", "n": 43}, retry=False)
    good_labels = {"peer": good_peer, "topic_class": TOPIC}
    bad_labels = {"peer": bad_peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_terminal_total, **good_labels, outcome="acked") == 1
    assert _counter(gossip_peer_publish_terminal_total, **bad_labels, outcome="failed") == 1
    # No cross-talk: the bad peer's timeout did not touch the good peer's
    # ack histogram or terminal counters.
    assert _hist_count(gossip_peer_publish_ack_seconds, **bad_labels) == 0
    assert _counter(gossip_peer_publish_attempts_total, **good_labels, attempt="1", outcome="ack_timeout") == 0


@pytest.mark.asyncio
async def test_event_loop_starvation_during_ack_wait(caplog):
    """Real starvation injection: a synchronous loop block longer than the
    ack timeout must surface as lag AND explain the ack_timeout — the two
    signals are recorded separately so starvation is separable from latency."""
    peer = "starve-peer"
    ensure_event_loop_lag_monitor(interval=0.01)
    monitor = event_loop_lag_monitor_for_tests()
    assert monitor is not None
    lag_before = monitor.max_lag

    def _starve(backend, topic, message):
        loop = asyncio.get_running_loop()

        async def _block() -> None:
            time.sleep(0.25)  # freezes the whole loop past the 0.05s ack wait

        loop.create_task(_block())

    backend = _backend(peer, ack_timeout=0.05, echo_delays=0.01, on_send=_starve)
    message = {"type": "attest", "n": 7}
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        with pytest.raises(RuntimeError):
            await backend._publish_with_ack(TOPIC, message, retry=False)
        # The echo was scheduled at +10 ms but could not run during the
        # 250 ms block; it arrives after the timeout → true late ack.
        await asyncio.sleep(0.05)
        [r.getMessage() for r in caplog.records]
    labels = {"peer": peer, "topic_class": TOPIC}
    assert _counter(gossip_peer_publish_attempts_total, **labels, attempt="1", outcome="ack_timeout") == 1
    assert _counter(gossip_peer_publish_terminal_total, **labels, outcome="failed") == 1
    # Starvation recorded independently of the ack outcome.
    assert monitor.max_lag > lag_before
    assert monitor.max_lag >= 0.15
    assert gossip_event_loop_lag_max_seconds._value.get() >= 0.15
    # And the delayed echo is a late ack attributed to attempt 1.
    assert _counter(gossip_peer_ack_late_total, **labels, attempt="1") == 1
    assert _events(caplog, "ack_late")


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
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
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
    published: list[tuple[str, Any]] = []

    class _Local(GossipBackend):
        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    class _Peer(GossipBackend):
        async def publish(self, topic, message):
            published.append((topic, message))

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    mesh = MeshGossipBackend(_Local(), {"peer-x:443": _Peer()})
    mesh._running = True
    message = {"type": "ping", "v": 7}
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        await mesh.publish(TOPIC, message)
        for _ in range(100):
            if published:
                break
            await asyncio.sleep(0.01)
        [r.getMessage() for r in caplog.records]
    assert published == [(TOPIC, message)]
    done = _events(caplog, "peer_publish_done")
    assert done and "peer=peer-x:443" in done[0]
    assert f"id={_message_id(TOPIC, message)}" in done[0]


@pytest.mark.asyncio
async def test_mesh_publish_dropped_event(caplog):
    """Inflight-full peer publish emits peer_publish_dropped, not done."""

    class _Local(GossipBackend):
        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    class _Peer(GossipBackend):
        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    mesh = MeshGossipBackend(_Local(), {"peer-drop": _Peer()}, max_inflight_per_peer=0)
    mesh._running = True
    with caplog.at_level(logging.WARNING, logger=TELEMETRY_LOGGER):
        await mesh.publish(TOPIC, {"type": "x"})
        await asyncio.sleep(0.05)
    dropped = _events(caplog, "peer_publish_dropped")
    assert dropped and "peer=peer-drop" in dropped[0]
    assert not _events(caplog, "peer_publish_done")


@pytest.mark.asyncio
async def test_mesh_forward_attributes_source_and_event_id(caplog):
    """Receiver side: first delivery logs source link + same event id."""

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
    with caplog.at_level(logging.INFO, logger=TELEMETRY_LOGGER):
        sub = await mesh.subscribe(TOPIC, max_queue_size=10)
        message = {"type": "block", "hash": "0xabc"}
        peer.queues[TOPIC].put_nowait(message)
        got = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
        assert got == message
        # Second delivery of the same message is deduped — only one forward event.
        local.queues[TOPIC].put_nowait(message)
        await asyncio.sleep(0.05)
        [r.getMessage() for r in caplog.records]
    labels = {"source": "peer-y:443", "topic_class": TOPIC}
    assert _counter(gossip_mesh_message_forward_total, **labels) == 1
    fwd = _events(caplog, "message_forward")
    assert fwd and "peer=peer-y:443" in fwd[0]
    # Event-id equality across the hop — kills a random/per-attempt id mutant.
    assert f"id={_message_id(TOPIC, message)}" in fwd[0]
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


@pytest.mark.asyncio
async def test_mesh_publish_cap_terminal(caplog):
    """peer_publish_timeout exhaustion is cap-terminal, not generic failure —
    distinct event + metric at INFO (production level), peer-attributed."""

    class _Local(GossipBackend):
        async def publish(self, topic, message):
            return None

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    class _SlowPeer(GossipBackend):
        async def publish(self, topic, message):
            await asyncio.sleep(5)

        async def subscribe(self, topic, max_queue_size=100):
            return TopicSubscription(topic, asyncio.Queue(), lambda: None)

    mesh = MeshGossipBackend(_Local(), {"peer-slow:1": _SlowPeer()}, peer_publish_timeout=0.05)
    mesh._running = True
    labels = {"peer": "peer-slow:1", "topic_class": TOPIC, "outcome": "cap_timeout"}
    before = _counter(gossip_mesh_cap_terminal_total, **labels)
    with caplog.at_level(logging.INFO, logger=TELEMETRY_LOGGER):
        await mesh.publish(TOPIC, {"type": "x"})
        for _ in range(200):
            if _events(caplog, "peer_publish_cap_terminal"):
                break
            await asyncio.sleep(0.01)
    term = _events(caplog, "peer_publish_cap_terminal")
    assert term, "cap-terminal event missing"
    assert "peer=peer-slow:1" in term[0]
    assert "bound_s=" in term[0] and "attempt_age_ms=" in term[0]
    assert _counter(gossip_mesh_cap_terminal_total, **labels) == before + 1
    # cap-terminal must not double-count as a generic failure
    assert not _events(caplog, "peer_publish_failed")


@pytest.fixture
def _ws_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same surface as test_websocket.py: auth off, limits raised."""
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    monkeypatch.setattr(
        websocket_module,
        "_gossip_msg_rate",
        RateLimiter(rate=1_000_000, per=60),
    )


def test_ws_receiver_metrics_and_fields(caplog, _ws_test_settings):
    """Production-level receiver observability (#1308): rx_publish and
    echo_forward increment Prometheus counters regardless of log level, and
    the DEBUG records carry the additive R3/R7 fields (publisher, lag_ms,
    queue_depth) with stable event-id correlation."""
    topic = "transactions"
    tc = bounded_topic_label(topic)
    before_rx = _counter(gossip_ws_rx_publish_total, topic_class=tc)
    before_echo = _counter(gossip_ws_echo_forward_total, topic_class=tc)
    payload = {
        "tx_hash": "0x" + "c" * 64,
        "proposer": "0xValidatorA",
        "timestamp": time.time(),
        "payload": {"amount": 1},
    }
    # The app configures its own logging (propagate may be off under
    # TestClient), so attach a direct handler to the telemetry logger —
    # caplog's root handler cannot be relied on across the portal thread.
    tele_logger = logging.getLogger(TELEMETRY_LOGGER)
    records: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    collector = _Collect()
    tele_logger.addHandler(collector)
    try:
        with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
            with TestClient(create_app()) as client:
                with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as ws:
                    ws.send_json(payload)
                    echoed = ws.receive_json()
                    assert echoed == payload
    finally:
        tele_logger.removeHandler(collector)
    # Metrics advanced — this is the production-level pin: counters do not
    # depend on the DEBUG log level being enabled.
    assert _counter(gossip_ws_rx_publish_total, topic_class=tc) == before_rx + 1
    assert _counter(gossip_ws_echo_forward_total, topic_class=tc) >= before_echo + 1
    rx = [m for m in records if "event=rx_publish" in m]
    assert rx, "rx_publish event missing"
    assert "publisher=0xValidatorA" in rx[0]
    assert "lag_ms=" in rx[0] and "queue_depth=" in rx[0]
    # Same deterministic event id across the rx -> broker -> echo hop.
    event_id = _message_id(topic, payload)
    assert f"id={event_id}" in rx[0]
    echo = [m for m in records if "event=echo_forward" in m]
    assert echo and f"id={event_id}" in echo[0] and "queue_depth=" in echo[0]


def test_rx_publish_extra_fields_edges():
    """_rx_publish_extra_fields: publisher precedence + lag sanity bounds."""
    from aitbc_chain.rpc.websocket import _rx_publish_extra_fields

    now = time.time()
    assert _rx_publish_extra_fields({"proposer": "0xP"}) == {"publisher": "0xP"}
    assert _rx_publish_extra_fields({"validator": "0xV", "timestamp": now})["publisher"] == "0xV"
    f = _rx_publish_extra_fields({"timestamp": now - 5})
    assert 4000.0 <= f["lag_ms"] <= 8000.0  # type: ignore[index]
    # stale / future / non-numeric / bool timestamps emit no lag_ms
    assert "lag_ms" not in _rx_publish_extra_fields({"timestamp": now - 7200})
    assert "lag_ms" not in _rx_publish_extra_fields({"timestamp": now + 100})
    assert "lag_ms" not in _rx_publish_extra_fields({"timestamp": "soon"})
    assert "lag_ms" not in _rx_publish_extra_fields({"timestamp": True})
    assert _rx_publish_extra_fields([1, 2]) == {}
    assert _rx_publish_extra_fields("str") == {}


def _collect_telemetry():
    """Attach a direct handler to the telemetry logger (app logging config can
    stop propagation under TestClient); returns (records, detach)."""
    tele_logger = logging.getLogger(TELEMETRY_LOGGER)
    records: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Collect()
    handler.setLevel(logging.DEBUG)
    tele_logger.addHandler(handler)
    return records, lambda: tele_logger.removeHandler(handler)


def test_ws_queue_depth_value_and_gauge_under_backlog(caplog, _ws_test_settings, monkeypatch):
    """#1308 respin-3: a stalled echo path must show a NON-ZERO queue depth in
    the rx_publish event and the gauge. Kills mutants that hardcode
    queue_depth=0 / gauge 0.0 (E review c23580-83, M3/M4)."""
    topic = "transactions"
    tc = bounded_topic_label(topic)
    real_send = websocket_module._gossip_ws_send_json
    gauge_at_send: list[float] = []
    state = {"n": 0}

    async def slow_send(ws, payload):
        state["n"] += 1
        gauge_at_send.append(float(gossip_ws_subscriber_queue_depth.labels(topic_class=tc)._value.get()))
        if state["n"] == 1:
            # Stall the first echo until all five publishes have been recorded —
            # deterministic backlog instead of a fixed sleep that races suite load.
            for _ in range(1000):
                if sum("event=rx_publish" in m for m in records) >= 5:
                    break
                await asyncio.sleep(0.01)
        return await real_send(ws, payload)

    monkeypatch.setattr(websocket_module, "_gossip_ws_send_json", slow_send)
    records, detach = _collect_telemetry()
    try:
        with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
            with TestClient(create_app()) as client:
                with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as ws:
                    for i in range(5):
                        ws.send_json({"tx_hash": f"0x{i:064x}", "proposer": "0xV", "timestamp": time.time()})
                    for _ in range(5):
                        ws.receive_json()
    finally:
        detach()
    depths = [
        int(m.split("queue_depth=")[1].split()[0].rstrip(","))
        for m in records
        if "event=rx_publish" in m and "queue_depth=" in m
    ]
    assert len(depths) == 5, depths
    assert max(depths) >= 1, f"stalled echo must show backlog in rx_publish queue_depth, got {depths}"
    echo_depths = [
        int(m.split("queue_depth=")[1].split()[0].rstrip(","))
        for m in records
        if "event=echo_forward" in m and "queue_depth=" in m
    ]
    assert max(echo_depths) >= 1, echo_depths
    assert max(gauge_at_send) >= 1.0, f"gauge never reflected backlog: {gauge_at_send}"


def test_ws_echo_forward_failure_counted(caplog, _ws_test_settings, monkeypatch):
    """#1308 respin-3: a failed echo send increments echo_forward_failed_total
    and emits echo_forward_failed (kills M1)."""
    topic = "transactions"
    tc = bounded_topic_label(topic)
    before_fail = _counter(gossip_ws_echo_forward_failed_total, topic_class=tc)
    real_send = websocket_module._gossip_ws_send_json

    async def failing_send(ws, payload):
        if isinstance(payload, dict) and "tx_hash" in payload:
            raise RuntimeError("injected echo send failure")
        return await real_send(ws, payload)

    monkeypatch.setattr(websocket_module, "_gossip_ws_send_json", failing_send)
    records, detach = _collect_telemetry()
    try:
        with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
            with TestClient(create_app()) as client:
                with client.websocket_connect(f"/rpc/gossip/ws?topic={topic}") as ws:
                    ws.send_json({"tx_hash": "0x" + "d" * 64, "proposer": "0xV"})
                    time.sleep(0.3)
    finally:
        detach()
    assert _counter(gossip_ws_echo_forward_failed_total, topic_class=tc) == before_fail + 1
    failed = [m for m in records if "event=echo_forward_failed" in m]
    assert failed and "injected echo send failure" in failed[0]
