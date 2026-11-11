"""#1764: mesh subscribe() waits for peer legs when gossip_mesh_subscribe_wait_peers_enabled."""

from __future__ import annotations

import asyncio
import time
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


class _FlakyPeerSucceedsOnAttempt(_FlakyPeer):
    """Fails subscribe until attempt ``succeed_on`` (models ~N-1 retry delays before attach)."""

    def __init__(self, succeed_on: int) -> None:
        super().__init__()
        self._succeed_on = succeed_on
        self.available = True  # availability flag unused; attempts gate success

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        self.subscribe_attempts += 1
        if self.subscribe_attempts < self._succeed_on:
            raise RuntimeError("peer down")
        return await self.inner.subscribe(topic, max_queue_size=max_queue_size)


async def _recv(sub: TopicSubscription, timeout: float = 1.0) -> Any:
    return await asyncio.wait_for(sub.get(), timeout=timeout)


@pytest.mark.asyncio
async def test_flag_on_happy_path_peer_messages_flow(monkeypatch):
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", True)
    local, p1 = InMemoryGossipBackend(), InMemoryGossipBackend()
    mesh = MeshGossipBackend(local, {"p1": p1})
    await mesh.start()
    sub = await mesh.subscribe("blocks")
    await p1.publish("blocks", {"id": "m1", "v": 1})
    assert await _recv(sub) == {"id": "m1", "v": 1}
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_flag_off_returns_before_flaky_peer_attaches(monkeypatch):
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", False)
    local = InMemoryGossipBackend()
    flaky = _FlakyPeer()
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=0.05, retry_max_delay=0.2)
    await mesh.start()

    t0 = time.monotonic()
    sub = await mesh.subscribe("blocks")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.08
    assert flaky.subscribe_attempts >= 1

    flaky.available = True
    await asyncio.sleep(0.15)
    await flaky.inner.publish("blocks", {"id": "m2", "v": 2})
    assert await _recv(sub) == {"id": "m2", "v": 2}
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_flag_on_waits_for_flaky_peer_then_immediate_delivery(monkeypatch):
    """Pin #1764: subscribe() must block on wait_for_pending_peers until retry attaches the leg."""
    monkeypatch.setattr(settings, "gossip_mesh_subscribe_wait_peers_enabled", True)
    retry_min = 0.05
    retry_max = 0.2
    local = InMemoryGossipBackend()
    # attempt 1: attach() fails; attempts 2–3: _retry_attach after two backoff sleeps.
    flaky = _FlakyPeerSucceedsOnAttempt(succeed_on=3)
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=retry_min, retry_max_delay=retry_max)
    await mesh.start()

    t0 = time.monotonic()
    sub = await mesh.subscribe("blocks")
    elapsed = time.monotonic() - t0

    min_attach_time = retry_min + min(retry_min * 2, retry_max)
    assert elapsed >= min_attach_time - 0.02, f"subscribe returned in {elapsed:.3f}s; expected >= ~{min_attach_time:.3f}s"
    assert flaky.subscribe_attempts == 3

    payload = {"id": "post-wait-immediate", "v": 1}
    await flaky.inner.publish("blocks", payload)
    assert await _recv(sub, timeout=0.25) == payload
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

    sub = await asyncio.wait_for(mesh.subscribe("blocks"), timeout=1.0)
    assert not flaky.available
    sub.close()
    await mesh.shutdown()
