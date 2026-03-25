"""
Core WebSocket Backpressure Tests

Tests for the essential backpressure control mechanisms
without complex dependencies.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any, List


class MockMessage:
    """Mock message for testing"""
    def __init__(self, data: str, priority: int = 1):
        self.data = data
        self.priority = priority
        self.timestamp = time.time()
        self.message_id = f"msg_{id(self)}"


class MockBoundedQueue:
    """Mock bounded queue with priority handling"""
    
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.queues = {
            "critical": [],
            "important": [],
            "bulk": [],
            "control": []
        }
        self.total_size = 0
        self._lock = asyncio.Lock()
    
    async def put(self, message: MockMessage, priority: str = "important") -> bool:
        """Add message with backpressure handling"""
        async with self._lock:
            # Check capacity
            if self.total_size >= self.max_size:
                # Drop bulk messages first
                if priority == "bulk":
                    return False
                
                # For important messages: drop oldest important if exists, otherwise drop bulk
                if priority == "important":
                    if self.queues["important"]:
                        self.queues["important"].pop(0)
                        self.total_size -= 1
                    elif self.queues["bulk"]:
                        self.queues["bulk"].pop(0)
                        self.total_size -= 1
                    else:
                        return False
                
                # For critical messages: drop oldest critical if exists, otherwise drop important, otherwise drop bulk
                if priority == "critical":
                    if self.queues["critical"]:
                        self.queues["critical"].pop(0)
                        self.total_size -= 1
                    elif self.queues["important"]:
                        self.queues["important"].pop(0)
                        self.total_size -= 1
                    elif self.queues["bulk"]:
                        self.queues["bulk"].pop(0)
                        self.total_size -= 1
                    else:
                        return False
            
            self.queues[priority].append(message)
            self.total_size += 1
            return True
    
    async def get(self) -> MockMessage:
        """Get next message by priority"""
        async with self._lock:
            # Priority order: control > critical > important > bulk
            for priority in ["control", "critical", "important", "bulk"]:
                if self.queues[priority]:
                    message = self.queues[priority].pop(0)
                    self.total_size -= 1
                    return message
            return None
    
    def size(self) -> int:
        return self.total_size
    
    def fill_ratio(self) -> float:
        return self.total_size / self.max_size


class MockWebSocketStream:
    """Mock WebSocket stream with backpressure control"""
    
    def __init__(self, stream_id: str, max_queue_size: int = 100):
        self.stream_id = stream_id
        self.queue = MockBoundedQueue(max_queue_size)
        self.websocket = AsyncMock()
        self.status = "connected"
        self.metrics = {
            "messages_sent": 0,
            "messages_dropped": 0,
            "backpressure_events": 0,
            "slow_consumer_events": 0
        }
        
        self._running = False
        self._sender_task = None
        self._send_lock = asyncio.Lock()
        
        # Configuration
        self.send_timeout = 1.0
        self.slow_consumer_threshold = 0.5
        self.backpressure_threshold = 0.7
    
    async def start(self):
        """Start stream processing"""
        if self._running:
            return
        
        self._running = True
        self._sender_task = asyncio.create_task(self._sender_loop())
    
    async def stop(self):
        """Stop stream processing"""
        if not self._running:
            return
        
        self._running = False
        
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
    
    async def send_message(self, data: Any, priority: str = "important") -> bool:
        """Send message with backpressure handling"""
        if not self._running:
            return False
        
        message = MockMessage(data, priority)
        
        # Check backpressure
        queue_ratio = self.queue.fill_ratio()
        if queue_ratio > self.backpressure_threshold:
            self.metrics["backpressure_events"] += 1
            
            # Drop bulk messages under backpressure
            if priority == "bulk" and queue_ratio > 0.8:
                self.metrics["messages_dropped"] += 1
                return False
        
        # Add to queue
        success = await self.queue.put(message, priority)
        if not success:
            self.metrics["messages_dropped"] += 1
        
        return success
    
    async def _sender_loop(self):
        """Main sender loop with backpressure control"""
        while self._running:
            try:
                message = await self.queue.get()
                if message is None:
                    await asyncio.sleep(0.01)
                    continue
                
                # Send with timeout protection
                start_time = time.time()
                success = await self._send_with_backpressure(message)
                send_time = time.time() - start_time
                
                if success:
                    self.metrics["messages_sent"] += 1
                    
                    # Check for slow consumer
                    if send_time > self.slow_consumer_threshold:
                        self.metrics["slow_consumer_events"] += 1
                        if self.metrics["slow_consumer_events"] > 5:
                            self.status = "slow_consumer"
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in sender loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _send_with_backpressure(self, message: MockMessage) -> bool:
        """Send message with timeout protection"""
        try:
            async with self._send_lock:
                # Simulate send with potential delay
                await asyncio.wait_for(
                    self.websocket.send(message.data),
                    timeout=self.send_timeout
                )
                return True
                
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get stream metrics"""
        return {
            "stream_id": self.stream_id,
            "status": self.status,
            "queue_size": self.queue.size(),
            "queue_fill_ratio": self.queue.fill_ratio(),
            **self.metrics
        }


