"""Tests for REST-submit tx fan-out to mesh peers.

The node's mempool is a localhost DB and nothing republishes local-bus
messages to the mesh, so a REST-submitted tx previously only reached a block
if the submitting host happened to propose. `_queue_peer_fanout` pushes the
envelope to each peer's public transactions.<chain> gossip endpoint.
"""

from __future__ import annotations

import pytest

from aitbc_chain.config import settings as aitbc_settings
from aitbc_chain.rpc import transactions as txmod


@pytest.fixture(autouse=True)
def _default_chain(monkeypatch):
    # #1260: untagged GOSSIP_MESH_PEER_URLS entries serve the default chain
    # only; these tests exercise that chain, so pin chain_id to match.
    monkeypatch.setattr(aitbc_settings, "chain_id", "ait-test")


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_publishes_envelope_to_each_peer(monkeypatch):
    published: list[tuple[str, str, dict]] = []

    class FakeBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            self.url = url

        async def start(self) -> None:
            pass

        async def publish(self, topic: str, message: dict) -> None:
            published.append((self.url, topic, message))

        async def shutdown(self) -> None:
            pass

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "wss://peer1/rpc/gossip/ws,ws://peer2:8202/rpc/gossip/ws")
    monkeypatch.setattr("aitbc_chain.gossip.backends.websocket.WebsocketGossipBackend", FakeBackend)
    # The helper does a late import; patch the attribute it resolves.
    import aitbc_chain.gossip.backends.websocket as ws_mod

    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", FakeBackend)

    tx = {"from": "0xabc", "to": "0xdef", "type": "GOVERNANCE_EXECUTE", "signature": "0xsig"}
    await txmod._fanout_transaction_to_peers("ait-test", tx)

    assert len(published) == 2
    for _url, topic, message in published:
        assert topic == "transactions.ait-test"
        assert message == {"type": "new_transaction", "tx": tx}
    assert {u for u, _, _ in published} == {
        "wss://peer1/rpc/gossip/ws",
        "ws://peer2:8202/rpc/gossip/ws",
    }


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_no_peers_is_noop(monkeypatch):
    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "")
    tx = {"from": "0xabc"}
    # Must not raise even with no peers configured.
    await txmod._fanout_transaction_to_peers("ait-test", tx)


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_no_peers_warns(monkeypatch):
    """An empty peer list must not look like a successful fan-out.

    All other logging lives per-URL *inside* the loop, so with no peers the
    helper produced no output at all — a tx submitted to a non-proposing host
    was stranded in that host's local mempool with nothing to show for it.
    """
    warnings: list[str] = []

    class RecordingLogger:
        def warning(self, msg, *args):
            warnings.append(msg % args if args else msg)

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "")
    monkeypatch.setattr(txmod, "_logger", RecordingLogger())

    await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})

    assert len(warnings) == 1
    assert "GOSSIP_MESH_PEER_URLS" in warnings[0]
    assert "ait-test" in warnings[0]


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_with_peers_does_not_warn(monkeypatch):
    """The skip warning must not fire when peers are configured."""
    warnings: list[str] = []

    class RecordingLogger:
        def warning(self, msg, *args):
            warnings.append(msg % args if args else msg)

    class FakeBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            self.url = url

        async def start(self) -> None:
            pass

        async def publish(self, topic: str, message: dict) -> None:
            pass

        async def shutdown(self) -> None:
            pass

    import aitbc_chain.gossip.backends.websocket as ws_mod

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "ws://peer:8202/rpc/gossip/ws")
    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", FakeBackend)
    monkeypatch.setattr(txmod, "_logger", RecordingLogger())

    await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})

    assert warnings == []


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_survives_peer_failure(monkeypatch):
    calls: list[str] = []

    class FailingBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            self.url = url

        async def start(self) -> None:
            raise ConnectionError("peer down")

        async def publish(self, topic: str, message: dict) -> None:
            calls.append(self.url)

        async def shutdown(self) -> None:
            pass

    import aitbc_chain.gossip.backends.websocket as ws_mod

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "ws://down:8202/rpc/gossip/ws,ws://up:8202/rpc/gossip/ws")

    class MixedBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            self.url = url

        async def start(self) -> None:
            if "down" in self.url:
                raise ConnectionError("peer down")

        async def publish(self, topic: str, message: dict) -> None:
            calls.append(self.url)

        async def shutdown(self) -> None:
            pass

    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", MixedBackend)
    await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})
    assert calls == ["ws://up:8202/rpc/gossip/ws"]


# ---------------------------------------------------------------------------
# #1215: _queue_peer_fanout must reach the app loop from sync REST handlers.
# FastAPI `def` endpoints run on the anyio threadpool — get_running_loop()
# raises there, which is why every REST submit logged "no running event loop"
# and stranded txs until a proposer turn.
# ---------------------------------------------------------------------------

