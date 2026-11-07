"""#1241: gossip websocket client identity honours forwarding headers only
from trusted proxies, and the per-worker limit dilution is pinned.

``_gossip_client_ip`` keys the per-(ip, chain) connection cap, the per-message
rate bucket and the challenge-mint bucket. Before #1241 it believed
``X-Real-IP`` / ``X-Forwarded-For`` from any peer, so one TCP peer rotating a
header per connection minted a fresh slot, bucket and challenge budget each
time. The key is now the wire peer unless that peer is in
``AITBC_TRUSTED_PROXIES`` (default loopback).
"""

from __future__ import annotations

import asyncio
import importlib.util
from types import ModuleType

import pytest
from aitbc_chain.config import settings
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from starlette.websockets import WebSocket, WebSocketDisconnect

CLIENT = "203.0.113.50"
ATTACKER_PEER = "198.51.100.77"


def _ws(peer: str | None, headers: list[tuple[bytes, bytes]] | None = None) -> WebSocket:
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rpc/gossip/ws",
        "raw_path": b"/rpc/gossip/ws",
        "query_string": b"topic=transactions",
        "root_path": "",
        # ASGI servers (uvicorn/h11) lowercase header names before building the scope.
        "headers": [(k.lower(), v) for k, v in (headers or [])],
        "client": (peer, 4444) if peer is not None else None,
        "server": ("testserver", 80),
        "subprotocols": [],
    }

    async def _recv() -> dict:
        return {"type": "websocket.disconnect"}

    async def _send(message: dict) -> None:
        return None

    return WebSocket(scope, receive=_recv, send=_send)


def _h(**kw: str) -> list[tuple[bytes, bytes]]:
    return [(k.replace("_", "-").encode(), v.encode()) for k, v in kw.items()]


@pytest.fixture(autouse=True)
def _default_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITBC_TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=1_000_000, per=60))


# --------------------------------------------------------------------------
# identity derivation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        _h(x_real_ip="1.2.3.4"),
        _h(x_forwarded_for="1.2.3.4"),
        _h(x_forwarded_for="9.9.9.9, 1.2.3.4"),
        _h(x_real_ip="1.2.3.4", x_forwarded_for="5.6.7.8"),  # conflicting
        _h(x_real_ip="1.2.3.4, 5.6.7.8", x_forwarded_for="9.9.9.9"),
        _h(forwarded="for=1.2.3.4;proto=https"),
        [(b"X-REAL-IP", b"1.2.3.4"), (b"X-Forwarded-For", b"5.6.7.8")],  # case variants
        [(b"x-real-ip", b"1.2.3.4"), (b"x-real-ip", b"5.6.7.8")],  # duplicate header
        _h(x_real_ip="not-an-ip", x_forwarded_for="also-not"),
    ],
)
def test_untrusted_peer_headers_are_ignored(headers: list[tuple[bytes, bytes]]) -> None:
    assert websocket_module._gossip_client_ip(_ws(ATTACKER_PEER, headers)) == ATTACKER_PEER


def test_rotating_headers_collapse_to_one_identity() -> None:
    keys = {
        websocket_module._gossip_client_ip(_ws(ATTACKER_PEER, _h(x_real_ip=f"10.0.{i // 250}.{i % 250 + 1}")))
        for i in range(500)
    }
    assert keys == {ATTACKER_PEER}


def test_trusted_loopback_peer_reads_x_real_ip() -> None:
    # nginx / the gateway overwrite X-Real-IP with the address they observed.
    assert websocket_module._gossip_client_ip(_ws("127.0.0.1", _h(x_real_ip=CLIENT))) == CLIENT
    assert websocket_module._gossip_client_ip(_ws("::1", _h(x_real_ip=CLIENT))) == CLIENT


def test_trusted_peer_ipv4_mapped_ipv6_is_trusted() -> None:
    assert websocket_module._gossip_client_ip(_ws("::ffff:127.0.0.1", _h(x_real_ip=CLIENT))) == CLIENT