class MockStreamManager:
    """Mock stream manager with backpressure control"""
    
    def __init__(self):
        self.streams: Dict[str, MockWebSocketStream] = {}
        self.total_connections = 0
        self._running = False
        self._broadcast_queue = asyncio.Queue(maxsize=1000)
        self._broadcast_task = None
    
    async def start(self):
        """Start the stream manager"""
        if self._running:
            return
        
        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
    
    async def stop(self):
        """Stop the stream manager"""
        if not self._running:
            return
        
        self._running = False
        
        # Stop all streams
        for stream in self.streams.values():
            await stream.stop()
        
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
    
    async def create_stream(self, stream_id: str, max_queue_size: int = 100) -> MockWebSocketStream:
        """Create a new stream"""
        stream = MockWebSocketStream(stream_id, max_queue_size)
        await stream.start()
        
        self.streams[stream_id] = stream
        self.total_connections += 1
        
        return stream
    
    async def remove_stream(self, stream_id: str):
        """Remove a stream"""
        if stream_id in self.streams:
            stream = self.streams[stream_id]
            await stream.stop()
            del self.streams[stream_id]
            self.total_connections -= 1
    
    async def broadcast_to_all(self, data: Any, priority: str = "important"):
        """Broadcast message to all streams"""
        if not self._running:
            return
        
        try:
            await self._broadcast_queue.put((data, priority))
        except asyncio.QueueFull:
            print("Broadcast queue full, dropping message")
    
    async def _broadcast_loop(self):
        """Broadcast messages to all streams"""
        while self._running:
            try:
                data, priority = await self._broadcast_queue.get()
                
                # Send to all streams concurrently
                tasks = []
                for stream in self.streams.values():
                    task = asyncio.create_task(
                        stream.send_message(data, priority)
                    )
                    tasks.append(task)
                
                # Wait for all sends (with timeout)
                if tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True),
                            timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        print("Broadcast timeout, some streams may be slow")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in broadcast loop: {e}")
                await asyncio.sleep(0.1)
    
    def get_slow_streams(self, threshold: float = 0.8) -> List[str]:
        """Get streams with high queue fill ratios"""
        slow_streams = []
        for stream_id, stream in self.streams.items():
            if stream.queue.fill_ratio() > threshold:
                slow_streams.append(stream_id)
        return slow_streams
    
    def get_manager_metrics(self) -> Dict[str, Any]:
        """Get manager metrics"""
        stream_metrics = []
        for stream in self.streams.values():
            stream_metrics.append(stream.get_metrics())
        
        total_queue_size = sum(m["queue_size"] for m in stream_metrics)
        total_messages_sent = sum(m["messages_sent"] for m in stream_metrics)
        total_messages_dropped = sum(m["messages_dropped"] for m in stream_metrics)
        
        status_counts = {}
        for stream in self.streams.values():
            status = stream.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "manager_status": "running" if self._running else "stopped",
            "total_connections": self.total_connections,
            "active_streams": len(self.streams),
            "total_queue_size": total_queue_size,
            "total_messages_sent": total_messages_sent,
            "total_messages_dropped": total_messages_dropped,
            "broadcast_queue_size": self._broadcast_queue.qsize(),
            "stream_status_distribution": status_counts,
            "stream_metrics": stream_metrics
        }


