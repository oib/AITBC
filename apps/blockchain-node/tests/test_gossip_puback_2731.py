"""#2731: explicit publish acks (``puback``) on the gossip websocket transport.

The websocket backend dials peers with ``?puback=1``; a peer that understands
it answers each publish with ``{"type": "puback", "event_id", "ok"}`` instead
of relying solely on the broker echo. ``ok`` reports broker acceptance only —
``GossipBroker.publish`` returns normally on a dedup skip or a priority-queue
enqueue, so it is NOT a durability or downstream-delivery guarantee. These
tests pin the client-side wait resolution, the rejection retry path,
malformed-frame filtering, URL negotiation, and the server-side emission
gates (opt-in only, no exception detail, nothing on auth-denied).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import websockets.exceptions  # noqa: F401 - backend except-clauses evaluate websockets.exceptions.*; production loads it via websockets.connect, these fakes bypass that
from aitbc_chain.config import settings
from aitbc_chain.gossip import GossipBroker, InMemoryGossipBackend
from aitbc_chain.gossip._internal import _message_id
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.rpc import websocket as websocket_module

TOPIC = "status"
PEER = "puback-peer-2731"
TELEMETRY_LOGGER = "aitbc_chain.gossip.telemetry"


class _AckWS:
    """Fake websocket: ``send`` records the payload and answers per ``plan``.

    Plan items (shared across reconnects, last value repeats):
    ``True``/``False`` -> feed a ``puback`` frame with that ``ok`` back through
    the backend's real ``_handle_inbound`` (what the reader task does);
    ``"echo"`` -> schedule a delayed broker echo via ``_is_echo`` (legacy ack);
    ``None`` -> no automatic response (the test drives ``_handle_inbound``).
    """

    def __init__(
        self, backend: WebsocketGossipBackend, topic: str, sent_log: list[dict], plan: list[Any], echo_delay: float
    ) -> None:
        self._backend = backend
        self._topic = topic
        self._sent_log = sent_log
        self._plan = plan
        self._echo_delay = echo_delay

    async def send(self, payload: str) -> None:
        message = json.loads(payload)
        self._sent_log.append(message)
        step = self._plan.pop(0) if len(self._plan) > 1 else (self._plan[0] if self._plan else None)
        if step is True or step is False:
            frame = {
                "type": "puback",
                "event_id": self._backend._compute_message_id(self._topic, message),
                "ok": step,
            }
            await self._backend._handle_inbound(self._topic, json.dumps(frame))
        elif step == "echo":

            async def _echo() -> None:
                await asyncio.sleep(self._echo_delay)
                await self._backend._is_echo(self._topic, message)

            asyncio.get_running_loop().create_task(_echo())

    async def close(self, close_timeout: float | None = None) -> None:
        return None


def _backend(
    ack_timeout: float = 5.0,
    plan: list[Any] | None = None,
    echo_delay: float = 0.01,
) -> tuple[WebsocketGossipBackend, list[dict]]:
    backend = WebsocketGossipBackend("ws://127.0.0.1:9/rpc/gossip/ws", ack_timeout=ack_timeout, peer_name=PEER)
    backend._running = True
    sent: list[dict] = []
    steps = list(plan) if plan is not None else [True]

    async def fake_ensure(topic: str) -> None:
        backend._websockets[topic] = _AckWS(backend, topic, sent, steps, echo_delay)

    backend._ensure_connection_unsafe = fake_ensure  # type: ignore[method-assign]
    return backend, sent


async def _wait_for_send(sent: list[dict], expected: int = 1) -> None:
    for _ in range(200):
        if len(sent) >= expected:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"expected {expected} sends, got {len(sent)}")


# ---------------------------------------------------------------------------
# client side: WebsocketGossipBackend ack resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_puback_resolves_publish_without_echo_and_is_not_delivered() -> None:
    """A puback-only peer acks the wait; the frame itself never reaches queues."""
    backend, sent = _backend(plan=[True])
    queue: asyncio.Queue = asyncio.Queue()
    backend._queues[TOPIC] = [queue]
    message = {"type": "new_transaction", "tx": {"n": 1}}
    await backend._publish_with_ack(TOPIC, message, retry=False)
    assert sent == [message]
    # The puback frame was consumed by _handle_inbound — never queued.
    assert queue.empty()
    assert backend._ack_events == {}
    assert backend._ack_errors == {}
    # Ordinary payloads still flow to subscribers afterwards.
    payload = {"type": "new_transaction", "tx": {"n": 2}}
    await backend._handle_inbound(TOPIC, json.dumps(payload))
    assert queue.get_nowait() == payload


@pytest.mark.asyncio
async def test_puback_rejection_is_error_outcome_with_single_fast_retry() -> None:
    """ok=false -> error outcome -> one retry -> terminal raise, all fast
    (ack_timeout is deliberately huge so only the puback can end the wait)."""
    backend, sent = _backend(ack_timeout=30.0, plan=[False])
    message = {"type": "attest", "n": 5}
    with pytest.raises(RuntimeError, match="publish/ack failed"):
        await asyncio.wait_for(backend._publish_with_ack(TOPIC, message, retry=True), timeout=10)
    assert sent == [message, message]
    assert backend._ack_events == {}
    assert backend._ack_errors == {}


@pytest.mark.asyncio
async def test_echo_still_acks_for_peers_without_puback() -> None:
    """Legacy peer: no puback frame — the broker echo remains the ack."""
    backend, sent = _backend(plan=["echo"], echo_delay=0.01)
    message = {"type": "attest", "n": 6}
    await asyncio.wait_for(backend._publish_with_ack(TOPIC, message, retry=False), timeout=5)
    assert sent == [message]


@pytest.mark.asyncio
async def test_malformed_unknown_and_wrong_topic_pubacks_are_ignored() -> None:
    backend, sent = _backend(plan=[None])  # manual: the test feeds frames
    queue: asyncio.Queue = asyncio.Queue()
    backend._queues[TOPIC] = [queue]
    message = {"type": "attest", "n": 7}
    msg_id = backend._compute_message_id(TOPIC, message)
    task = asyncio.create_task(backend._publish_with_ack(TOPIC, message, retry=False))
    await _wait_for_send(sent)
    entry = backend._ack_events.get(msg_id)
    assert entry is not None

    bad_frames = [
        {"type": "puback"},  # missing event_id/ok
        {"type": "puback", "event_id": 123, "ok": True},  # non-str event_id
        {"type": "puback", "event_id": msg_id, "ok": "yes"},  # non-bool ok
        {"type": "puback", "event_id": msg_id, "ok": 1},  # non-bool ok
        {"type": "puback", "event_id": "pbft.prepare.x:abc", "ok": True},  # other topic
        {"type": "puback", "event_id": "status.other:deadbeef", "ok": True},  # topic-prefix lookalike
        {"type": "puback", "event_id": "status:unknown-id", "ok": True},  # well-formed, unknown id
    ]
    for frame in bad_frames:
        await backend._handle_inbound(TOPIC, json.dumps(frame))
        assert not task.done()
        assert not entry[0].is_set()
        assert queue.empty()

    # A well-formed puback for the live event id still resolves the wait.
    await backend._handle_inbound(TOPIC, json.dumps({"type": "puback", "event_id": msg_id, "ok": True}))
    await asyncio.wait_for(task, timeout=5)
    assert queue.empty()


def test_build_url_opts_into_puback_and_preserves_chain_and_base_params() -> None:
    bound = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws?chain=chain-b&foo=bar", chain_id="chain-a")
    query = parse_qs(urlsplit(bound._build_url("transactions")).query)
    assert query["puback"] == ["1"]
    assert query["chain"] == ["chain-a"]  # explicit chain_id wins over the embedded one
    assert query["foo"] == ["bar"]  # unrelated base params preserved
    assert query["topic"] == ["transactions"]
    assert "client_id" in query

    embedded = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws?chain=chain-b")
    query2 = parse_qs(urlsplit(embedded._build_url("blocks.x")).query)
    assert query2["chain"] == ["chain-b"]
    assert query2["puback"] == ["1"]

    legacy = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws")
    query3 = parse_qs(urlsplit(legacy._build_url("transactions")).query)
    assert "chain" not in query3
    assert query3["puback"] == ["1"]


# ---------------------------------------------------------------------------
# server side: _gossip_handle_publish puback emission
# ---------------------------------------------------------------------------


class _ServerWS:
    """Minimal WebSocket double for ``_GossipConnState``/``_gossip_handle_publish``."""

    def __init__(self, query_params: dict[str, str] | None = None) -> None:
        self.query_params = query_params or {}
        self.sent: list[dict] = []
        self.closed: list[int | None] = []

    async def send_json(self, payload: object) -> None:
        self.sent.append(payload)  # type: ignore[arg-type]

    async def close(self, code: int | None = None, reason: str | None = None) -> None:
        self.closed.append(code)


class _BrokerStub:
    """Duck-typed GossipBroker: records publishes, optionally raises."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic: str, data: object) -> None:
        self.published.append((topic, data))
        if self.error is not None:
            raise self.error


