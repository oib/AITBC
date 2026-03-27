"""Test suite for Gossip Network - Message broadcasting and network topology."""

from __future__ import annotations

import pytest
import asyncio
from typing import Generator, Any
from unittest.mock import AsyncMock, patch

from aitbc_chain.gossip.broker import (
    GossipBackend,
    InMemoryGossipBackend,
    BroadcastGossipBackend,
    TopicSubscription
)


class TestInMemoryGossipBackend:
    """Test in-memory gossip backend functionality."""

    @pytest.fixture
    def backend(self) -> InMemoryGossipBackend:
        """Create an in-memory gossip backend."""
        return InMemoryGossipBackend()

    @pytest.mark.asyncio
    async def test_backend_initialization(self, backend: InMemoryGossipBackend) -> None:
        """Test backend initialization."""
        assert backend._topics == {}
        assert backend._lock is not None

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, backend: InMemoryGossipBackend) -> None:
        """Test publishing when no subscribers exist."""
        # Should not raise an exception
        await backend.publish("test_topic", {"message": "test"})
        
        # Topics should remain empty
        assert backend._topics == {}

    @pytest.mark.asyncio
    async def test_subscribe_single_subscriber(self, backend: InMemoryGossipBackend) -> None:
        """Test subscribing to a topic."""
        subscription = await backend.subscribe("test_topic")
        
        assert subscription.topic == "test_topic"
        assert subscription.queue is not None
        assert subscription._unsubscribe is not None
        
        # Topic should be registered
        assert "test_topic" in backend._topics
        assert len(backend._topics["test_topic"]) == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_subscribers(self, backend: InMemoryGossipBackend) -> None:
        """Test multiple subscribers to the same topic."""
        sub1 = await backend.subscribe("test_topic")
        sub2 = await backend.subscribe("test_topic")
        sub3 = await backend.subscribe("test_topic")
        
        # All should be registered
        assert len(backend._topics["test_topic"]) == 3
        assert sub1.queue in backend._topics["test_topic"]
        assert sub2.queue in backend._topics["test_topic"]
        assert sub3.queue in backend._topics["test_topic"]

    @pytest.mark.asyncio
    async def test_publish_to_single_subscriber(self, backend: InMemoryGossipBackend) -> None:
        """Test publishing to a single subscriber."""
        subscription = await backend.subscribe("test_topic")
        
        message = {"data": "test_message"}
        await backend.publish("test_topic", message)
        
        # Message should be in queue
        received = await subscription.queue.get()
        assert received == message

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self, backend: InMemoryGossipBackend) -> None:
        """Test publishing to multiple subscribers."""
        sub1 = await backend.subscribe("test_topic")
        sub2 = await backend.subscribe("test_topic")
        sub3 = await backend.subscribe("test_topic")
        
        message = {"data": "broadcast_message"}
        await backend.publish("test_topic", message)
        
        # All subscribers should receive the message
        received1 = await sub1.queue.get()
        received2 = await sub2.queue.get()
        received3 = await sub3.queue.get()
        
        assert received1 == message
        assert received2 == message
        assert received3 == message

    @pytest.mark.asyncio
    async def test_publish_different_topics(self, backend: InMemoryGossipBackend) -> None:
        """Test publishing to different topics."""
        sub1 = await backend.subscribe("topic1")
        sub2 = await backend.subscribe("topic2")
        
        message1 = {"topic": "topic1", "data": "message1"}
        message2 = {"topic": "topic2", "data": "message2"}
        
        await backend.publish("topic1", message1)
        await backend.publish("topic2", message2)
        
        # Each subscriber should only receive their topic's message
        received1 = await sub1.queue.get()
        received2 = await sub2.queue.get()
        
        assert received1 == message1
        assert received2 == message2
        
        # Queues should be empty now
        assert sub1.queue.empty()
        assert sub2.queue.empty()

    @pytest.mark.asyncio
    async def test_unsubscribe_single_subscriber(self, backend: InMemoryGossipBackend) -> None:
        """Test unsubscribing a single subscriber."""
        subscription = await backend.subscribe("test_topic")
        
        # Verify subscription exists
        assert len(backend._topics["test_topic"]) == 1
        
        # Unsubscribe
        subscription.close()
        
        # Give time for async cleanup
        await asyncio.sleep(0.01)
        
        # Topic should be removed when no subscribers left
        assert "test_topic" not in backend._topics

    @pytest.mark.asyncio
    async def test_unsubscribe_multiple_subscribers(self, backend: InMemoryGossipBackend) -> None:
        """Test unsubscribing when multiple subscribers exist."""
        sub1 = await backend.subscribe("test_topic")
        sub2 = await backend.subscribe("test_topic")
        sub3 = await backend.subscribe("test_topic")
        
        # Verify all subscriptions exist
        assert len(backend._topics["test_topic"]) == 3
        
        # Unsubscribe one
        sub2.close()
        await asyncio.sleep(0.01)
        
        # Should still have 2 subscribers
        assert len(backend._topics["test_topic"]) == 2
        assert sub1.queue in backend._topics["test_topic"]
        assert sub3.queue in backend._topics["test_topic"]
        
        # Unsubscribe another
        sub1.close()
        await asyncio.sleep(0.01)
        
        # Should still have 1 subscriber
        assert len(backend._topics["test_topic"]) == 1
        assert sub3.queue in backend._topics["test_topic"]
        
        # Unsubscribe last one
        sub3.close()
        await asyncio.sleep(0.01)
        
        # Topic should be removed
        assert "test_topic" not in backend._topics

    @pytest.mark.asyncio
    async def test_queue_size_limit(self, backend: InMemoryGossipBackend) -> None:
        """Test queue size limits."""
        # Create subscription with small queue
        subscription = await backend.subscribe("test_topic", max_queue_size=2)
        
        # Fill queue to capacity
        await backend.publish("test_topic", "message1")
        await backend.publish("test_topic", "message2")
        
        # Queue should be full
        assert subscription.queue.full()
        
        # Third message should be handled (depends on queue behavior)
        # This test verifies the queue limit is respected
        await backend.publish("test_topic", "message3")
        
        # Should be able to get first two messages
        assert await subscription.queue.get() == "message1"
        assert await subscription.queue.get() == "message2"

    @pytest.mark.asyncio
    async def test_shutdown(self, backend: InMemoryGossipBackend) -> None:
        """Test backend shutdown."""
        # Add some subscriptions
        sub1 = await backend.subscribe("topic1")
        sub2 = await backend.subscribe("topic2")
        sub3 = await backend.subscribe("topic2")
        
        assert len(backend._topics) == 2
        
        # Shutdown
        await backend.shutdown()
        
        # All topics should be cleared
        assert len(backend._topics) == 0

    @pytest.mark.asyncio
    async def test_concurrent_publish_subscribe(self, backend: InMemoryGossipBackend) -> None:
        """Test concurrent publishing and subscribing."""
        subscriptions = []
        
        # Create multiple subscribers
        for i in range(5):
            sub = await backend.subscribe("concurrent_topic")
            subscriptions.append(sub)
        
        # Publish messages concurrently
        messages = [f"message_{i}" for i in range(10)]
        publish_tasks = [
            backend.publish("concurrent_topic", msg) 
            for msg in messages
        ]
        
        await asyncio.gather(*publish_tasks)
        
        # Each subscriber should receive all messages
        for sub in subscriptions:
            received_messages = []
            
            # Collect all messages (with timeout)
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(sub.queue.get(), timeout=0.1)
                    received_messages.append(msg)
                except asyncio.TimeoutError:
                    break
            
            assert len(received_messages) == 10
            assert set(received_messages) == set(messages)


