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
async def test_fanout_no_peers_is_noop(monkeypatch):
    monkeypatch.setattr(aitbc_settings, "gossip_mesh_peer_urls", "")
    tx = {"from": "0xabc"}
    # Must not raise even with no peers configured.
    await txmod._fanout_transaction_to_peers("ait-test", tx)


@pytest.mark.anyio
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