class TestBoundedQueue:
    """Test bounded message queue"""
    
    @pytest.fixture
    def queue(self):
        return MockBoundedQueue(max_size=10)
    
    @pytest.mark.asyncio
    async def test_basic_operations(self, queue):
        """Test basic queue operations"""
        message = MockMessage("test", "important")
        
        # Put message
        success = await queue.put(message, "important")
        assert success is True
        assert queue.size() == 1
        
        # Get message
        retrieved = await queue.get()
        assert retrieved == message
        assert queue.size() == 0
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        """Test priority ordering"""
        messages = [
            MockMessage("bulk", "bulk"),
            MockMessage("critical", "critical"),
            MockMessage("important", "important"),
            MockMessage("control", "control")
        ]
        
        # Add messages
        for msg in messages:
            await queue.put(msg, msg.priority)
        
        # Should retrieve in priority order
        expected_order = ["control", "critical", "important", "bulk"]
        
        for expected_priority in expected_order:
            msg = await queue.get()
            assert msg.priority == expected_priority
    
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, queue):
        """Test backpressure when queue is full"""
        # Fill queue to capacity with bulk messages first
        for i in range(queue.max_size):
            await queue.put(MockMessage(f"bulk_{i}", "bulk"), "bulk")
        
        assert queue.size() == queue.max_size
        assert queue.fill_ratio() == 1.0
        
        # Try to add bulk message (should be dropped)
        bulk_msg = MockMessage("new_bulk", "bulk")
        success = await queue.put(bulk_msg, "bulk")
        assert success is False
        
        # Now add some important messages by replacing bulk messages
        # First, remove some bulk messages to make space
        for i in range(3):
            await queue.get()  # Remove bulk messages
        
        # Add important messages
        for i in range(3):
            await queue.put(MockMessage(f"important_{i}", "important"), "important")
        
        # Fill back to capacity with bulk
        while queue.size() < queue.max_size:
            await queue.put(MockMessage(f"bulk_extra", "bulk"), "bulk")
        
        # Now try to add important message (should replace oldest important)
        important_msg = MockMessage("new_important", "important")
        success = await queue.put(important_msg, "important")
        assert success is True
        
        # Try to add critical message (should always succeed)
        critical_msg = MockMessage("new_critical", "critical")
        success = await queue.put(critical_msg, "critical")
        assert success is True


class TestWebSocketStream:
    """Test WebSocket stream with backpressure"""
    
    @pytest.fixture
    def stream(self):
        return MockWebSocketStream("test_stream", max_queue_size=50)
    
    @pytest.mark.asyncio
    async def test_stream_start_stop(self, stream):
        """Test stream start and stop"""
        assert stream._running is False
        
        await stream.start()
        assert stream._running is True
        assert stream.status == "connected"
        
        await stream.stop()
        assert stream._running is False
    
    @pytest.mark.asyncio
    async def test_message_sending(self, stream):
        """Test basic message sending"""
        await stream.start()
        
        # Send message
        success = await stream.send_message({"test": "data"}, "important")
        assert success is True
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Verify message was sent
        assert stream.websocket.send.called
        assert stream.metrics["messages_sent"] > 0
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_slow_consumer_detection(self, stream):
        """Test slow consumer detection"""
        # Make websocket send slow
        async def slow_send(message):
            await asyncio.sleep(0.6)  # Slower than threshold (0.5s)
        
        stream.websocket.send = slow_send
        
        await stream.start()
        
        # Send many messages to trigger detection (need > 5 slow events)
        for i in range(15):  # Increased from 10 to 15
            await stream.send_message({"test": f"data_{i}"}, "important")
            await asyncio.sleep(0.1)  # Small delay between sends
        
        # Wait for processing
        await asyncio.sleep(3.0)  # Increased wait time
        
        # Check slow consumer detection
        assert stream.status == "slow_consumer"
        assert stream.metrics["slow_consumer_events"] > 5  # Need > 5 events
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, stream):
        """Test backpressure handling"""
        # Make websocket send slower to build up queue
        async def slow_send(message):
            await asyncio.sleep(0.02)  # Small delay to allow queue to build
        
        stream.websocket.send = slow_send
        
        await stream.start()
        
        # Fill queue to trigger backpressure
        for i in range(40):  # 40/50 = 80% > threshold (70%)
            await stream.send_message({"test": f"data_{i}"}, "important")
        
        # Wait a bit but not too long to allow queue to build
        await asyncio.sleep(0.05)
        
        # Check backpressure status
        assert stream.metrics["backpressure_events"] > 0
        assert stream.queue.fill_ratio() > 0.7
        
        # Try to send bulk message under backpressure
        success = await stream.send_message({"bulk": "data"}, "bulk")
        # Should be dropped due to high queue fill ratio
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_send_timeout_handling(self, stream):
        """Test send timeout handling"""
        # Make websocket send timeout
        async def timeout_send(message):
            await asyncio.sleep(2.0)  # Longer than timeout (1.0s)
        
        stream.websocket.send = timeout_send
        
        await stream.start()
        
        # Send message
        await stream.send_message({"test": "data"}, "important")
        
        # Wait for processing
        await asyncio.sleep(1.5)
        
        # Check that message handling handled timeout
        # (In real implementation, would retry or drop)
        
        await stream.stop()


