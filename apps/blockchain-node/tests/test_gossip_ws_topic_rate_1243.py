"""#1243: the gossip websocket message budget is shared across a bounded set of
topic classes, not minted per topic string.

``_gossip_msg_rate`` used to key on ``{ip}:{chain}:{topic}``. ``is_public_topic``
admits any dotted subtopic of ``status``/``transactions``/``mempool``, so N
connections on N subtopics got N x ``gossip_max_messages_per_minute`` from one
source (~16k accepted against 2000 on the A2 mesh with 8 topics). The key is
now ``{ip}:{chain}:{class}`` with class in
``public | blocks | pbft | consensus | other``.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aitbc_chain.config import settings
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from starlette.websockets import WebSocket, WebSocketDisconnect

PEER = "198.51.100.88"
LIMIT = 5


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
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", LIMIT)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 1000)
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=LIMIT, per=60))
    published: list[str] = []

    async def _publish(topic: str, data: object, *a: object, **k: object) -> None:
        published.append(topic)

    async def _subscribe(topic: str, max_queue_size: int = 100) -> _Sub:
        return _Sub()

    monkeypatch.setattr(websocket_module.gossip_broker, "publish", _publish)
    monkeypatch.setattr(websocket_module.gossip_broker, "subscribe", _subscribe)
    websocket_module._gossip_ip_connections.clear()
    yield published
    websocket_module._gossip_ip_connections.clear()


async def _run_conn(topic: str, n_messages: int, peer: str = PEER) -> list[dict]:
    """One connection on ``topic`` sending ``n_messages``; returns what the server sent."""
    ws = _ws(topic, peer)
    sent: list[dict] = []
    queue = [json.dumps({"probe": i}) for i in range(n_messages)]

    async def _noop(*a: object, **k: object) -> None:
        return None

    async def _receive_text() -> str:
        if queue:
            return queue.pop(0)
        raise WebSocketDisconnect()

    async def _send_json(payload: object) -> None:
        sent.append(payload)  # type: ignore[arg-type]

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _send_json  # type: ignore[method-assign]
    ws.close = _noop  # type: ignore[method-assign]
    await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=10)
    return sent


# --------------------------------------------------------------------------
# class derivation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("transactions", "public"),
        ("transactions.bc-2", "public"),
        ("status.a.b.c", "public"),
        ("mempool.whatever.depth.never.ends", "public"),
        ("blocks", "blocks"),
        ("blocks.bc-2", "blocks"),
        ("pbft.prepare.bc-2", "pbft"),
        ("consensus.attest_request.bc-2", "consensus"),
        ("consensus.attest_response.bc-2", "consensus"),
        # prefix confusion, case variants, junk: never public, never a new class
        ("statuses", "other"),
        ("transactionsX.a", "other"),
        ("Transactions.a", "other"),
        ("consensus_x", "other"),
        ("", "other"),
        ("../etc/passwd", "other"),
        ("random.topic", "other"),
    ],
)
def test_rate_class(topic: str, expected: str) -> None:
    assert websocket_module._gossip_rate_class(topic) == expected


def test_keyspace_per_identity_is_bounded() -> None:
    topics = [f"status.{i}.{j}" for i in range(100) for j in range(50)]
    topics += [f"transactions.sub{i}" for i in range(5000)]
    topics += [f"junk-{i}" for i in range(5000)]
    topics += [f"consensus.{i}" for i in range(2000)] + ["blocks", "pbft", "pbft.x.y"]
    keys = {websocket_module._gossip_rate_key(PEER, "bc-2", t) for t in topics}
    assert keys <= {f"{PEER}:bc-2:{c}" for c in ("public", "blocks", "pbft", "consensus", "other")}
    assert len(keys) == 5


def test_identity_and_chain_still_separate_budgets() -> None:
    k = websocket_module._gossip_rate_key
    assert k("203.0.113.1", "bc-2", "status.a") != k("203.0.113.2", "bc-2", "status.a")
    assert k(PEER, "bc-2", "status.a") != k(PEER, "bc-3", "status.a")
    assert k(PEER, "bc-2", "status.a") == k(PEER, "bc-2", "transactions.z")  # same class, one budget


def test_restricted_class_not_starved_by_public_flood() -> None:
    rl = RateLimiter(rate=LIMIT, per=60)
    pub = websocket_module._gossip_rate_key(PEER, "bc-2", "transactions.flood")
    con = websocket_module._gossip_rate_key(PEER, "bc-2", "consensus.attest_request.bc-2")
    blk = websocket_module._gossip_rate_key(PEER, "bc-2", "blocks.bc-2")
    assert [rl.is_allowed(pub) for _ in range(LIMIT + 3)] == [True] * LIMIT + [False] * 3
    # a validator's consensus and block traffic from the same ip is unaffected
    assert all(rl.is_allowed(con) for _ in range(LIMIT))
    assert all(rl.is_allowed(blk) for _ in range(LIMIT))


# --------------------------------------------------------------------------
# through the real handler
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subtopic_multiplication_collapses_to_one_budget(harness: list[str]) -> None:
    """8 public subtopics x 10 messages from one peer: exactly LIMIT accepted, not 8 x LIMIT."""
    replies: list[dict] = []
    for i in range(8):
        replies += await _run_conn(f"status.probe{i}", 10)
    assert len(harness) == LIMIT
    assert sum(1 for r in replies if "Rate limit" in str(r)) == 8 * 10 - LIMIT


@pytest.mark.asyncio
async def test_mixed_public_roots_share_one_budget(harness: list[str]) -> None:
    for topic in ("status.a", "transactions.b", "mempool.c", "status.d", "transactions.e"):
        await _run_conn(topic, 4)
    assert len(harness) == LIMIT


@pytest.mark.asyncio
async def test_invented_topics_cannot_mint_budget_by_churn(harness: list[str]) -> None:
    """Unauthenticated junk topics are closed on the first message, but the
    rate check runs first: 30 distinct junk topics must share one budget."""
    replies: list[dict] = []
    for i in range(30):
        replies += await _run_conn(f"junk-topic-{i}", 1)
    unauthorized = sum(1 for r in replies if "Topic not authorized" in str(r))
    limited = sum(1 for r in replies if "Rate limit" in str(r))
    assert unauthorized == LIMIT
    assert limited == 30 - LIMIT
    assert harness == []


@pytest.mark.asyncio
async def test_legit_multi_topic_client_within_budget_is_unaffected(harness: list[str]) -> None:
    """A client that uses several public subtopics within the aggregate budget is not limited."""
    replies: list[dict] = []
    for topic in ("transactions.bc-2", "status.bc-2", "mempool.bc-2"):
        replies += await _run_conn(topic, 1)
    replies += await _run_conn("transactions.bc-2", 1)
    assert len(harness) == 4
    assert not any("Rate limit" in str(r) for r in replies)


@pytest.mark.asyncio
async def test_other_identity_keeps_its_own_budget(harness: list[str]) -> None:
    await _run_conn("status.x", 10)
    assert len(harness) == LIMIT
    await _run_conn("status.x", 10, peer="203.0.113.99")
    assert len(harness) == 2 * LIMIT
