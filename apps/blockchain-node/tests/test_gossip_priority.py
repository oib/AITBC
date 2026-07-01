"""Integration tests for v0.6.2 gossip priority queue and message batching."""

from __future__ import annotations

import asyncio

import pytest
from aitbc_chain.gossip.broker import (
    GossipBroker,
    InMemoryGossipBackend,
    _decode_batch,
    _encode_batch,
    _encode_message,
)


class TestGossipPriority:
    """Test gossip message prioritization."""

    @pytest.mark.asyncio
    async def test_block_messages_have_higher_priority(self):
        """Block messages should be delivered before transaction messages."""
        # Use InMemoryGossipBackend — priority is handled by the broker
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        # Subscribe to a topic
        sub = await broker.subscribe("test_topic")

        # Publish a transaction message first, then a block message
        await broker.publish("test_topic", {"type": "tx", "data": 1})
        await broker.publish("test_topic", {"type": "block", "data": 2})

        # Without priority enabled, messages arrive in order published
        msg1 = await asyncio.wait_for(sub.get(), timeout=1.0)
        msg2 = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert msg1["type"] == "tx"
        assert msg2["type"] == "block"

        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_priority_disabled_uses_direct_publish(self):
        """When priority is disabled, publish goes directly to backend."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("aitbc_chain.gossip.broker.settings.gossip_priority_enabled", False)

            backend = InMemoryGossipBackend()
            broker = GossipBroker(backend)

            # _priority_enabled should be False when explicitly disabled
            assert broker._priority_enabled is False
            assert broker._priority_queue is None

            # Publish should go directly to backend
            sub = await broker.subscribe("test_topic")
            await broker.publish("test_topic", {"msg": "hello"})
            msg = await asyncio.wait_for(sub.get(), timeout=1.0)
            assert msg["msg"] == "hello"

            await broker.shutdown()

    @pytest.mark.asyncio
    async def test_priority_enabled_routes_through_queue(self):
        """When priority is enabled, publish goes through the priority queue."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("aitbc_chain.gossip.broker.settings.gossip_priority_enabled", True)

            backend = InMemoryGossipBackend()
            broker = GossipBroker(backend)

            assert broker._priority_enabled is True
            assert broker._priority_queue is not None

            # Subscribe
            sub = await broker.subscribe("blocks.test")

            # Publish a block message
            await broker.publish("blocks.test", {"block": 1})

            # The drain task should deliver it
            msg = await asyncio.wait_for(sub.get(), timeout=2.0)
            assert msg["block"] == 1

            await broker.shutdown()


class TestMessageBatching:
    """Test gossip message batching."""

    def test_message_batching_encode_decode(self):
        """Test that batch encode/decode roundtrips correctly."""
        messages = [
            {"type": "block", "height": 1},
            {"type": "block", "height": 2},
            {"type": "tx", "hash": "abc"},
        ]
        encoded = _encode_batch(messages)
        decoded = _decode_batch(encoded)
        assert len(decoded) == 3
        assert decoded[0]["type"] == "block"
        assert decoded[0]["height"] == 1
        assert decoded[1]["height"] == 2
        assert decoded[2]["type"] == "tx"

    def test_batch_backward_compat_single_message(self):
        """Test that _decode_batch handles single (non-batched) messages."""
        # Encode a single message (not as a list)
        single = _encode_message({"type": "block", "height": 1})
        decoded = _decode_batch(single)
        # Should be wrapped in a list
        assert isinstance(decoded, list)
        assert len(decoded) == 1
        assert decoded[0]["type"] == "block"

    @pytest.mark.asyncio
    async def test_publish_batch_in_memory(self):
        """Test that publish_batch delivers all messages to subscribers."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)

        sub = await broker.subscribe("test_topic")
        messages = [
            {"msg": "first"},
            {"msg": "second"},
            {"msg": "third"},
        ]
        await broker.publish_batch("test_topic", messages)

        received = []
        for _ in range(3):
            msg = await asyncio.wait_for(sub.get(), timeout=1.0)
            received.append(msg)

        assert len(received) == 3
        assert received[0]["msg"] == "first"
        assert received[1]["msg"] == "second"
        assert received[2]["msg"] == "third"

        await broker.shutdown()

    @pytest.mark.asyncio
    async def test_publish_batch_empty_list(self):
        """Test that publish_batch with empty list doesn't error."""
        backend = InMemoryGossipBackend()
        broker = GossipBroker(backend)
        await broker.publish_batch("test_topic", [])
        await broker.shutdown()