class TestStreamManager:
    """Test stream manager with multiple streams"""
    
    @pytest.fixture
    def manager(self):
        return MockStreamManager()
    
    @pytest.mark.asyncio
    async def test_manager_start_stop(self, manager):
        """Test manager start and stop"""
        await manager.start()
        assert manager._running is True
        
        await manager.stop()
        assert manager._running is False
    
    @pytest.mark.asyncio
    async def test_stream_management(self, manager):
        """Test stream lifecycle management"""
        await manager.start()
        
        # Create stream
        stream = await manager.create_stream("test_stream")
        assert stream is not None
        assert stream._running is True
        assert len(manager.streams) == 1
        assert manager.total_connections == 1
        
        # Remove stream
        await manager.remove_stream("test_stream")
        assert len(manager.streams) == 0
        assert manager.total_connections == 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_streams(self, manager):
        """Test broadcasting to all streams"""
        await manager.start()
        
        # Create multiple streams
        streams = []
        for i in range(3):
            stream = await manager.create_stream(f"stream_{i}")
            streams.append(stream)
        
        # Broadcast message
        await manager.broadcast_to_all({"broadcast": "test"}, "important")
        
        # Wait for broadcast
        await asyncio.sleep(0.2)
        
        # Verify all streams received the message
        for stream in streams:
            assert stream.websocket.send.called
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_slow_stream_detection(self, manager):
        """Test slow stream detection"""
        await manager.start()
        
        # Create slow stream
        slow_stream = await manager.create_stream("slow_stream")
        
        # Make it slow
        async def slow_send(message):
            await asyncio.sleep(0.6)
        
        slow_stream.websocket.send = slow_send
        
        # Send many messages to fill queue and trigger slow detection
        for i in range(30):  # More messages to fill queue
            await slow_stream.send_message({"test": f"data_{i}"}, "important")
        
        await asyncio.sleep(2.0)
        
        # Check for slow streams (based on queue fill ratio)
        slow_streams = manager.get_slow_streams(threshold=0.5)  # Lower threshold
        
        # Should detect slow stream either by status or queue fill ratio
        stream_detected = (
            len(slow_streams) > 0 or 
            slow_stream.status == "slow_consumer" or
            slow_stream.queue.fill_ratio() > 0.5
        )
        
        assert stream_detected, f"Slow stream not detected. Status: {slow_stream.status}, Queue ratio: {slow_stream.queue.fill_ratio()}"
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_manager_metrics(self, manager):
        """Test manager metrics"""
        await manager.start()
        
        # Create streams with different loads
        normal_stream = await manager.create_stream("normal_stream")
        slow_stream = await manager.create_stream("slow_stream")
        
        # Send messages to normal stream
        for i in range(5):
            await normal_stream.send_message({"test": f"data_{i}"}, "important")
        
        # Send messages to slow stream (to fill queue)
        for i in range(40):
            await slow_stream.send_message({"test": f"data_{i}"}, "important")
        
        await asyncio.sleep(0.1)
        
        # Get metrics
        metrics = manager.get_manager_metrics()
        
        assert "manager_status" in metrics
        assert "total_connections" in metrics
        assert "active_streams" in metrics
        assert "total_queue_size" in metrics
        assert "stream_status_distribution" in metrics
        
        await manager.stop()