def test_trusted_peer_xff_rightmost_untrusted_hop_wins() -> None:
    # Legit chain: client -> edge proxy (trusted) -> nginx (appends peer).
    ws = _ws("127.0.0.1", _h(x_forwarded_for=f"6.6.6.6, {CLIENT}, 127.0.0.1"))
    assert websocket_module._gossip_client_ip(ws) == CLIENT
    # A client-prepended left entry never counts.
    ws = _ws("127.0.0.1", _h(x_forwarded_for=f"6.6.6.6, 7.7.7.7, {CLIENT}"))
    assert websocket_module._gossip_client_ip(ws) == CLIENT


def test_trusted_peer_garbage_headers_fall_back_to_peer() -> None:
    ws = _ws("127.0.0.1", _h(x_real_ip="<script>", x_forwarded_for="nope, also-nope"))
    assert websocket_module._gossip_client_ip(ws) == "127.0.0.1"
    assert websocket_module._gossip_client_ip(_ws("127.0.0.1")) == "127.0.0.1"


def test_trusted_peer_case_variants_are_read() -> None:
    # Header names are case-insensitive on the wire; the legit chain survives.
    ws = _ws("127.0.0.1", [(b"X-REAL-IP", CLIENT.encode())])
    assert websocket_module._gossip_client_ip(ws) == CLIENT
    ws = _ws("127.0.0.1", [(b"X-Forwarded-For", f"6.6.6.6, {CLIENT}".encode())])
    assert websocket_module._gossip_client_ip(ws) == CLIENT


def test_trusted_list_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    lan_proxy = "10.1.223.1"
    ws = _ws(lan_proxy, _h(x_real_ip=CLIENT))
    assert websocket_module._gossip_client_ip(ws) == lan_proxy  # not trusted by default
    monkeypatch.setenv("AITBC_TRUSTED_PROXIES", "10.1.223.0/24")
    assert websocket_module._gossip_client_ip(ws) == CLIENT
    # loopback is no longer trusted once the list is replaced
    assert websocket_module._gossip_client_ip(_ws("127.0.0.1", _h(x_real_ip=CLIENT))) == "127.0.0.1"


def test_missing_client_is_unknown() -> None:
    assert websocket_module._gossip_client_ip(_ws(None, _h(x_real_ip=CLIENT))) == "unknown"


# --------------------------------------------------------------------------
# connection cap through the real handler
# --------------------------------------------------------------------------


async def _noop(*args: object, **kwargs: object) -> None:
    return None


class _Sub:
    def __aiter__(self):
        async def _gen():
            await asyncio.Event().wait()
            yield {}

        return _gen()

    def close(self) -> None:
        return None


def _held_ws(peer: str, headers: list[tuple[bytes, bytes]], release: asyncio.Event, closes: list[int | None]) -> WebSocket:
    ws = _ws(peer, headers)

    async def _receive_text() -> str:
        await release.wait()
        raise WebSocketDisconnect()

    async def _close(code: int | None = None, *a: object, **k: object) -> None:
        closes.append(code)

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _noop  # type: ignore[method-assign]
    ws.close = _close  # type: ignore[method-assign]
    return ws


async def _flood(module: ModuleType, peer: str, n: int, header_for: object) -> tuple[int, int]:
    """Open ``n`` connections from ``peer`` (held open); return (held, rejected)."""
    release = asyncio.Event()
    closes: list[int | None] = []
    tasks = []
    for i in range(n):
        ws = _held_ws(peer, header_for(i), release, closes)  # type: ignore[operator]
        tasks.append(asyncio.create_task(module.gossip_websocket(ws)))
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    rejected = sum(1 for c in closes if c == 1008)
    held = n - rejected
    release.set()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    return held, rejected


@pytest.fixture
def _cap3(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 3)

    async def _subscribe(topic: str, max_queue_size: int = 100) -> _Sub:
        return _Sub()

    monkeypatch.setattr(websocket_module.gossip_broker, "subscribe", _subscribe)
    websocket_module._gossip_ip_connections.clear()
    yield
    websocket_module._gossip_ip_connections.clear()