import asyncio
import threading


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_queue_peer_fanout_uses_running_loop(monkeypatch):
    ran: list[str] = []

    async def _fake(chain_id, tx_data):
        ran.append(chain_id)

    monkeypatch.setattr(txmod, "_fanout_transaction_to_peers", _fake)
    txmod._queue_peer_fanout("ait-test", {"from": "0xabc"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ran == ["ait-test"]


def test_queue_peer_fanout_falls_back_to_registered_loop(monkeypatch):
    """Sync handler path: schedule onto the lifespan-registered main loop."""
    ran = threading.Event()
    seen: list[str] = []

    async def _fake(chain_id, tx_data):
        seen.append(chain_id)
        ran.set()

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(txmod, "_fanout_transaction_to_peers", _fake)
        monkeypatch.setattr(txmod, "_PEER_FANOUT_LOOP", loop)
        txmod._queue_peer_fanout("ait-test", {"from": "0xabc"})
        assert ran.wait(timeout=5)
        assert seen == ["ait-test"]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()


def test_queue_peer_fanout_warns_when_no_loop_anywhere(monkeypatch):
    warnings: list[str] = []

    class RecordingLogger:
        def warning(self, msg, *args):
            warnings.append(msg % args if args else msg)

    async def _fake(chain_id, tx_data):  # pragma: no cover - must never run
        raise AssertionError("fan-out ran without a loop")

    monkeypatch.setattr(txmod, "_fanout_transaction_to_peers", _fake)
    monkeypatch.setattr(txmod, "_PEER_FANOUT_LOOP", None)
    monkeypatch.setattr(txmod, "_logger", RecordingLogger())

    txmod._queue_peer_fanout("ait-test", {"from": "0xabc"})  # must not raise
    assert any("no event loop" in w for w in warnings)


# ---------------------------------------------------------------------------
# #2361 — relay outcome must reach the submit response
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_returns_relay_summary(monkeypatch):
    """All peers accepted → status ok; the summary feeds the submit response."""

    class FakeBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            pass

        async def start(self) -> None:
            pass

        async def publish(self, topic: str, message: dict) -> None:
            pass

        async def shutdown(self) -> None:
            pass

    import aitbc_chain.gossip.backends.websocket as ws_mod

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "ws://p1:8202/rpc/gossip/ws,ws://p2:8202/rpc/gossip/ws")
    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", FakeBackend)

    out = await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})
    assert out == {"status": "ok", "attempted": 2, "accepted": 2}


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_summary_partial_and_failed(monkeypatch):
    class MixedBackend:
        def __init__(self, url: str, chain_id: str | None = None):
            self.url = url

        async def start(self) -> None:
            if "down" in self.url:
                raise ConnectionError("peer down")

        async def publish(self, topic: str, message: dict) -> None:
            pass

        async def shutdown(self) -> None:
            pass

    import aitbc_chain.gossip.backends.websocket as ws_mod

    monkeypatch.setattr(
        aitbc_settings,
        "gossip_mesh_peer_urls",
        "ws://down:8202/rpc/gossip/ws,ws://up:8202/rpc/gossip/ws",
    )
    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", MixedBackend)
    out = await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})
    assert out == {"status": "partial", "attempted": 2, "accepted": 1}

    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "ws://down:8202/rpc/gossip/ws")
    out = await txmod._fanout_transaction_to_peers("ait-test", {"from": "0xabc"})
    assert out == {"status": "failed", "attempted": 1, "accepted": 0}


def test_await_peer_fanout_timeout_reports_pending(monkeypatch):
    import concurrent.futures

    fut: concurrent.futures.Future = concurrent.futures.Future()  # never resolves
    monkeypatch.setenv("TX_FANOUT_WAIT_SECONDS", "0.01")
    out = txmod._await_peer_fanout(fut, "ait-test")
    assert out == {"status": "pending", "attempted": None, "accepted": None}


def test_await_peer_fanout_none_and_task_report_nothing():
    assert txmod._await_peer_fanout(None, "ait-test") is None
    # An asyncio.Task cannot be waited on from a sync caller — stays fire-and-forget.
    loop = asyncio.new_event_loop()
    try:

        async def _noop() -> dict:
            return {"status": "ok"}

        task = loop.create_task(_noop())
        assert txmod._await_peer_fanout(task, "ait-test") is None
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    finally:
        loop.close()


def test_fanout_response_fields_warns_on_stranded_tx(monkeypatch):
    monkeypatch.setattr(aitbc_settings, "enable_block_production", False)
    fields = txmod._fanout_response_fields({"status": "failed", "attempted": 2, "accepted": 0})
    assert fields["peer_relay"]["status"] == "failed"
    assert "nonce slot" in fields["warning"]

    # Same relay on a proposing host: local mempool suffices — no warning.
    monkeypatch.setattr(aitbc_settings, "enable_block_production", True)
    fields = txmod._fanout_response_fields({"status": "failed", "attempted": 2, "accepted": 0})
    assert "warning" not in fields

    # Skipped (no peers) on a non-proposer is the original silent-strand case.
    monkeypatch.setattr(aitbc_settings, "enable_block_production", False)
    fields = txmod._fanout_response_fields({"status": "skipped", "attempted": 0, "accepted": 0})
    assert "warning" in fields

    fields = txmod._fanout_response_fields({"status": "ok", "attempted": 2, "accepted": 2})
    assert fields == {"peer_relay": {"status": "ok", "attempted": 2, "accepted": 2}}

    assert txmod._fanout_response_fields(None) == {}
