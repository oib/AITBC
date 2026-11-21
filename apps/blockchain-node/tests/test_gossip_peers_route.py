"""#2417: GET /rpc/gossip/peers — live gossip peer connectivity, never simulated.

The route resolves the chain's GossipBroker through the same
``_broker_for_chain``/``_connectable_chain_ids`` pair the ``/rpc/gossip/ws``
handler uses, so multi-chain hosts report each chain's own backend.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.config import settings
from aitbc_chain.gossip import GossipBroker, InMemoryGossipBackend, MeshGossipBackend, WebsocketGossipBackend
from aitbc_chain.gossip.backends.base import GossipBackend
from aitbc_chain.rpc import websocket as ws_rpc
from aitbc_chain.rpc.websocket import router


class _FakeBroker:
    """Stand-in for GossipBroker: returns a canned peer_status payload."""

    def __init__(self, status: dict[str, Any] | Exception) -> None:
        self._status = status

    async def peer_status(self) -> dict[str, Any]:
        if isinstance(self._status, Exception):
            raise self._status
        return dict(self._status)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/rpc")
    monkeypatch.setattr(ws_rpc, "_connectable_chain_ids", lambda: [settings.chain_id])
    return TestClient(app, raise_server_exceptions=False)


def test_gossip_peers_returns_structured_payload(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    status = {
        "peers": [
            {
                "name": "node1",
                "url": "wss://node1.example/rpc/gossip/ws",
                "connected": True,
                "topics": ["blocks." + settings.chain_id],
            }
        ],
        "configured": 1,
        "running": True,
        "backend": "MeshGossipBackend",
        "local_bus": {"ok": True},
    }
    monkeypatch.setattr(ws_rpc, "_broker_for_chain", lambda chain_id: _FakeBroker(status))

    resp = client.get("/rpc/gossip/peers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_id"] == settings.chain_id
    assert data["backend"] == "MeshGossipBackend"
    assert data["running"] is True
    assert data["configured"] == 1
    assert data["count"] == 1
    assert data["peers"] == status["peers"]
    assert data["local_bus"] == {"ok": True}


def test_gossip_peers_unserved_chain_is_honest_empty(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws_rpc, "_broker_for_chain", lambda chain_id: pytest.fail("must not resolve"))

    resp = client.get("/rpc/gossip/peers", params={"chain_id": "not-served"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_id"] == "not-served"
    assert data["peers"] == []
    assert data["count"] == 0
    assert data["configured"] == 0
    assert data["running"] is False
    assert "error" in data


def test_gossip_peers_broker_failure_is_honest(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ws_rpc,
        "_broker_for_chain",
        lambda chain_id: _FakeBroker(RuntimeError("backend exploded")),
    )

    resp = client.get("/rpc/gossip/peers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["peers"] == []
    assert data["count"] == 0
    assert "error" in data


# --- backend-level peer_status -------------------------------------------------


@pytest.mark.asyncio
async def test_inmemory_backend_reports_no_peers() -> None:
    status = await InMemoryGossipBackend().peer_status()
    assert status == {"peers": [], "configured": 0}


@pytest.mark.asyncio
async def test_broker_peer_status_stamps_running_and_backend() -> None:
    broker = GossipBroker(InMemoryGossipBackend())
    status = await broker.peer_status()
    assert status["running"] is False
    assert status["backend"] == "InMemoryGossipBackend"
    assert status["peers"] == []
    assert status["configured"] == 0


@pytest.mark.asyncio
async def test_websocket_backend_reports_dialed_peer() -> None:
    backend = WebsocketGossipBackend("wss://peer1.example:8443/rpc/gossip/ws")
    await backend.start()
    status = await backend.peer_status()
    assert status["configured"] == 1
    assert status["running"] is True
    (peer,) = status["peers"]
    assert peer["url"] == "wss://peer1.example:8443/rpc/gossip/ws"
    assert peer["name"]
    # Never subscribed → no live link, honestly disconnected.
    assert peer["connected"] is False
    assert peer["topics"] == []
    await backend.shutdown()


@pytest.mark.asyncio
async def test_websocket_backend_connected_with_open_topic() -> None:
    backend = WebsocketGossipBackend("wss://peer1.example/rpc/gossip/ws")
    await backend.start()
    backend._ref_counts["blocks.test"] = 1

    class _OpenWS:
        open = True

    backend._websockets["blocks.test"] = _OpenWS()
    status = await backend.peer_status()
    (peer,) = status["peers"]
    assert peer["connected"] is True
    assert peer["topics"] == ["blocks.test"]
    await backend.shutdown()


@pytest.mark.asyncio
async def test_mesh_backend_flattens_peer_status() -> None:
    peer = WebsocketGossipBackend("wss://node2.example/rpc/gossip/ws", peer_name="node2")
    await peer.start()
    peer._ref_counts["blocks.test"] = 1

    class _OpenWS:
        open = True

    peer._websockets["blocks.test"] = _OpenWS()

    mesh = MeshGossipBackend(InMemoryGossipBackend(), {"node2": peer})
    await mesh.start()
    status = await mesh.peer_status()
    assert status["configured"] == 1
    assert status["running"] is True
    assert "local_bus" in status
    (row,) = status["peers"]
    assert row["name"] == "node2"
    assert row["url"] == "wss://node2.example/rpc/gossip/ws"
    assert row["connected"] is True
    assert row["topics"] == ["blocks.test"]
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_mesh_peer_status_survives_peer_probe_failure() -> None:
    class _BrokenPeer(GossipBackend):
        async def peer_status(self) -> dict[str, Any]:
            raise RuntimeError("probe blew up")

    mesh = MeshGossipBackend(InMemoryGossipBackend(), {"bad": _BrokenPeer()})
    await mesh.start()
    status = await mesh.peer_status()
    assert status["configured"] == 1
    assert status["peers"] == []
    await mesh.shutdown()