def _state(
    ws: _ServerWS, broker: Any, topic: str = "transactions", authorized: bool = True
) -> websocket_module._GossipConnState:
    state = websocket_module._GossipConnState(ws, topic, "chain-a", "198.51.100.9", broker)  # type: ignore[arg-type]
    state.authorized = authorized
    return state


@pytest.fixture
def gossip_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "gossip_public_publish_require_key", True)


def test_puback_enabled_only_for_exact_opt_in() -> None:
    assert _state(_ServerWS({"puback": "1"}), _BrokerStub()).puback_enabled is True
    assert _state(_ServerWS({"puback": "0"}), _BrokerStub()).puback_enabled is False
    assert _state(_ServerWS({"puback": "true"}), _BrokerStub()).puback_enabled is False
    assert _state(_ServerWS({}), _BrokerStub()).puback_enabled is False


@pytest.mark.asyncio
async def test_server_sends_one_true_puback_on_broker_accept(gossip_settings: None) -> None:
    broker = _BrokerStub()
    ws = _ServerWS({"puback": "1"})
    state = _state(ws, broker)
    data = {"type": "new_transaction", "tx": {"hash": "0x" + "a" * 64}}
    assert await websocket_module._gossip_handle_publish(state, data) is True
    assert broker.published == [("transactions", data)]
    assert ws.sent == [{"type": "puback", "event_id": _message_id("transactions", data), "ok": True}]


