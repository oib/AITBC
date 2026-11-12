"""#1874: public gossip topics are subscribe-open but publish-gated.

``/rpc/gossip/ws`` used to bridge ANY client publish on ``transactions`` /
``status`` / ``mempool`` (and dotted subtopics) into the node's gossip broker —
an anonymous internet caller could inject forged tx/status gossip that
propagates to every peer's broker. Publishing now requires a peer credential
sent in-band as ``{"type": "peer_auth", "api_key": ...}`` — the same set
``/subscribe/ws`` and the lease routes accept (own ``BLOCKCHAIN_RPC_API_KEY``,
a configured ``BLOCKCHAIN_RPC_API_KEY_PEERS`` key, or a live issued join key).
Validator challenge-response still governs the restricted topics and is NOT
substituted by the peer key. ``GOSSIP_PUBLIC_PUBLISH_REQUIRE_KEY=false`` is
the pre-#1874 escape hatch.

Mempool admission re-verifies every gossip tx signature
(``gossip_transaction_drop_reason`` + ``_validate_transaction_admission``,
pinned by test_gossip_tx_admission.py), so the residual risk this gate closes
is broker/peer pollution and status/mempool-topic spoofing, not state forgery.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aitbc_chain.config import settings
from aitbc_chain.rpc import escrow_routes, websocket as websocket_module
from aitbc.security import RateLimiter
from starlette.websockets import WebSocket, WebSocketDisconnect

PEER = "198.51.100.66"
RPC_KEY = "node-rpc-key-1874"
PEER_KEY = "fleet-peer-key-1874"


def _ws(topic: str, peer: str = PEER) -> WebSocket:
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rpc/gossip/ws",
        "raw_path": b"/rpc/gossip/ws",
        "query_string": f"topic={topic}".encode(),
        "root_path": "",
        "headers": [],
        "client": (peer, 4444),
        "server": ("testserver", 80),
        "subprotocols": [],
    }

    async def _recv() -> dict:
        return {"type": "websocket.disconnect"}

    async def _send(message: dict) -> None:
        return None

    return WebSocket(scope, receive=_recv, send=_send)


class _Sub:
    def __aiter__(self):
        async def _gen():
            await asyncio.Event().wait()
            yield {}

        return _gen()

    def close(self) -> None:
        return None


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AITBC_TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "gossip_public_publish_require_key", True)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 1000)
    monkeypatch.setattr(settings, "validator_set", "[]")
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=1_000_000, per=60))
    # The accepted peer-key set: this node's RPC key + one configured peer key.
    # Issued join keys are covered by rpc_peer_key_accepted's peer_keys lookup
    # and are exercised by the subscribe/ws suite (#1702).
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", RPC_KEY)
    monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({PEER_KEY}))
    published: list[tuple[str, object]] = []

    async def _publish(topic: str, data: object, *a: object, **k: object) -> None:
        published.append((topic, data))

    async def _subscribe(topic: str, max_queue_size: int = 100) -> _Sub:
        return _Sub()

    monkeypatch.setattr(websocket_module.gossip_broker, "publish", _publish)
    monkeypatch.setattr(websocket_module.gossip_broker, "subscribe", _subscribe)
    websocket_module._gossip_ip_connections.clear()
    yield published
    websocket_module._gossip_ip_connections.clear()


async def _run_conn(topic: str, frames: list[dict]) -> tuple[list[dict], int | None]:
    """Drive one connection through ``frames``; return (server frames, close code)."""
    ws = _ws(topic)
    sent: list[dict] = []
    queue = [json.dumps(f) for f in frames]
    close_code: list[int | None] = []

    async def _noop(*a: object, **k: object) -> None:
        return None

    async def _receive_text() -> str:
        if queue:
            return queue.pop(0)
        raise WebSocketDisconnect()

    async def _send_json(payload: object) -> None:
        sent.append(payload)  # type: ignore[arg-type]

    async def _close(code: int | None = None, *a: object, **k: object) -> None:
        close_code.append(code)

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _send_json  # type: ignore[method-assign]
    ws.close = _close  # type: ignore[method-assign]
    await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=10)
    return sent, close_code[0] if close_code else None


PAYLOAD = {"type": "new_transaction", "tx": {"from": "0xabc"}}


# --------------------------------------------------------------------------
# publish gate on public topics
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_publish_without_peer_key_is_rejected(harness: list) -> None:
    sent, code = await _run_conn("transactions", [PAYLOAD])
    assert harness == []
    assert any("Peer key required" in str(m) for m in sent)
    assert code == 1008


@pytest.mark.asyncio
async def test_public_publish_with_node_rpc_key_reaches_broker(harness: list) -> None:
    sent, _ = await _run_conn("transactions", [{"type": "peer_auth", "api_key": RPC_KEY}, PAYLOAD])
    assert harness == [("transactions", PAYLOAD)]
    assert any(m.get("type") == "peer_auth_ok" for m in sent)


@pytest.mark.asyncio
async def test_public_publish_with_configured_peer_key_reaches_broker(harness: list) -> None:
    await _run_conn("status", [{"type": "peer_auth", "api_key": PEER_KEY}, {"height": 7}])
    assert harness == [("status", {"height": 7})]


@pytest.mark.asyncio
@pytest.mark.parametrize("topic", ["transactions", "status", "mempool", "transactions.bc-2", "status.deep.sub"])
async def test_gate_covers_every_public_root_and_subtopic(harness: list, topic: str) -> None:
    await _run_conn(topic, [{"type": "peer_auth", "api_key": "wrong"}, PAYLOAD])
    assert harness == []


@pytest.mark.asyncio
async def test_subscribe_only_needs_no_key(harness: list) -> None:
    """A keyless client may still subscribe — the gate is publish-only."""
    ws = _ws("transactions")
    closes: list[int | None] = []

    async def _noop(*a: object, **k: object) -> None:
        return None

    async def _receive_text() -> str:
        await asyncio.sleep(0.2)
        raise WebSocketDisconnect()

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _noop  # type: ignore[method-assign]
    ws.close = lambda code=None, *a, **k: closes.append(code)  # type: ignore[method-assign]
    await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=10)
    assert closes in ([], [None])


# --------------------------------------------------------------------------
# escapes and non-substitution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_key_escape_restores_open_publish(harness: list, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_public_publish_require_key", False)
    await _run_conn("transactions", [PAYLOAD])
    assert harness == [("transactions", PAYLOAD)]


@pytest.mark.asyncio
async def test_gossip_auth_disabled_restores_open_publish(harness: list, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    await _run_conn("transactions", [PAYLOAD])
    assert harness == [("transactions", PAYLOAD)]


@pytest.mark.asyncio
async def test_peer_key_does_not_unlock_restricted_topics(harness: list) -> None:
    """blocks/pbft/consensus stay validator-challenge-only — a valid peer key
    must not substitute for the VALIDATOR_SET signature."""
    sent, code = await _run_conn("blocks", [{"type": "peer_auth", "api_key": RPC_KEY}, {"hash": "0x" + "a" * 64}])
    assert harness == []
    assert any("authentication required" in str(m).lower() for m in sent)
    assert code == 1008


@pytest.mark.asyncio
async def test_peer_auth_ok_is_not_a_publish(harness: list) -> None:
    """The handshake frame itself never reaches the broker."""
    await _run_conn("transactions", [{"type": "peer_auth", "api_key": RPC_KEY}])
    assert harness == []


# --------------------------------------------------------------------------
# dialer side: WebsocketGossipBackend sends peer_auth with its credential
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backend_peer_auth_frame_and_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend

    monkeypatch.setenv("BLOCKCHAIN_RPC_API_KEY", "env-key-1874")
    backend = WebsocketGossipBackend("ws://127.0.0.1:1/rpc/gossip/ws")
    assert backend._api_key == "env-key-1874"

    sent: list[dict] = []

    class _FakeWS:
        async def send(self, data: str) -> None:
            sent.append(json.loads(data))

    await backend._send_peer_auth(_FakeWS())
    assert sent == [{"type": "peer_auth", "api_key": "env-key-1874"}]

    explicit = WebsocketGossipBackend("ws://127.0.0.1:1/rpc/gossip/ws", api_key="explicit-key")
    assert explicit._api_key == "explicit-key"

    monkeypatch.delenv("BLOCKCHAIN_RPC_API_KEY")
    no_key = WebsocketGossipBackend("ws://127.0.0.1:1/rpc/gossip/ws")
    assert no_key._api_key is None
    await no_key._send_peer_auth(_FakeWS())
    assert sent == [{"type": "peer_auth", "api_key": "env-key-1874"}]