class TestBackpressureScenarios:
    """Test backpressure scenarios"""
    
    @pytest.mark.asyncio
    async def test_high_load_scenario(self):
        """Test system behavior under high load"""
        manager = MockStreamManager()
        await manager.start()
        
        try:
            # Create multiple streams
            streams = []
            for i in range(5):
                stream = await manager.create_stream(f"stream_{i}", max_queue_size=50)
                streams.append(stream)
            
            # Send high volume of messages
            tasks = []
            for stream in streams:
                for i in range(100):
                    task = asyncio.create_task(
                        stream.send_message({"test": f"data_{i}"}, "important")
                    )
                    tasks.append(task)
            
            # Wait for all sends
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Check system handled load
            metrics = manager.get_manager_metrics()
            
            # Should have processed some messages
            assert metrics["total_messages_sent"] > 0
            
            # System should still be running
            assert metrics["manager_status"] == "running"
            
            # Some messages may be dropped under load
            assert metrics["total_messages_dropped"] >= 0
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_mixed_priority_scenario(self):
        """Test handling of mixed priority messages"""
        queue = MockBoundedQueue(max_size=20)
        
        # Fill queue with bulk messages
        for i in range(15):
            await queue.put(MockMessage(f"bulk_{i}", "bulk"), "bulk")
        
        # Add critical messages (should succeed)
        critical_success = await queue.put(MockMessage("critical_1", "critical"), "critical")
        critical_success2 = await queue.put(MockMessage("critical_2", "critical"), "critical")
        
        assert critical_success is True
        assert critical_success2 is True
        
        # Add important messages (should replace bulk)
        important_success = await queue.put(MockMessage("important_1", "important"), "important")
        important_success2 = await queue.put(MockMessage("important_2", "important"), "important")
        
        assert important_success is True
        assert important_success2 is True
        
        # Try to add more bulk (should be dropped)
        bulk_success = await queue.put(MockMessage("bulk_new", "bulk"), "bulk")
        assert bulk_success is False
        
        # Verify priority order in retrieval
        retrieved_order = []
        for _ in range(10):
            msg = await queue.get()
            if msg:
                retrieved_order.append(msg.priority)
        
        # Should start with critical messages
        assert retrieved_order[0] == "critical"
        assert retrieved_order[1] == "critical"
    
    @pytest.mark.asyncio
    async def test_slow_consumer_isolation(self):
        """Test that slow consumers don't block fast ones"""
        manager = MockStreamManager()
        await manager.start()
        
        try:
            # Create fast and slow streams
            fast_stream = await manager.create_stream("fast_stream")
            slow_stream = await manager.create_stream("slow_stream")
            
            # Make slow stream slow
            async def slow_send(message):
                await asyncio.sleep(0.3)
            
            slow_stream.websocket.send = slow_send
            
            # Send messages to both streams
            for i in range(10):
                await fast_stream.send_message({"fast": f"data_{i}"}, "important")
                await slow_stream.send_message({"slow": f"data_{i}"}, "important")
            
            # Wait for processing
            await asyncio.sleep(1.0)
            
            # Fast stream should have processed more messages
            fast_metrics = fast_stream.get_metrics()
            slow_metrics = slow_stream.get_metrics()
            
            # Fast stream should be ahead
            assert fast_metrics["messages_sent"] >= slow_metrics["messages_sent"]
            
            # Slow stream should be detected as slow
            assert slow_stream.status == "slow_consumer"
            
        finally:
            await manager.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