@pytest.mark.asyncio
async def test_server_sends_false_puback_on_broker_failure_without_exception_text(gossip_settings: None) -> None:
    broker = _BrokerStub(error=RuntimeError("sqlite detail: disk I/O on secret-path"))
    ws = _ServerWS({"puback": "1"})
    state = _state(ws, broker)
    data = {"type": "new_transaction", "tx": {"hash": "0x" + "b" * 64}}
    assert await websocket_module._gossip_handle_publish(state, data) is True
    assert len(ws.sent) == 1
    frame = ws.sent[0]
    assert frame["type"] == "puback"
    assert frame["ok"] is False
    assert frame["event_id"] == _message_id("transactions", data)
    assert set(frame) == {"type", "event_id", "ok"}
    assert "secret" not in json.dumps(frame)
    assert "sqlite" not in json.dumps(frame)


@pytest.mark.asyncio
async def test_server_sends_no_puback_to_legacy_client(gossip_settings: None) -> None:
    broker = _BrokerStub()
    ws = _ServerWS({})  # no ?puback=1 — the pre-#2731 client
    state = _state(ws, broker)
    data = {"height": 11}
    assert await websocket_module._gossip_handle_publish(state, data) is True
    assert broker.published == [("transactions", data)]
    assert ws.sent == []


@pytest.mark.asyncio
async def test_server_no_puback_and_no_broker_call_when_auth_denied(gossip_settings: None) -> None:
    broker = _BrokerStub()
    ws = _ServerWS({"puback": "1"})
    state = _state(ws, broker, authorized=False)  # peer_authorized stays False
    data = {"type": "new_transaction", "tx": {"hash": "0x" + "c" * 64}}
    assert await websocket_module._gossip_handle_publish(state, data) is False
    assert broker.published == []
    assert all(not (isinstance(f, dict) and f.get("type") == "puback") for f in ws.sent)
    assert ws.closed == [1008]


