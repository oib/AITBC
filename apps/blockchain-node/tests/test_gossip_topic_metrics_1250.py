"""#1250: gossip metric series are keyed on a bounded label, not the raw topic.

Before: ``gossip_publications_topic_<topic>`` / ``gossip_queue_size_<topic>`` /
``gossip_subscribers_topic_<topic>`` (process-lifetime ``metrics_registry``
keys, never removed) and the ``topic`` label of
``blockchain_gossip_messages_published_total`` were minted per topic string.
``is_public_topic`` admits any dotted subtopic of ``status``/``transactions``/
``mempool``, so a remote caller could grow the registry and ``/metrics``
without bound (sandbox: 300 subtopics -> 724 new series, +50 KB per scrape).
Now only the node's own topics keep their exact name; the rest collapse to
``other.<class>``.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aitbc_chain.config import settings
from aitbc_chain.gossip import _internal
from aitbc_chain.gossip._internal import bounded_topic_label
from aitbc_chain.gossip.backends.in_memory import InMemoryGossipBackend
from aitbc_chain.metrics import MetricsRegistry, gossip_messages_published_total
from aitbc_chain.rpc import websocket as websocket_module
from aitbc.security import RateLimiter
from starlette.websockets import WebSocket, WebSocketDisconnect

CHAIN = "bc-test"


@pytest.fixture
def chains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "supported_chains", CHAIN)
    monkeypatch.setattr(settings, "gossip_backends", "")


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> MetricsRegistry:
    reg = MetricsRegistry()
    monkeypatch.setattr(_internal, "metrics_registry", reg)
    monkeypatch.setattr(_internal, "_subscriber_labels", set())
    return reg


def _gossip_series(reg: MetricsRegistry) -> set[str]:
    return {k for k in (*reg._counters, *reg._gauges) if k.startswith("gossip_")}


# --------------------------------------------------------------------------
# label derivation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic",
    [
        "blocks",
        "pbft",
        "consensus",
        "transactions",
        "status",
        "mempool",
        f"blocks.{CHAIN}",
        f"transactions.{CHAIN}",
        f"status.{CHAIN}",
        f"pbft.pre_prepare.{CHAIN}",
        f"pbft.prepare.{CHAIN}",
        f"pbft.commit.{CHAIN}",
        f"consensus.attest_request.{CHAIN}",
        f"consensus.attest_response.{CHAIN}",
    ],
)
def test_own_topics_keep_exact_name(chains: None, topic: str) -> None:
    assert bounded_topic_label(topic) == topic


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("status.a.b", "other.public"),
        ("transactions.evil", "other.public"),
        (f"transactions.{CHAIN}.evil", "other.public"),
        (f"status.junk.{CHAIN}", "other.public"),
        ("mempool.x" * 50, "other.public"),
        ("blocks.other-chain", "other.blocks"),
        (f"blocks.{CHAIN}.x", "other.blocks"),
        ("pbft.weird.bc-test", "other.pbft"),
        ("pbft.prepare.other-chain", "other.pbft"),
        ("consensus.anything", "other.consensus"),
        ("consensus.attest_request.other-chain", "other.consensus"),
        ("test_topic", "other.other"),
        ("Status.bc-test", "other.other"),
        ("", "other.other"),
        ("../etc/passwd", "other.other"),
    ],
)
def test_foreign_topics_collapse_to_class_bucket(chains: None, topic: str, expected: str) -> None:
    assert bounded_topic_label(topic) == expected


def test_label_keyspace_is_bounded(chains: None) -> None:
    topics = [f"status.{i}.{j}" for i in range(100) for j in range(50)]
    topics += [f"transactions.sub{i}" for i in range(5000)]
    topics += [f"junk-{i}" for i in range(5000)]
    topics += [f"consensus.{i}" for i in range(2000)]
    topics += [f"blocks.chain{i}" for i in range(2000)]
    topics += [f"pbft.p{i}.{CHAIN}" for i in range(2000)]
    labels = {bounded_topic_label(t) for t in topics}
    assert labels == {"other.public", "other.other", "other.consensus", "other.blocks", "other.pbft"}


def test_served_chain_ids_follow_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chain_id", "c1")
    monkeypatch.setattr(settings, "supported_chains", "c1,c2")
    monkeypatch.setattr(settings, "gossip_backends", "c3:redis://localhost:6379/0")
    for c in ("c1", "c2", "c3"):
        assert bounded_topic_label(f"blocks.{c}") == f"blocks.{c}"
    assert bounded_topic_label("blocks.c4") == "other.blocks"


# --------------------------------------------------------------------------
# registry keys through the backend
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_churn_does_not_mint_registry_keys(chains: None, registry: MetricsRegistry) -> None:
    backend = InMemoryGossipBackend()
    await backend.publish(f"blocks.{CHAIN}", {"n": 0})
    baseline = _gossip_series(registry)
    assert f"gossip_publications_topic_blocks.{CHAIN}" in baseline  # own topic keeps its exact series
    for i in range(500):
        await backend.publish(f"status.flood{i}.x", {"n": i})
    for i in range(500):
        await backend.publish(f"junk-{i}", {"n": i})
    grown = _gossip_series(registry) - baseline
    assert grown <= {"gossip_publications_topic_other.public", "gossip_publications_topic_other.other"}
    assert registry._counters["gossip_publications_topic_other.public"] == 500
    assert registry._counters["gossip_publications_total"] == 1001


@pytest.mark.asyncio
async def test_subscribe_churn_does_not_mint_gauges_and_zeroes_bucket(chains: None, registry: MetricsRegistry) -> None:
    backend = InMemoryGossipBackend()
    own = await backend.subscribe(f"blocks.{CHAIN}")
    subs = [await backend.subscribe(f"status.churn{i}") for i in range(200)]
    assert len(_gossip_series(registry)) <= 6
    # many topics, one bucket: the gauge is the aggregate, not the last topic
    assert registry._gauges["gossip_subscribers_topic_other.public"] == 200.0
    assert registry._gauges[f"gossip_subscribers_topic_blocks.{CHAIN}"] == 1.0
    for s in subs:
        s.close()
    assert registry._gauges["gossip_subscribers_topic_other.public"] == 0.0  # not a stale 1.0
    assert registry._gauges[f"gossip_subscribers_topic_blocks.{CHAIN}"] == 1.0
    own.close()
    assert registry._gauges[f"gossip_subscribers_topic_blocks.{CHAIN}"] == 0.0
    assert len(_gossip_series(registry)) <= 6


@pytest.mark.asyncio
async def test_rendered_metrics_stay_bounded(chains: None, registry: MetricsRegistry) -> None:
    backend = InMemoryGossipBackend()
    for i in range(1000):
        sub = await backend.subscribe(f"status.r{i}")
        await backend.publish(f"status.r{i}", {"n": i})
        sub.close()
    lines = registry.render_prometheus().splitlines()
    assert len(lines) < 40
    assert max(len(line) for line in lines) < 120


@pytest.mark.asyncio
async def test_inmemory_topic_table_is_collected_on_unsubscribe(chains: None, registry: MetricsRegistry) -> None:
    """Verification pin (#1250 flag 2): the backend's own per-topic table does not leak."""
    backend = InMemoryGossipBackend()
    subs = [await backend.subscribe(f"status.t{i}") for i in range(100)]
    assert len(backend._topics) == 100
    for s in subs:
        s.close()
    assert backend._topics == {}


# --------------------------------------------------------------------------
# prometheus label through the real handler
# --------------------------------------------------------------------------


def _ws(topic: str) -> WebSocket:
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
        "client": ("198.51.100.77", 4444),
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


async def _run_conn(topic: str, n: int) -> None:
    ws = _ws(topic)
    queue = [json.dumps({"probe": i}) for i in range(n)]

    async def _noop(*a: object, **k: object) -> None:
        return None

    async def _receive_text() -> str:
        if queue:
            return queue.pop(0)
        raise WebSocketDisconnect()

    ws.accept = _noop  # type: ignore[method-assign]
    ws.receive_text = _receive_text  # type: ignore[method-assign]
    ws.send_json = _noop  # type: ignore[method-assign]
    ws.close = _noop  # type: ignore[method-assign]
    await asyncio.wait_for(websocket_module.gossip_websocket(ws), timeout=10)


def _published_labels() -> dict[str, float]:
    out: dict[str, float] = {}
    for metric in gossip_messages_published_total.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                out[sample.labels["topic"]] = sample.value
    return out


@pytest.mark.asyncio
async def test_published_total_label_is_bounded_through_handler(chains: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITBC_TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 100000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100000)
    monkeypatch.setattr(websocket_module, "_gossip_msg_rate", RateLimiter(rate=100000, per=60))
    websocket_module._gossip_ip_connections.clear()

    async def _publish(topic: str, data: object, *a: object, **k: object) -> None:
        return None

    async def _subscribe(topic: str, max_queue_size: int = 100) -> _Sub:
        return _Sub()

    monkeypatch.setattr(websocket_module.gossip_broker, "publish", _publish)
    monkeypatch.setattr(websocket_module.gossip_broker, "subscribe", _subscribe)

    before = _published_labels()
    for i in range(40):
        await _run_conn(f"status.mint1250_{i}", 2)
    await _run_conn(f"transactions.{CHAIN}", 3)
    after = _published_labels()
    new = {k: v - before.get(k, 0.0) for k, v in after.items() if v != before.get(k, 0.0)}
    assert new == {"other.public": 80.0, f"transactions.{CHAIN}": 3.0}
    assert not any("mint1250" in k for k in after)
    websocket_module._gossip_ip_connections.clear()
