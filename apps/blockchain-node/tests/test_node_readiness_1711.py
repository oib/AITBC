"""#1711: node-engine readiness heartbeat + gossip transport health probes.

The consensus engine (aitbc_chain.main) has no HTTP surface; the RPC
/ready probe lives in a separate process. The heartbeat file is the
cross-process signal: missing/stale/degraded => not ready. Pins cover the
writer, the file reader, the /ready check, and each backend's health().
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from aitbc_chain.gossip.backends.broadcast import BroadcastGossipBackend
from aitbc_chain.gossip.backends.mesh import MeshGossipBackend
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.readiness import NodeReadinessHeartbeat, read_heartbeat


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_writes_ready_file(tmp_path: Path) -> None:
    hb = NodeReadinessHeartbeat(tmp_path / "ready.json", interval_seconds=1.0)
    hb.register_probe("gossip", lambda: _ok())
    await hb._write_once()
    data = read_heartbeat(tmp_path / "ready.json")
    assert data is not None
    assert data["status"] == "ready"
    assert data["components"]["gossip"]["ok"] is True
    assert data["pid"] > 0


async def _ok() -> dict:
    return {"ok": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_degraded_on_failed_probe(tmp_path: Path) -> None:
    async def bad() -> dict:
        return {"ok": False, "detail": "peer ws down"}

    hb = NodeReadinessHeartbeat(tmp_path / "ready.json", interval_seconds=1.0)
    hb.register_probe("gossip", bad)
    await hb._write_once()
    data = read_heartbeat(tmp_path / "ready.json")
    assert data["status"] == "degraded"
    assert data["components"]["gossip"]["detail"] == "peer ws down"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_probe_exception_fails_closed(tmp_path: Path) -> None:
    async def boom() -> dict:
        raise RuntimeError("probe crashed")

    hb = NodeReadinessHeartbeat(tmp_path / "ready.json", interval_seconds=1.0)
    hb.register_probe("gossip", boom)
    await hb._write_once()
    data = read_heartbeat(tmp_path / "ready.json")
    assert data["status"] == "degraded"
    assert "probe raised" in data["components"]["gossip"]["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_stop_removes_file(tmp_path: Path) -> None:
    path = tmp_path / "ready.json"
    hb = NodeReadinessHeartbeat(path, interval_seconds=60.0)
    hb.register_probe("gossip", _ok)
    await hb.start()
    await asyncio.sleep(0.05)
    assert path.exists()
    await hb.stop()
    assert not path.exists()


@pytest.mark.unit
def test_read_heartbeat_missing_and_malformed(tmp_path: Path) -> None:
    assert read_heartbeat(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert read_heartbeat(bad) is None
    bad.write_text(json.dumps([1, 2, 3]))
    assert read_heartbeat(bad) is None


@pytest.mark.unit
def test_check_node_engine_ready_states(tmp_path: Path, monkeypatch) -> None:
    """The /ready check: missing, stale, degraded all raise; fresh ready passes."""
    import aitbc_chain.app as app_mod
    from aitbc_chain.config import settings

    path = tmp_path / "ready.json"
    monkeypatch.setattr(settings, "node_engine_ready_file", str(path))
    monkeypatch.setattr(settings, "node_engine_ready_max_age_seconds", 45.0)

    # missing
    with pytest.raises(RuntimeError, match="missing or unreadable"):
        app_mod._check_node_engine_ready()

    # stale
    path.write_text(json.dumps({"ts": time.time() - 120, "status": "ready", "components": {}}))
    with pytest.raises(RuntimeError, match="stale"):
        app_mod._check_node_engine_ready()

    # degraded
    path.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "status": "degraded",
                "components": {"gossip": {"ok": False, "detail": "peer ws down"}},
            }
        )
    )
    with pytest.raises(RuntimeError, match="degraded"):
        app_mod._check_node_engine_ready()

    # ready
    path.write_text(json.dumps({"ts": time.time(), "status": "ready", "components": {"gossip": {"ok": True}}}))
    app_mod._check_node_engine_ready()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_health_pings_redis() -> None:
    backend = BroadcastGossipBackend("redis://127.0.0.1:6379")
    assert (await backend.health())["ok"] is False  # not started
    backend._running = True

    class FakeRedis:
        async def ping(self):
            return True

    backend._redis = FakeRedis()
    assert (await backend.health())["ok"] is True

    class DeadRedis:
        async def ping(self):
            raise ConnectionError("refused")

    backend._redis = DeadRedis()
    health = await backend.health()
    assert health["ok"] is False
    assert "ping failed" in health["detail"]


class _FakeWS:
    def __init__(self, open_: bool) -> None:
        self.open = open_


@pytest.mark.unit
@pytest.mark.asyncio
async def test_websocket_health_requires_open_topic_links() -> None:
    backend = WebsocketGossipBackend("wss://peer.example/rpc/gossip/ws")
    # No subscriptions -> vacuously ok.
    assert (await backend.health())["ok"] is True
    backend._ref_counts["consensus.attest_request.ch"] = 1
    # Subscribed but no ws -> not ok.
    assert (await backend.health())["ok"] is False
    backend._websockets["consensus.attest_request.ch"] = _FakeWS(False)
    assert (await backend.health())["ok"] is False
    backend._websockets["consensus.attest_request.ch"] = _FakeWS(True)
    health = await backend.health()
    assert health["ok"] is True
    assert health["topics"] == ["consensus.attest_request.ch"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mesh_health_needs_local_bus_and_a_peer() -> None:
    class Local:
        async def health(self):
            return {"ok": True}

    class Peer:
        def __init__(self, ok: bool, topics: list[str] | None = None) -> None:
            self._ok = ok
            self._topics = topics if topics is not None else (["consensus.attest_request.ch"] if ok else [])

        async def health(self):
            return {"ok": self._ok, "topics": self._topics}

    mesh = MeshGossipBackend(Local(), {"p1": Peer(True), "p2": Peer(False)})
    health = await mesh.health()
    assert health["ok"] is True
    assert health["peers_connected"] == 1
    assert health["peers_configured"] == 2

    mesh_all_dead = MeshGossipBackend(Local(), {"p1": Peer(False)})
    assert (await mesh_all_dead.health())["ok"] is False

    # #1711 rework: a peer whose health is ok but holds ZERO subscribed
    # topic links (never completed a subscribe — the ws backend's
    # vacuous-ok case) must NOT count as connected.
    mesh_vacuous = MeshGossipBackend(Local(), {"p1": Peer(True, topics=[])})
    vacuous = await mesh_vacuous.health()
    assert vacuous["ok"] is False
    assert vacuous["peers_connected"] == 0

    class DeadLocal:
        async def health(self):
            return {"ok": False, "detail": "redis down"}

    mesh_no_local = MeshGossipBackend(DeadLocal(), {})
    health = await mesh_no_local.health()
    assert health["ok"] is False
