"""#1257 (#1159 design v2, G5 + D3): per-chain gossip refusal metrics and the
optional per-IP aggregate ceilings.

Every metric label set stays bounded - ``chain`` is a served chain id or the
literal "unknown" (an invented chain string is never echoed), ``topic_class``
is one of public|blocks|pbft|consensus|other, ``reason`` one of
``GOSSIP_REJECT_REASONS``. The aggregate ceilings default to 0 (off), so a
single-chain host behaves exactly as before.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import pytest
from aitbc.security import RateLimiter
from aitbc_chain.config import settings
from aitbc_chain.gossip.gossip_auth import _challenge_mint_rate
from aitbc_chain.metrics import (
    GOSSIP_REJECT_REASONS,
    gossip_ws_open_connections,
    gossip_ws_rejected_total,
)
from aitbc_chain.rpc import websocket as websocket_module
from starlette.websockets import WebSocket, WebSocketDisconnect

PEER = "198.51.100.77"


@pytest.fixture(autouse=True)
def _two_chain_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AITBC_TRUSTED_PROXIES", raising=False)
    websocket_module._chain_brokers.clear()
    websocket_module._gossip_ip_connections.clear()
    websocket_module._gossip_ip_total.clear()
    monkeypatch.setattr(websocket_module, "_msg_total_limiter", None)
    monkeypatch.setattr(settings, "gossip_backends", "chain-a:memory,chain-b:memory")
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    monkeypatch.setattr(settings, "gossip_max_connections_per_ip_total", 0)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute_total", 0)
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=1_000_000, per=60))
    yield
    websocket_module._chain_brokers.clear()
    websocket_module._gossip_ip_connections.clear()
    websocket_module._gossip_ip_total.clear()


def _ws(topic: str, chain: str | None, peer: str = PEER) -> WebSocket:
    query = f"topic={quote(topic)}" + (f"&chain={quote(chain)}" if chain is not None else "")
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/rpc/gossip/ws",
        "raw_path": b"/rpc/gossip/ws",
        "query_string": query.encode(),
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


async def _run_conn(
    topic: str,
    chain: str | None,
    messages: int = 0,
    peer: str = PEER,
    hold: asyncio.Event | None = None,
) -> list[dict]:
    """Run one handler invocation; returns the JSON frames the server sent.

    With ``hold`` the connection sends its messages then waits for the event
    before disconnecting, so a test can observe state while it is open.
    """
    ws = _ws(topic, chain, peer)
    sent: list[dict] = []
    queue = [json.dumps({"probe": i}) for i in range(messages)]
    closed: list[int | None] = []

    async def _noop(*a: object, **k: object) -> None:
        return None

    async def _receive_text() -> str:
        if queue:
            return queue.pop(0)
        if hold is not None:
            await hold.wait()
        raise WebSocketDisconnect()

    async def _send_json(payload: object) -> None:
        sent.append(payload)  # type: ignore[arg-type]

    async def _close(code: int | None = None, *a: object, **k: object) -> None:
        closed.append(code)

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _send_json  # type: ignore[method-assign]
    ws.close = _close  # type: ignore[method-assign]
    await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=10)
    sent.append({"_closed": closed[0] if closed else None})
    return sent


def _count(chain: str, topic_class: str, reason: str) -> float:
    return gossip_ws_rejected_total.labels(chain=chain, topic_class=topic_class, reason=reason)._value.get()


def _frames(sent: list[dict]) -> list[dict]:
    return [f for f in sent if "_closed" not in f]


def _closed_code(sent: list[dict]) -> int | None:
    return next(f["_closed"] for f in sent if "_closed" in f)


# --- per-chain refusal metrics ------------------------------------------------


def test_unknown_chain_counts_under_literal_unknown() -> None:
    before = _count("unknown", "public", "unknown_chain")
    sent = asyncio.run(_run_conn("transactions", "never-heard-of-it"))
    assert _closed_code(sent) == 1008
    assert _count("unknown", "public", "unknown_chain") == before + 1


def test_missing_chain_on_multi_chain_host_counts_unknown_chain() -> None:
    before = _count("unknown", "public", "unknown_chain")
    sent = asyncio.run(_run_conn("transactions", None))
    assert _closed_code(sent) == 1008
    assert _count("unknown", "public", "unknown_chain") == before + 1


def test_cross_chain_topic_counts_on_the_served_chain() -> None:
    before = _count("chain-a", "public", "cross_chain_topic")
    sent = asyncio.run(_run_conn("transactions.chain-b", "chain-a"))
    assert _closed_code(sent) == 1008
    assert _count("chain-a", "public", "cross_chain_topic") == before + 1


def test_no_backend_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websocket_module, "_broker_for_chain", lambda chain_id: None)
    before = _count("chain-a", "blocks", "no_backend")
    sent = asyncio.run(_run_conn("blocks.chain-a", "chain-a"))
    assert _closed_code(sent) == 1008
    assert _count("chain-a", "blocks", "no_backend") == before + 1


def test_per_chain_connection_cap_counts_and_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 1)

    async def scenario() -> tuple[list[dict], list[dict]]:
        hold = asyncio.Event()
        first = asyncio.create_task(_run_conn("transactions", "chain-a", hold=hold))
        await asyncio.sleep(0.2)
        refused = await _run_conn("transactions", "chain-a")
        other_chain = asyncio.create_task(_run_conn("transactions", "chain-b", hold=hold))
        await asyncio.sleep(0.2)
        hold.set()
        return refused, await other_chain, await first  # type: ignore[return-value]

    before_a = _count("chain-a", "public", "conn_cap")
    before_b = _count("chain-b", "public", "conn_cap")
    refused, other, _first = asyncio.run(scenario())  # type: ignore[misc]
    assert _closed_code(refused) == 1008
    assert _closed_code(other) != 1008
    assert _count("chain-a", "public", "conn_cap") == before_a + 1
    assert _count("chain-b", "public", "conn_cap") == before_b


def test_auth_rejection_is_counted_per_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """A restricted-topic publish without auth bumps the existing reason
    counter AND the per-chain ``auth`` series."""
    from aitbc_chain.metrics import gossip_auth_rejected_total

    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    before = _count("chain-a", "blocks", "auth")
    reason_before = gossip_auth_rejected_total.labels(reason="unauthorized_publish")._value.get()
    sent = asyncio.run(_run_conn("blocks.chain-a", "chain-a", messages=1))
    assert any(f.get("error") == "Validator authentication required" for f in _frames(sent))
    assert _count("chain-a", "blocks", "auth") == before + 1
    assert gossip_auth_rejected_total.labels(reason="unauthorized_publish")._value.get() == reason_before + 1
    assert _count("chain-b", "blocks", "auth") == 0


def test_open_connection_gauge_is_per_chain_and_returns_to_zero() -> None:
    async def scenario() -> tuple[float, float]:
        hold = asyncio.Event()
        task = asyncio.create_task(_run_conn("transactions", "chain-a", hold=hold))
        await asyncio.sleep(0.2)
        seen = gossip_ws_open_connections.labels(chain="chain-a")._value.get()
        other = gossip_ws_open_connections.labels(chain="chain-b")._value.get()
        hold.set()
        await task
        return seen, other

    base_b = gossip_ws_open_connections.labels(chain="chain-b")._value.get()
    base_a = gossip_ws_open_connections.labels(chain="chain-a")._value.get()
    seen, other = asyncio.run(scenario())
    assert seen == base_a + 1
    assert other == base_b
    assert gossip_ws_open_connections.labels(chain="chain-a")._value.get() == base_a


def test_reject_reason_label_set_is_closed() -> None:
    assert set(GOSSIP_REJECT_REASONS) == {
        "unknown_chain",
        "cross_chain_topic",
        "no_backend",
        "conn_cap",
        "conn_cap_total",
        "rate",
        "rate_total",
        "auth",
    }


# --- bounded keyspace under invented chains ----------------------------------


def test_invented_chains_mint_no_buckets_counters_challenges_or_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown chain string is resolved away BEFORE any per-chain state is
    touched: no (ip, chain) slot, no rate bucket, no challenge mint, and the
    metric series count grows by at most the single literal "unknown" label."""
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    series_before = len(gossip_ws_rejected_total._metrics)  # type: ignore[attr-defined]
    buckets_before = dict(websocket_module._gossip_msg_rate._requests)
    mint_before = dict(_challenge_mint_rate._requests)

    async def scenario() -> None:
        for i in range(1000):
            sent = await _run_conn("blocks.x", f"invented-{i}")
            assert _closed_code(sent) == 1008

    asyncio.run(scenario())
    assert websocket_module._gossip_ip_connections == {}
    assert websocket_module._gossip_ip_total == {}
    assert websocket_module._gossip_msg_rate._requests == buckets_before
    assert _challenge_mint_rate._requests == mint_before
    assert len(gossip_ws_rejected_total._metrics) <= series_before + 1  # type: ignore[attr-defined]
    for labels in gossip_ws_rejected_total._metrics:  # type: ignore[attr-defined]
        assert not any(str(v).startswith("invented-") for v in labels)