@pytest.mark.asyncio
async def test_rotating_xff_cannot_exceed_per_ip_cap(_cap3: None) -> None:
    """N+1 connections from one TCP peer with a rotating XFF/X-Real-IP stay capped."""
    cap = settings.gossip_max_concurrent_connections_per_ip

    def headers(i: int) -> list[tuple[bytes, bytes]]:
        return [
            (b"x-forwarded-for", f"10.9.{i}.1".encode()),
            (b"x-real-ip", f"10.8.{i}.1".encode()),
        ]

    held, rejected = await _flood(websocket_module, ATTACKER_PEER, cap + 5, headers)
    assert held == cap
    assert rejected == 5
    assert websocket_module._gossip_ip_connections.get((ATTACKER_PEER, settings.chain_id), 0) == 0
    # one key only: the peer — no per-header-value entries were minted
    assert all(k[0] == ATTACKER_PEER for k in websocket_module._gossip_ip_connections)


@pytest.mark.asyncio
async def test_distinct_clients_behind_trusted_proxy_get_own_slots(_cap3: None) -> None:
    """Legit chain: nginx on loopback stamps each real client; they do not share a cap."""
    cap = settings.gossip_max_concurrent_connections_per_ip
    a, _ = await _flood(websocket_module, "127.0.0.1", cap + 2, lambda i: _h(x_real_ip="203.0.113.1"))
    b, _ = await _flood(websocket_module, "127.0.0.1", cap + 2, lambda i: _h(x_real_ip="203.0.113.2"))
    assert a == cap and b == cap


# --------------------------------------------------------------------------
# per-worker dilution (pinned actual behaviour)
# --------------------------------------------------------------------------


def _fresh_worker_module(name: str) -> ModuleType:
    """Import ``rpc/websocket.py`` again under another name: what a second
    uvicorn worker process holds — its own counters, same source."""
    spec = importlib.util.spec_from_file_location(f"aitbc_chain.rpc.{name}", websocket_module.__file__)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_per_ip_cap_is_per_worker_effective_ceiling_is_workers_times_cap(_cap3: None) -> None:
    """#1241 pin: counters are process-local, so ``--workers N`` multiplies the cap.

    ``aitbc-blockchain-rpc`` runs ``--workers 2``: a single peer that lands
    connections on both workers holds 2 x ``gossip_max_concurrent_connections_per_ip``
    slots. This pins the *actual* behaviour so a change to shared counters (or
    ``--workers 1``) is a deliberate edit of this test, and so size the
    configured cap for the per-worker share (prod 256 => effective 512).
    """
    cap = settings.gossip_max_concurrent_connections_per_ip
    worker_a = websocket_module
    worker_b = _fresh_worker_module("websocket_worker_b")
    assert worker_b._gossip_ip_connections is not worker_a._gossip_ip_connections
    assert worker_b._gossip_msg_rate is not worker_a._gossip_msg_rate

    nohdr = lambda i: []  # noqa: E731
    held_a, rej_a = await _flood(worker_a, ATTACKER_PEER, cap + 2, nohdr)
    held_b, rej_b = await _flood(worker_b, ATTACKER_PEER, cap + 2, nohdr)
    assert (held_a, rej_a) == (cap, 2)
    assert (held_b, rej_b) == (cap, 2)
    assert held_a + held_b == 2 * cap


@pytest.mark.asyncio
async def test_message_rate_bucket_is_per_worker() -> None:
    """The per-(ip,chain,topic) message bucket is likewise one-per-process."""
    worker_b = _fresh_worker_module("websocket_worker_b_rate")
    key = f"{ATTACKER_PEER}:{settings.chain_id}:transactions"
    a = RateLimiter(rate=2, per=60)
    b = RateLimiter(rate=2, per=60)
    assert [a.is_allowed(key) for _ in range(3)] == [True, True, False]
    assert [b.is_allowed(key) for _ in range(3)] == [True, True, False]
    assert worker_b._gossip_msg_rate is not websocket_module._gossip_msg_rate
