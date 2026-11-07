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


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_publishes_envelope_to_each_peer(monkeypatch):
    published: list[tuple[str, str, dict]] = []

    class FakeBackend:
        def __init__(self, url: str):
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
        def __init__(self, url: str):
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
        def __init__(self, url: str):
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
        def __init__(self, url: str):
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