@pytest.mark.asyncio
async def test_broker_acceptance_without_echo_resolves_client(gossip_settings: None) -> None:
    """A broker.publish that returns without delivering (dedup skip or
    priority-queue enqueue — the stub models that acceptance) still acks the
    client: no echo will ever arrive, so only the puback can resolve the wait.
    The real-broker dedup seam is covered by
    test_real_broker_dedup_still_acks_without_refanout below."""
    backend, sent = _backend(plan=[None])  # client waits; nothing auto-responds
    queue: asyncio.Queue = asyncio.Queue()
    backend._queues[TOPIC] = [queue]
    message = {"type": "new_transaction", "tx": {"hash": "0x" + "d" * 64}}
    task = asyncio.create_task(backend._publish_with_ack(TOPIC, message, retry=False))
    await _wait_for_send(sent)
    assert sent == [message]

    # Server side: the broker "accepts" (returns normally — dedup path) and
    # emits exactly one puback for the opted-in client.
    broker = _BrokerStub()
    ws = _ServerWS({"puback": "1"})
    state = _state(ws, broker, topic=TOPIC, authorized=True)
    assert await websocket_module._gossip_handle_publish(state, message) is True
    assert broker.published == [(TOPIC, message)]
    puback_frames = [f for f in ws.sent if isinstance(f, dict) and f.get("type") == "puback"]
    assert len(puback_frames) == 1
    assert puback_frames[0]["ok"] is True
    assert puback_frames[0]["event_id"] == _message_id(TOPIC, message)

    # Feed the server's puback through the client's real inbound path.
    await backend._handle_inbound(TOPIC, json.dumps(puback_frames[0]))
    await asyncio.wait_for(task, timeout=5)
    assert queue.empty()


@pytest.mark.asyncio
async def test_real_broker_dedup_still_acks_without_refanout(gossip_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real ``GossipBroker`` seam: the second identical publish is dedup-
    skipped inside ``broker.publish`` — it returns normally (so the server
    emits ``ok=true``) but never reaches the backend, hence no echo. The
    subscription must see exactly one payload."""
    monkeypatch.setattr(settings, "gossip_priority_enabled", False)
    broker = GossipBroker(InMemoryGossipBackend())
    sub = await broker.subscribe("transactions")
    ws = _ServerWS({"puback": "1"})
    state = _state(ws, broker, topic="transactions", authorized=True)
    data = {"type": "new_transaction", "tx": {"hash": "0x" + "e" * 64}}
    try:
        assert await websocket_module._gossip_handle_publish(state, data) is True
        assert await websocket_module._gossip_handle_publish(state, data) is True
        pubacks = [f for f in ws.sent if isinstance(f, dict) and f.get("type") == "puback"]
        assert len(pubacks) == 2
        assert all(f["ok"] is True for f in pubacks)
        assert pubacks[0]["event_id"] == pubacks[1]["event_id"] == _message_id("transactions", data)
        # Dedup skipped the second fanout: exactly one payload on the bus.
        assert await asyncio.wait_for(sub.get(), timeout=1) == data
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.2)
    finally:
        sub.close()
        await broker.shutdown()


# ---------------------------------------------------------------------------
# ack bookkeeping: prior-timeout supersede + concurrent identical publishers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_later_puback_supersedes_prior_timeout_marker(caplog: pytest.LogCaptureFixture) -> None:
    """Attempt 1 times out (no ack at all); attempt 2's puback ok retires the
    attempt-1 timeout marker — the same bookkeeping the echo path performs."""
    backend, sent = _backend(ack_timeout=0.05, plan=[None, True])
    message = {"type": "attest", "n": 8}
    msg_id = backend._compute_message_id(TOPIC, message)
    with caplog.at_level(logging.DEBUG, logger=TELEMETRY_LOGGER):
        await asyncio.wait_for(backend._publish_with_ack(TOPIC, message, retry=True), timeout=10)
    assert sent == [message, message]
    assert msg_id not in backend._ack_timeouts
    assert msg_id not in backend._ack_errors
    ack_events = [r.getMessage() for r in caplog.records if "event=publish_ack" in r.getMessage()]
    assert ack_events and "attempt=2" in ack_events[0]
    assert "prior_timed_out_attempt=1" in ack_events[0]
    assert not [r for r in caplog.records if "event=ack_late" in r.getMessage()]


@pytest.mark.asyncio
async def test_concurrent_identical_publishers_each_get_their_own_ack() -> None:
    """Registration inside the connect lock: two publishers of the same
    message serialize on the lock instead of overwriting each other's
    waiter — both must resolve, each on its own send+puback."""
    backend, sent = _backend(ack_timeout=1.0, plan=[True])
    message = {"type": "attest", "n": 9}
    results = await asyncio.wait_for(
        asyncio.gather(
            backend._publish_with_ack(TOPIC, message, retry=True),
            backend._publish_with_ack(TOPIC, message, retry=True),
        ),
        timeout=10,
    )
    assert results == [None, None]
    assert sent == [message, message]
    assert backend._ack_events == {}
    assert backend._ack_errors == {}
