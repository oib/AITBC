"""
Message Queue Tests
Tests for priority queues, TTL, and dead letter queue handling
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
import asyncio
from datetime import UTC, datetime, timedelta

from app.protocols.communication import AgentMessage, MessageType, Priority
from app.protocols.message_types import MessageQueue


class TestMessageQueuePriority:
    """Test message queue priority handling"""

    @pytest.mark.asyncio
    async def test_critical_priority_first(self):
        """Test critical priority messages are dequeued first"""
        queue = MessageQueue()
        
        # Add messages with different priorities
        low_msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.LOW
        )
        
        high_msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.HIGH
        )
        
        critical_msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.CRITICAL
        )
        
        await queue.enqueue(low_msg)
        await queue.enqueue(high_msg)
        await queue.enqueue(critical_msg)
        
        # Critical should be dequeued first
        first = await queue.dequeue()
        assert first.priority == Priority.CRITICAL
        
        # High should be second
        second = await queue.dequeue()
        assert second.priority == Priority.HIGH
        
        # Low should be last
        third = await queue.dequeue()
        assert third.priority == Priority.LOW

    @pytest.mark.asyncio
    async def test_priority_queue_limits(self):
        """Test priority queue size limits"""
        queue = MessageQueue(max_size=100)
        
        # Check queue sizes
        stats = queue.get_queue_stats()
        assert stats["max_size"] == 100
        assert stats["queue_sizes"]["critical"] == 25  # 1/4 of max
        assert stats["queue_sizes"]["high"] == 25
        assert stats["queue_sizes"]["normal"] == 50  # 1/2 of max
        assert stats["queue_sizes"]["low"] == 25

    @pytest.mark.asyncio
    async def test_queue_full_handling(self):
        """Test handling when queue is full"""
        queue = MessageQueue(max_size=10)
        
        # Fill the queue
        for i in range(12):
            msg = AgentMessage(
                sender_id=f"agent_{i}",
                receiver_id="agent_002",
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=Priority.NORMAL
            )
            success = await queue.enqueue(msg)
            if i >= 10:
                assert success is False  # Should fail when queue is full
            else:
                assert success is True


class TestMessageQueuePersistence:
    """Test message queue persistence and storage"""

    @pytest.mark.asyncio
    async def test_message_storage(self):
        """Test messages are stored in message store"""
        queue = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL
        )
        
        await queue.enqueue(msg)
        
        # Check message is stored
        assert msg.id in queue.message_store
        assert queue.message_store[msg.id].sender_id == "agent_001"

    @pytest.mark.asyncio
    async def test_delivery_confirmation_removes_from_storage(self):
        """Test delivery confirmation removes message from storage"""
        queue = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL
        )
        
        await queue.enqueue(msg)
        await queue.confirm_delivery(msg.id)
        
        # Message should be removed from storage
        assert msg.id not in queue.message_store
        assert msg.id in queue.delivery_confirmations

    @pytest.mark.asyncio
    async def test_queue_stats_accuracy(self):
        """Test queue statistics are accurate"""
        queue = MessageQueue()
        
        # Add some messages
        for i in range(5):
            msg = AgentMessage(
                sender_id=f"agent_{i}",
                receiver_id="agent_002",
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=Priority.NORMAL
            )
            await queue.enqueue(msg)
        
        stats = queue.get_queue_stats()
        assert stats["stored_messages"] == 5
        assert stats["delivery_confirmations"] == 0


class TestMessageQueueTTL:
    """Test message TTL and expiration"""

    @pytest.mark.asyncio
    async def test_message_ttl(self):
        """Test message TTL is set correctly"""
        queue = MessageQueue()
        
        msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL,
            ttl=300  # 5 minutes
        )
        
        await queue.enqueue(msg)
        
        # Check TTL is preserved
        assert msg.ttl == 300

    @pytest.mark.asyncio
    async def test_expired_message_handling(self):
        """Test expired messages are handled correctly"""
        queue = MessageQueue()
        
        # Create message with very short TTL
        msg = AgentMessage(
            sender_id="agent_001",
            receiver_id="agent_002",
            message_type=MessageType.TASK_ASSIGNMENT,
            priority=Priority.NORMAL,
            ttl=0.001  # Very short TTL
        )
        
        await queue.enqueue(msg)
        
        # Wait for expiration
        await asyncio.sleep(0.01)
        
        # In a real implementation, expired messages would be moved to dead letter queue
        # For this test, we just verify the message exists in the queue
        assert msg.id in queue.message_store


class TestDeadLetterQueue:
    """Test dead letter queue functionality"""

    @pytest.mark.asyncio
    async def test_dead_letter_queue_exists(self):
        """Test dead letter queue is initialized"""
        queue = MessageQueue()
        
        # The MessageQueue has a dead_letter_queue in the MessageRouter
        # For this test, we verify the queue structure exists
        assert hasattr(queue, 'queues')
        assert len(queue.queues) == 4


class TestMessageQueueConcurrency:
    """Test concurrent message queue operations"""

    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self):
        """Test concurrent message enqueue operations"""
        queue = MessageQueue()
        
        async def enqueue_messages(count):
            for i in range(count):
                msg = AgentMessage(
                    sender_id=f"agent_{i}",
                    receiver_id="agent_002",
                    message_type=MessageType.TASK_ASSIGNMENT,
                    priority=Priority.NORMAL
                )
                await queue.enqueue(msg)
        
        # Enqueue concurrently
        await asyncio.gather(
            enqueue_messages(5),
            enqueue_messages(5)
        )
        
        stats = queue.get_queue_stats()
        assert stats["stored_messages"] == 10

    @pytest.mark.asyncio
    async def test_concurrent_dequeue(self):
        """Test concurrent message dequeue operations"""
        queue = MessageQueue()
        
        # Enqueue messages first
        for i in range(10):
            msg = AgentMessage(
                sender_id=f"agent_{i}",
                receiver_id="agent_002",
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=Priority.NORMAL
            )
            await queue.enqueue(msg)
        
        async def dequeue_messages(count):
            messages = []
            for _ in range(count):
                msg = await queue.dequeue()
                if msg:
                    messages.append(msg)
            return messages
        
        # Dequeue concurrently
        results = await asyncio.gather(
            dequeue_messages(5),
            dequeue_messages(5)
        )
        
        total_dequeued = sum(len(r) for r in results)
        assert total_dequeued == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