# --- optional aggregate ceilings ---------------------------------------------


def test_aggregate_connection_ceiling_spans_chains_and_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_max_connections_per_ip_total", 2)

    async def scenario() -> tuple[list[dict], list[dict]]:
        hold = asyncio.Event()
        t1 = asyncio.create_task(_run_conn("transactions", "chain-a", hold=hold))
        t2 = asyncio.create_task(_run_conn("transactions", "chain-b", hold=hold))
        await asyncio.sleep(0.3)
        refused = await _run_conn("transactions", "chain-a")
        hold.set()
        await t1
        await t2
        after = await _run_conn("transactions", "chain-a")
        return refused, after

    before = _count("chain-a", "public", "conn_cap_total")
    refused, after = asyncio.run(scenario())
    assert _closed_code(refused) == 1008
    assert _count("chain-a", "public", "conn_cap_total") == before + 1
    # Slots were released: the same source connects again, and no entries linger.
    assert _closed_code(after) != 1008
    assert websocket_module._gossip_ip_total == {}
    assert websocket_module._gossip_ip_connections == {}


def test_aggregate_connection_ceiling_is_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_max_connections_per_ip_total", 1)

    async def scenario() -> list[dict]:
        hold = asyncio.Event()
        t1 = asyncio.create_task(_run_conn("transactions", "chain-a", hold=hold, peer="198.51.100.1"))
        await asyncio.sleep(0.2)
        other_ip = await _run_conn("transactions", "chain-b", peer="198.51.100.2")
        hold.set()
        await t1
        return other_ip

    other_ip = asyncio.run(scenario())
    assert _closed_code(other_ip) != 1008


