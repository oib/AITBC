"""Unit tests for MeshGossipBackend (fan-out publish, merged subscribe, dedup, peer loss)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aitbc_chain.gossip.broker import (
    GossipBackend,
    InMemoryGossipBackend,
    MeshGossipBackend,
    TopicSubscription,
    WebsocketGossipBackend,
    create_backend,
)


class _FlakyPeer(GossipBackend):
    """Peer that refuses to subscribe/publish until ``available`` is set."""

    def __init__(self) -> None:
        self.inner = InMemoryGossipBackend()
        self.available = False
        self.subscribe_attempts = 0
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, message: Any) -> None:
        if not self.available:
            raise RuntimeError("peer down")
        self.published.append((topic, message))
        await self.inner.publish(topic, message)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        self.subscribe_attempts += 1
        if not self.available:
            raise RuntimeError("peer down")
        return await self.inner.subscribe(topic, max_queue_size=max_queue_size)


async def _recv(sub: TopicSubscription, timeout: float = 1.0) -> Any:
    return await asyncio.wait_for(sub.get(), timeout=timeout)


async def _drain_tasks() -> None:
    # Let fire-and-forget peer publishes run.
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_publish_fans_out_to_local_and_all_peers() -> None:
    local, p1, p2 = InMemoryGossipBackend(), InMemoryGossipBackend(), InMemoryGossipBackend()
    mesh = MeshGossipBackend(local, {"p1": p1, "p2": p2})
    await mesh.start()

    l_sub = await local.subscribe("t")
    p1_sub = await p1.subscribe("t")
    p2_sub = await p2.subscribe("t")

    await mesh.publish("t", {"id": "m1", "v": 1})
    await _drain_tasks()

    assert await _recv(l_sub) == {"id": "m1", "v": 1}
    assert await _recv(p1_sub) == {"id": "m1", "v": 1}
    assert await _recv(p2_sub) == {"id": "m1", "v": 1}
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_subscribe_merges_sources_and_dedups_same_message() -> None:
    local, p1, p2 = InMemoryGossipBackend(), InMemoryGossipBackend(), InMemoryGossipBackend()
    mesh = MeshGossipBackend(local, {"p1": p1, "p2": p2})
    await mesh.start()
    sub = await mesh.subscribe("pbft.prepare.chain")

    msg = {"sender": "0xabc", "sequence_number": 7, "digest": "d"}
    # Same message arrives on every link (direct push + relays).
    await local.publish("pbft.prepare.chain", msg)
    await p1.publish("pbft.prepare.chain", msg)
    await p2.publish("pbft.prepare.chain", msg)
    # A genuinely different message must still come through.
    other = {"sender": "0xdef", "sequence_number": 7, "digest": "d"}
    await p2.publish("pbft.prepare.chain", other)

    got = [await _recv(sub), await _recv(sub)]
    assert got == [msg, other]
    with pytest.raises(asyncio.TimeoutError):
        await _recv(sub, timeout=0.2)
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_attestation_responses_sharing_block_hash_are_not_deduped() -> None:
    """Regression: several validators attest the same block; the shared ``hash``
    is a reference, not a message identity, so all responses must be delivered."""
    local, p1 = InMemoryGossipBackend(), InMemoryGossipBackend()
    mesh = MeshGossipBackend(local, {"p1": p1})
    await mesh.start()
    topic = "consensus.attest_response.chain"
    sub = await mesh.subscribe(topic)
    block_hash = "0x" + "c" * 64
    responses = [
        {"chain_id": "chain", "height": 9, "hash": block_hash, "validator": f"0x{i}", "signature": f"sig{i}"} for i in range(3)
    ]
    for r in responses:
        await p1.publish(topic, r)
    got = [await _recv(sub) for _ in responses]
    assert got == responses
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_broker_publish_dedup_keeps_distinct_attestations_but_dedups_blocks() -> None:
    from aitbc_chain.gossip.broker import GossipBroker

    backend = InMemoryGossipBackend()
    broker = GossipBroker(backend)
    att_sub = await backend.subscribe("consensus.attest_response.chain")
    blk_sub = await backend.subscribe("blocks.chain")
    h = "0x" + "d" * 64
    await broker.publish("consensus.attest_response.chain", {"hash": h, "validator": "0x1", "signature": "a"})
    await broker.publish("consensus.attest_response.chain", {"hash": h, "validator": "0x2", "signature": "b"})
    await broker.publish("blocks.chain", {"hash": h, "height": 1})
    await broker.publish("blocks.chain", {"hash": h, "height": 1, "transactions": []})  # same block, re-sent
    assert (await _recv(att_sub))["validator"] == "0x1"
    assert (await _recv(att_sub))["validator"] == "0x2"
    assert await _recv(blk_sub) == {"hash": h, "height": 1}
    with pytest.raises(asyncio.TimeoutError):
        await _recv(blk_sub, timeout=0.2)
    await broker.shutdown()


@pytest.mark.asyncio
async def test_dead_peer_does_not_block_publish_and_is_retried_on_subscribe() -> None:
    local = InMemoryGossipBackend()
    flaky = _FlakyPeer()
    mesh = MeshGossipBackend(local, {"flaky": flaky}, retry_min_delay=0.01, retry_max_delay=0.02)
    await mesh.start()

    # Subscribe while peer is down: local attaches, peer goes to retry loop.
    sub = await mesh.subscribe("blocks")
    assert flaky.subscribe_attempts >= 1

    # Publish must succeed via local even though the peer is down.
    await asyncio.wait_for(mesh.publish("blocks", {"hash": "0x1"}), timeout=0.5)
    assert await _recv(sub) == {"hash": "0x1"}
    await _drain_tasks()
    assert flaky.published == []

    # Peer comes back: retry loop attaches and messages from it flow in.
    flaky.available = True
    await asyncio.sleep(0.1)
    assert flaky.subscribe_attempts >= 2
    await flaky.inner.publish("blocks", {"hash": "0x2"})
    assert await _recv(sub) == {"hash": "0x2"}

    # And publishes now reach it.
    await mesh.publish("blocks", {"hash": "0x3"})
    await _drain_tasks()
    assert ("blocks", {"hash": "0x3"}) in flaky.published
    sub.close()
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_local_failure_is_fatal_for_subscribe() -> None:
    class _Broken(GossipBackend):
        async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
            raise RuntimeError("no redis")

    mesh = MeshGossipBackend(_Broken(), {})
    await mesh.start()
    with pytest.raises(RuntimeError, match="no redis"):
        await mesh.subscribe("blocks")
    await mesh.shutdown()


@pytest.mark.asyncio
async def test_publish_batch_fans_out() -> None:
    local, p1 = InMemoryGossipBackend(), InMemoryGossipBackend()
    mesh = MeshGossipBackend(local, {"p1": p1})
    await mesh.start()
    l_sub = await local.subscribe("blocks")
    p_sub = await p1.subscribe("blocks")
    batch = [{"hash": "0xa"}, {"hash": "0xb"}]
    await mesh.publish_batch("blocks", batch)
    await _drain_tasks()
    assert [await _recv(l_sub), await _recv(l_sub)] == batch
    assert [await _recv(p_sub), await _recv(p_sub)] == batch
    await mesh.shutdown()


def test_create_backend_mesh_builds_websocket_peers() -> None:
    backend = create_backend(
        "mesh",
        broadcast_url="redis://127.0.0.1:6379/0",
        mesh_peer_urls=[
            "wss://a.example/rpc/gossip/ws",
            " wss://b.example/rpc/gossip/ws ",
            "",
        ],
    )
    assert isinstance(backend, MeshGossipBackend)
    assert backend.peer_names == ["a.example", "b.example"]
    assert all(isinstance(p, WebsocketGossipBackend) for p in backend._peers.values())


def test_create_backend_mesh_requires_local_bus_and_unique_peers() -> None:
    with pytest.raises(ValueError, match="local bus"):
        create_backend("mesh", broadcast_url=None, mesh_peer_urls=["wss://a/rpc/gossip/ws"])
    with pytest.raises(ValueError, match="Duplicate"):
        create_backend(
            "mesh",
            broadcast_url="redis://127.0.0.1:6379/0",
            mesh_peer_urls=["wss://a/rpc/gossip/ws", "wss://a/rpc/gossip/ws"],
        )