class TestTopicSubscription:
    """Test topic subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscription_iteration(self) -> None:
        """Test iterating over subscription messages."""
        backend = InMemoryGossipBackend()
        subscription = await backend.subscribe("iter_test")
        
        # Publish some messages
        messages = ["msg1", "msg2", "msg3"]
        for msg in messages:
            await backend.publish("iter_test", msg)
        
        # Iterate through messages
        received = []
        async for message in subscription:
            received.append(message)
            if len(received) >= len(messages):
                break
        
        assert received == messages

    @pytest.mark.asyncio
    async def test_subscription_context_manager(self) -> None:
        """Test subscription as context manager."""
        backend = InMemoryGossipBackend()
        
        async with await backend.subscribe("context_test") as subscription:
            assert subscription.topic == "context_test"
            assert subscription.queue is not None
        
        # After context exit, subscription should be cleaned up
        await asyncio.sleep(0.01)
        assert "context_test" not in backend._topics


class TestBroadcastGossipBackend:
    """Test broadcast gossip backend functionality."""

    @pytest.fixture
    def mock_broadcast(self) -> AsyncMock:
        """Create a mock broadcast instance."""
        broadcast = AsyncMock()
        broadcast.connect = AsyncMock()
        broadcast.publish = AsyncMock()
        broadcast.subscribe = AsyncMock()
        return broadcast

    @pytest.mark.asyncio
    async def test_backend_initialization(self, mock_broadcast: AsyncMock) -> None:
        """Test backend initialization with mock broadcast."""
        with patch('aitbc_chain.gossip.broker.Broadcast', return_value=mock_broadcast):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            assert backend._broadcast == mock_broadcast
            assert backend._tasks == set()
            assert backend._lock is not None
            assert backend._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_broadcast: AsyncMock) -> None:
        """Test starting and stopping the backend."""
        with patch('aitbc_chain.gossip.broker.Broadcast', return_value=mock_broadcast):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            # Start
            await backend.start()
            assert backend._running is True
            mock_broadcast.connect.assert_called_once()
            
            # Stop (shutdown)
            await backend.shutdown()
            assert backend._running is False

    @pytest.mark.asyncio
    async def test_publish_when_not_running(self, mock_broadcast: AsyncMock) -> None:
        """Test publishing when backend is not started."""
        with patch('aitbc_chain.gossip.broker.Broadcast', return_value=mock_broadcast):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            # Should raise error when not running
            with pytest.raises(RuntimeError, match="Broadcast backend not started"):
                await backend.publish("test_topic", {"message": "test"})

    @pytest.mark.asyncio
    async def test_publish_when_running(self, mock_broadcast: AsyncMock) -> None:
        """Test publishing when backend is running."""
        with patch('aitbc_chain.gossip.broker.Broadcast', return_value=mock_broadcast):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            # Start backend
            await backend.start()
            
            # Publish message
            message = {"data": "test_message"}
            await backend.publish("test_topic", message)
            
            # Should call broadcast.publish
            mock_broadcast.publish.assert_called_once()
            
            # Clean up
            await backend.shutdown()

    @pytest.mark.asyncio
    async def test_subscribe_when_not_running(self, mock_broadcast: AsyncMock) -> None:
        """Test subscribing when backend is not started."""
        with patch('aitbc_chain.gossip.broker.Broadcast', return_value=mock_broadcast):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            # Should raise error when not running
            with pytest.raises(RuntimeError, match="Broadcast backend not started"):
                await backend.subscribe("test_topic")

    @pytest.mark.asyncio
    async def test_in_process_broadcast_fallback(self) -> None:
        """Test fallback to in-process broadcast when Broadcast is missing."""
        with patch('aitbc_chain.gossip.broker.Broadcast', None):
            backend = BroadcastGossipBackend("redis://localhost:6379")
            
            # Should use _InProcessBroadcast
            assert hasattr(backend._broadcast, 'publish')
            assert hasattr(backend._broadcast, 'subscribe')


class TestGossipMetrics:
    """Test gossip network metrics."""

    @pytest.mark.asyncio
    async def test_publication_metrics(self) -> None:
        """Test that publication metrics are recorded."""
        with patch('aitbc_chain.gossip.broker.metrics_registry') as mock_metrics:
            backend = InMemoryGossipBackend()
            await backend.subscribe("test_topic")
            
            # Publish message
            await backend.publish("test_topic", {"data": "test"})
            
            # Should increment metrics
            mock_metrics.increment.assert_called()
            
            # Check specific calls
            calls = mock_metrics.increment.call_args_list
            assert any("gossip_publications_total" in str(call) for call in calls)
            assert any("gossip_publications_topic_test_topic" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_queue_metrics(self) -> None:
        """Test that queue metrics are recorded."""
        with patch('aitbc_chain.gossip.broker.metrics_registry') as mock_metrics:
            backend = InMemoryGossipBackend()
            await backend.subscribe("test_topic")
            
            # Publish message
            await backend.publish("test_topic", {"data": "test"})
            
            # Should set gauge for queue size
            mock_metrics.set_gauge.assert_called()
            
            # Check specific calls
            calls = mock_metrics.set_gauge.call_args_list
            assert any("gossip_queue_size_test_topic" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_subscriber_metrics(self) -> None:
        """Test that subscriber metrics are recorded."""
        with patch('aitbc_chain.gossip.broker.metrics_registry') as mock_metrics:
            backend = InMemoryGossipBackend()
            
            # Add multiple subscribers
            await backend.subscribe("topic1")
            await backend.subscribe("topic1")
            await backend.subscribe("topic2")
            
            # Should update subscriber metrics
            mock_metrics.set_gauge.assert_called()
            
            # Check for subscriber count metric
            calls = mock_metrics.set_gauge.call_args_list
            assert any("gossip_subscribers_total" in str(call) for call in calls)


class TestGossipIntegration:
    """Test gossip network integration scenarios."""

    @pytest.mark.asyncio
    async def test_multi_topic_broadcast(self) -> None:
        """Test broadcasting across multiple topics."""
        backend = InMemoryGossipBackend()
        
        # Create subscribers for different topics
        block_sub = await backend.subscribe("blocks")
        tx_sub = await backend.subscribe("transactions")
        peer_sub = await backend.subscribe("peers")
        
        # Publish different message types
        block_msg = {"type": "block", "height": 100, "hash": "0xabc"}
        tx_msg = {"type": "transaction", "hash": "0xdef", "amount": 1000}
        peer_msg = {"type": "peer", "address": "node1.example.com"}
        
        await backend.publish("blocks", block_msg)
        await backend.publish("transactions", tx_msg)
        await backend.publish("peers", peer_msg)
        
        # Each subscriber should receive only their topic's message
        assert await block_sub.queue.get() == block_msg
        assert await tx_sub.queue.get() == tx_msg
        assert await peer_sub.queue.get() == peer_msg

    @pytest.mark.asyncio
    async def test_high_volume_messaging(self) -> None:
        """Test handling high volume messages."""
        backend = InMemoryGossipBackend()
        subscription = await backend.subscribe("high_volume")
        
        # Send many messages
        message_count = 100
        messages = [f"message_{i}" for i in range(message_count)]
        
        # Publish all messages
        for msg in messages:
            await backend.publish("high_volume", msg)
        
        # Receive all messages
        received = []
        for _ in range(message_count):
            msg = await subscription.queue.get()
            received.append(msg)
        
        assert len(received) == message_count
        assert set(received) == set(messages)

    @pytest.mark.asyncio
    async def test_dynamic_subscriber_management(self) -> None:
        """Test adding and removing subscribers dynamically."""
        backend = InMemoryGossipBackend()
        
        # Start with some subscribers
        sub1 = await backend.subscribe("dynamic")
        sub2 = await backend.subscribe("dynamic")
        
        # Send message
        await backend.publish("dynamic", "msg1")
        
        # Add new subscriber
        sub3 = await backend.subscribe("dynamic")
        
        # Send another message
        await backend.publish("dynamic", "msg2")
        
        # Remove first subscriber
        sub1.close()
        await asyncio.sleep(0.01)
        
        # Send final message
        await backend.publish("dynamic", "msg3")
        
        # Check message distribution
        # sub1 should only receive msg1
        assert await sub1.queue.get() == "msg1"
        assert sub1.queue.empty()
        
        # sub2 should receive all messages
        assert await sub2.queue.get() == "msg1"
        assert await sub2.queue.get() == "msg2"
        assert await sub2.queue.get() == "msg3"
        
        # sub3 should receive msg2 and msg3
        assert await sub3.queue.get() == "msg2"
        assert await sub3.queue.get() == "msg3"
        assert sub3.queue.empty()