def test_aggregate_ceilings_off_by_default() -> None:
    from aitbc_chain.config import ChainSettings

    fresh = ChainSettings()
    assert fresh.gossip_max_connections_per_ip_total == 0
    assert fresh.gossip_max_messages_per_minute_total == 0


def test_acquire_release_unit() -> None:
    key_a, key_b = ("203.0.113.5", "chain-a"), ("203.0.113.5", "chain-b")
    assert websocket_module._acquire_ip_connection(key_a) is None
    assert websocket_module._acquire_ip_connection(key_b) is None
    assert websocket_module._gossip_ip_total == {"203.0.113.5": 2}
    websocket_module._release_ip_connection(key_a)
    assert websocket_module._gossip_ip_total == {"203.0.113.5": 1}
    websocket_module._release_ip_connection(key_b)
    assert websocket_module._gossip_ip_total == {}
    assert websocket_module._gossip_ip_connections == {}


def test_aggregate_message_ceiling_spans_chains(monkeypatch: pytest.MonkeyPatch) -> None:
    """Total 6/min per IP: three messages on each of two chains fit under the
    per-chain buckets but the 7th message of the source is refused."""
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute_total", 6)

    async def scenario() -> tuple[list[dict], list[dict]]:
        a = await _run_conn("transactions", "chain-a", messages=4)
        b = await _run_conn("transactions", "chain-b", messages=4)
        return a, b

    before_a = _count("chain-a", "public", "rate_total")
    before_b = _count("chain-b", "public", "rate_total")
    a, b = asyncio.run(scenario())
    errors_a = [f for f in _frames(a) if f.get("error") == "Rate limit exceeded"]
    errors_b = [f for f in _frames(b) if f.get("error") == "Rate limit exceeded"]
    assert len(errors_a) == 0  # 4 <= 6
    assert len(errors_b) == 2  # messages 7 and 8 of the source
    assert _count("chain-a", "public", "rate_total") == before_a
    assert _count("chain-b", "public", "rate_total") == before_b + 2
    # Per-chain buckets were NOT the limiter: they are huge here and untouched.
    assert _count("chain-b", "public", "rate") == 0


def test_aggregate_message_ceiling_off_means_unlimited() -> None:
    sent = asyncio.run(_run_conn("transactions", "chain-a", messages=50))
    assert not [f for f in _frames(sent) if f.get("error")]


def test_per_chain_rate_limit_counts_per_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=2, per=60))
    before = _count("chain-a", "public", "rate")
    sent = asyncio.run(_run_conn("transactions", "chain-a", messages=5))
    assert len([f for f in _frames(sent) if f.get("error") == "Rate limit exceeded"]) == 3
    assert _count("chain-a", "public", "rate") == before + 3
    assert _count("chain-b", "public", "rate") == 0
