"""#1764: mesh subscribe() waits for peer legs when gossip_mesh_subscribe_wait_peers_enabled."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aitbc_chain.config import settings
from aitbc_chain.gossip import GossipBackend, InMemoryGossipBackend, MeshGossipBackend, TopicSubscription


class _FlakyPeer(GossipBackend):
    def __init__(self) -> None:
        self.inner = InMemoryGossipBackend()
        self.available = False
        self.subscribe_attempts = 0

    async def publish(self, topic: str, message: Any) -> None:
        if not self.available:
            raise RuntimeError("peer down")
        await self.inner.publish(topic, message)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        self.subscribe_attempts += 1
        if not self.available:
            raise RuntimeError("peer down")
        return await self.inner.subscribe(topic, max_queue_size=max_queue_size)


async def _recv(sub: TopicSubscription, timeout: float = 1.0) -> Any:
    return await asyncio.wait_for(sub.get(), timeout=timeout)


@pytest.mark.asyncio
async def test_flag_on_waits_until_flaky_peer_attaches(monkeypatch):
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", True)
    local = InMemoryGossipBackend()
    flaky = _FlakyPeer()
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=0.05, retry_max_delay=0.2)
    await mesh.start()

    async def _flip() -> None:
        await asyncio.sleep(0.12)
        flaky.available = True

    flip = asyncio.create_task(_flip())
    t0 = asyncio.get_event_loop().time()
    sub = await mesh.subscribe("consensus.attest_response.chain")
    await flip
    assert asyncio.get_event_loop().time() - t0 >= 0.1
    assert flaky.subscribe_attempts >= 2

    await flaky.inner.publish("consensus.attest_response.chain", {"hash": "0xabc", "validator": "0x1"})
    assert await _recv(sub) == {"hash": "0xabc", "validator": "0x1"}
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_flag_off_returns_before_flaky_peer_attaches(monkeypatch):
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", False)
    local = InMemoryGossipBackend()
    flaky = _FlakyPeer()
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=0.05, retry_max_delay=0.2)
    await mesh.start()

    t0 = asyncio.get_event_loop().time()
    sub = await mesh.subscribe("consensus.attest_response.chain")
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 0.08
    assert flaky.subscribe_attempts >= 1

    flaky.available = True
    await asyncio.sleep(0.15)
    await flaky.inner.publish("consensus.attest_response.chain", {"v": 2})
    assert await _recv(sub) == {"v": 2}
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_wait_bounded_by_timeout(monkeypatch):
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", True)
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_timeout_seconds", 0.15)
    local = InMemoryGossipBackend()
    flaky = _FlakyPeer()
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=0.3, retry_max_delay=0.5)
    await mesh.start()

    sub = await asyncio.wait_for(mesh.subscribe("consensus.attest_response.chain"), timeout=1.0)
    assert not flaky.available
    sub.close()
    await mesh.shutdown()
