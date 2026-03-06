"""
Tests for WebSocket Stream Backpressure Control

Comprehensive test suite for WebSocket stream architecture with
per-stream flow control and backpressure handling.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'apps', 'coordinator-api', 'src'))

from app.services.websocket_stream_manager import (
    WebSocketStreamManager, StreamConfig, StreamMessage, MessageType,
    BoundedMessageQueue, WebSocketStream, StreamStatus
)
from app.services.multi_modal_websocket_fusion import (
    MultiModalWebSocketFusion, FusionStreamType, FusionStreamConfig,
    GPUProviderFlowControl, GPUProviderStatus, FusionData
)


class TestBoundedMessageQueue:
    """Test bounded message queue with priority and backpressure"""
    
    @pytest.fixture
    def queue(self):
        return BoundedMessageQueue(max_size=10)
    
    @pytest.mark.asyncio
    async def test_basic_queue_operations(self, queue):
        """Test basic queue put/get operations"""
        message = StreamMessage(data="test", message_type=MessageType.IMPORTANT)
        
        # Put message
        success = await queue.put(message)
        assert success is True
        assert queue.size() == 1
        
        # Get message
        retrieved = await queue.get()
        assert retrieved == message
        assert queue.size() == 0
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        """Test message priority ordering"""
        messages = [
            StreamMessage(data="bulk", message_type=MessageType.BULK),
            StreamMessage(data="critical", message_type=MessageType.CRITICAL),
            StreamMessage(data="important", message_type=MessageType.IMPORTANT),
            StreamMessage(data="control", message_type=MessageType.CONTROL)
        ]
        
        # Add messages in random order
        for msg in messages:
            await queue.put(msg)
        
        # Should retrieve in priority order: CONTROL > CRITICAL > IMPORTANT > BULK
        expected_order = [MessageType.CONTROL, MessageType.CRITICAL, 
                          MessageType.IMPORTANT, MessageType.BULK]
        
        for expected_type in expected_order:
            msg = await queue.get()
            assert msg.message_type == expected_type
    
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, queue):
        """Test backpressure handling when queue is full"""
        # Fill queue to capacity
        for i in range(queue.max_size):
            await queue.put(StreamMessage(data=f"bulk_{i}", message_type=MessageType.BULK))
        
        assert queue.size() == queue.max_size
        assert queue.fill_ratio() == 1.0
        
        # Try to add bulk message (should be dropped)
        bulk_msg = StreamMessage(data="new_bulk", message_type=MessageType.BULK)
        success = await queue.put(bulk_msg)
        assert success is False
        
        # Try to add important message (should replace oldest important)
        important_msg = StreamMessage(data="new_important", message_type=MessageType.IMPORTANT)
        success = await queue.put(important_msg)
        assert success is True
        
        # Try to add critical message (should always succeed)
        critical_msg = StreamMessage(data="new_critical", message_type=MessageType.CRITICAL)
        success = await queue.put(critical_msg)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_queue_size_limits(self, queue):
        """Test that individual queue size limits are respected"""
        # Fill control queue to its limit
        for i in range(100):  # Control queue limit is 100
            await queue.put(StreamMessage(data=f"control_{i}", message_type=MessageType.CONTROL))
        
        # Should still accept other message types
        success = await queue.put(StreamMessage(data="important", message_type=MessageType.IMPORTANT))
        assert success is True


class TestWebSocketStream:
    """Test individual WebSocket stream with backpressure control"""
    
    @pytest.fixture
    def mock_websocket(self):
        websocket = Mock()
        websocket.send = AsyncMock()
        websocket.remote_address = "127.0.0.1:12345"
        return websocket
    
    @pytest.fixture
    def stream_config(self):
        return StreamConfig(
            max_queue_size=50,
            send_timeout=1.0,
            slow_consumer_threshold=0.1,
            backpressure_threshold=0.7
        )
    
    @pytest.fixture
    def stream(self, mock_websocket, stream_config):
        return WebSocketStream(mock_websocket, "test_stream", stream_config)
    
    @pytest.mark.asyncio
    async def test_stream_start_stop(self, stream):
        """Test stream start and stop"""
        assert stream.status == StreamStatus.CONNECTING
        
        await stream.start()
        assert stream.status == StreamStatus.CONNECTED
        assert stream._running is True
        
        await stream.stop()
        assert stream.status == StreamStatus.DISCONNECTED
        assert stream._running is False
    
    @pytest.mark.asyncio
    async def test_message_sending(self, stream, mock_websocket):
        """Test basic message sending"""
        await stream.start()
        
        # Send message
        success = await stream.send_message({"test": "data"}, MessageType.IMPORTANT)
        assert success is True
        
        # Wait for message to be processed
        await asyncio.sleep(0.1)
        
        # Verify message was sent
        mock_websocket.send.assert_called()
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_slow_consumer_detection(self, stream, mock_websocket):
        """Test slow consumer detection"""
        # Make websocket send slow
        async def slow_send(message):
            await asyncio.sleep(0.2)  # Slower than threshold (0.1s)
        
        mock_websocket.send = slow_send
        
        await stream.start()
        
        # Send multiple messages to trigger slow consumer detection
        for i in range(10):
            await stream.send_message({"test": f"data_{i}"}, MessageType.IMPORTANT)
        
        # Wait for processing
        await asyncio.sleep(1.0)
        
        # Check if slow consumer was detected
        assert stream.status == StreamStatus.SLOW_CONSUMER
        assert stream.metrics.slow_consumer_events > 0
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, stream, mock_websocket):
        """Test backpressure handling"""
        await stream.start()
        
        # Fill queue to trigger backpressure
        for i in range(40):  # 40/50 = 80% > backpressure_threshold (70%)
            await stream.send_message({"test": f"data_{i}"}, MessageType.IMPORTANT)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Check backpressure status
        assert stream.status == StreamStatus.BACKPRESSURE
        assert stream.metrics.backpressure_events > 0
        
        # Try to send bulk message under backpressure
        success = await stream.send_message({"bulk": "data"}, MessageType.BULK)
        # Should be dropped due to high queue fill ratio
        assert stream.queue.fill_ratio() > 0.8
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_message_priority_handling(self, stream, mock_websocket):
        """Test that priority messages are handled correctly"""
        await stream.start()
        
        # Send messages of different priorities
        await stream.send_message({"bulk": "data"}, MessageType.BULK)
        await stream.send_message({"critical": "data"}, MessageType.CRITICAL)
        await stream.send_message({"important": "data"}, MessageType.IMPORTANT)
        await stream.send_message({"control": "data"}, MessageType.CONTROL)
        
        # Wait for processing
        await asyncio.sleep(0.2)
        
        # Verify all messages were sent
        assert mock_websocket.send.call_count >= 4
        
        await stream.stop()
    
    @pytest.mark.asyncio
    async def test_send_timeout_handling(self, stream, mock_websocket):
        """Test send timeout handling"""
        # Make websocket send timeout
        async def timeout_send(message):
            await asyncio.sleep(2.0)  # Longer than send_timeout (1.0s)
        
        mock_websocket.send = timeout_send
        
        await stream.start()
        
        # Send message
        success = await stream.send_message({"test": "data"}, MessageType.IMPORTANT)
        assert success is True
        
        # Wait for processing
        await asyncio.sleep(1.5)
        
        # Check that message was dropped due to timeout
        assert stream.metrics.messages_dropped > 0
        
        await stream.stop()
    
    def test_stream_metrics(self, stream):
        """Test stream metrics collection"""
        metrics = stream.get_metrics()
        
        assert "stream_id" in metrics
        assert "status" in metrics
        assert "queue_size" in metrics
        assert "messages_sent" in metrics
        assert "messages_dropped" in metrics
        assert "backpressure_events" in metrics
        assert "slow_consumer_events" in metrics


class TestWebSocketStreamManager:
    """Test WebSocket stream manager with multiple streams"""
    
    @pytest.fixture
    def manager(self):
        return WebSocketStreamManager()
    
    @pytest.fixture
    def mock_websocket(self):
        websocket = Mock()
        websocket.send = AsyncMock()
        websocket.remote_address = "127.0.0.1:12345"
        return websocket
    
    @pytest.mark.asyncio
    async def test_manager_start_stop(self, manager):
        """Test manager start and stop"""
        await manager.start()
        assert manager._running is True
        
        await manager.stop()
        assert manager._running is False
    
    @pytest.mark.asyncio
    async def test_stream_lifecycle_management(self, manager, mock_websocket):
        """Test stream lifecycle management"""
        await manager.start()
        
        # Create stream through manager
        stream = None
        async with manager.manage_stream(mock_websocket) as s:
            stream = s
            assert stream is not None
            assert stream._running is True
            assert len(manager.streams) == 1
            assert manager.total_connections == 1
        
        # Stream should be cleaned up
        assert len(manager.streams) == 0
        assert manager.total_connections == 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_streams(self, manager):
        """Test broadcasting to all streams"""
        await manager.start()
        
        # Create multiple mock websockets
        websockets = [Mock() for _ in range(3)]
        for ws in websockets:
            ws.send = AsyncMock()
            ws.remote_address = f"127.0.0.1:{12345 + websockets.index(ws)}"
        
        # Create streams
        streams = []
        for ws in websockets:
            async with manager.manage_stream(ws) as stream:
                streams.append(stream)
                await asyncio.sleep(0.01)  # Small delay
        
        # Broadcast message
        await manager.broadcast_to_all({"broadcast": "test"}, MessageType.IMPORTANT)
        
        # Wait for broadcast
        await asyncio.sleep(0.2)
        
        # Verify all streams received the message
        for ws in websockets:
            ws.send.assert_called()
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_slow_stream_handling(self, manager):
        """Test handling of slow streams"""
        await manager.start()
        
        # Create slow websocket
        slow_websocket = Mock()
        async def slow_send(message):
            await asyncio.sleep(0.5)  # Very slow
        
        slow_websocket.send = slow_send
        slow_websocket.remote_address = "127.0.0.1:12345"
        
        # Create slow stream
        async with manager.manage_stream(slow_websocket) as stream:
            # Send messages to fill queue
            for i in range(20):
                await stream.send_message({"test": f"data_{i}"}, MessageType.IMPORTANT)
            
            await asyncio.sleep(0.5)
            
            # Check if stream is detected as slow
            slow_streams = manager.get_slow_streams(threshold=0.5)
            assert len(slow_streams) > 0
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_manager_metrics(self, manager):
        """Test manager metrics collection"""
        await manager.start()
        
        # Create some streams
        websockets = [Mock() for _ in range(2)]
        for ws in websockets:
            ws.send = AsyncMock()
            ws.remote_address = f"127.0.0.1:{12345 + websockets.index(ws)}"
        
        streams = []
        for ws in websockets:
            async with manager.manage_stream(ws) as stream:
                streams.append(stream)
                await stream.send_message({"test": "data"}, MessageType.IMPORTANT)
                await asyncio.sleep(0.01)
        
        # Get metrics
        metrics = await manager.get_manager_metrics()
        
        assert "manager_status" in metrics
        assert "total_connections" in metrics
        assert "active_streams" in metrics
        assert "total_queue_size" in metrics
        assert "stream_status_distribution" in metrics
        assert "stream_metrics" in metrics
        
        await manager.stop()


class TestGPUProviderFlowControl:
    """Test GPU provider flow control"""
    
    @pytest.fixture
    def provider(self):
        return GPUProviderFlowControl("test_provider")
    
    @pytest.mark.asyncio
    async def test_provider_start_stop(self, provider):
        """Test provider start and stop"""
        await provider.start()
        assert provider._running is True
        
        await provider.stop()
        assert provider._running is False
    
    @pytest.mark.asyncio
    async def test_request_submission(self, provider):
        """Test request submission and processing"""
        await provider.start()
        
        # Create fusion data
        fusion_data = FusionData(
            stream_id="test_stream",
            stream_type=FusionStreamType.VISUAL,
            data={"test": "data"},
            timestamp=time.time(),
            requires_gpu=True
        )
        
        # Submit request
        request_id = await provider.submit_request(fusion_data)
        assert request_id is not None
        
        # Get result
        result = await provider.get_result(request_id, timeout=3.0)
        assert result is not None
        assert "processed_data" in result
        
        await provider.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_request_limiting(self, provider):
        """Test concurrent request limiting"""
        provider.max_concurrent_requests = 2
        await provider.start()
        
        # Submit multiple requests
        fusion_data = FusionData(
            stream_id="test_stream",
            stream_type=FusionStreamType.VISUAL,
            data={"test": "data"},
            timestamp=time.time(),
            requires_gpu=True
        )
        
        request_ids = []
        for i in range(5):
            request_id = await provider.submit_request(fusion_data)
            if request_id:
                request_ids.append(request_id)
        
        # Should have processed some requests
        assert len(request_ids) > 0
        
        # Get results
        results = []
        for request_id in request_ids:
            result = await provider.get_result(request_id, timeout=5.0)
            if result:
                results.append(result)
        
        assert len(results) > 0
        
        await provider.stop()
    
    @pytest.mark.asyncio
    async def test_overload_handling(self, provider):
        """Test provider overload handling"""
        await provider.start()
        
        # Fill input queue to capacity
        fusion_data = FusionData(
            stream_id="test_stream",
            stream_type=FusionStreamType.VISUAL,
            data={"test": "data"},
            timestamp=time.time(),
            requires_gpu=True
        )
        
        # Submit many requests to fill queue
        request_ids = []
        for i in range(150):  # More than queue capacity (100)
            request_id = await provider.submit_request(fusion_data)
            if request_id:
                request_ids.append(request_id)
            else:
                break  # Queue is full
        
        # Should have rejected some requests due to overload
        assert len(request_ids) < 150
        
        # Check provider status
        metrics = provider.get_metrics()
        assert metrics["queue_size"] >= provider.input_queue.maxsize * 0.8
        
        await provider.stop()
    
    @pytest.mark.asyncio
    async def test_provider_metrics(self, provider):
        """Test provider metrics collection"""
        await provider.start()
        
        # Submit some requests
        fusion_data = FusionData(
            stream_id="test_stream",
            stream_type=FusionStreamType.VISUAL,
            data={"test": "data"},
            timestamp=time.time(),
            requires_gpu=True
        )
        
        for i in range(3):
            request_id = await provider.submit_request(fusion_data)
            if request_id:
                await provider.get_result(request_id, timeout=3.0)
        
        # Get metrics
        metrics = provider.get_metrics()
        
        assert "provider_id" in metrics
        assert "status" in metrics
        assert "avg_processing_time" in metrics
        assert "queue_size" in metrics
        assert "total_requests" in metrics
        assert "error_rate" in metrics
        
        await provider.stop()


class TestMultiModalWebSocketFusion:
    """Test multi-modal WebSocket fusion service"""
    
    @pytest.fixture
    def fusion_service(self):
        return MultiModalWebSocketFusion()
    
    @pytest.mark.asyncio
    async def test_fusion_service_start_stop(self, fusion_service):
        """Test fusion service start and stop"""
        await fusion_service.start()
        assert fusion_service._running is True
        
        await fusion_service.stop()
        assert fusion_service._running is False
    
    @pytest.mark.asyncio
    async def test_fusion_stream_registration(self, fusion_service):
        """Test fusion stream registration"""
        await fusion_service.start()
        
        config = FusionStreamConfig(
            stream_type=FusionStreamType.VISUAL,
            max_queue_size=100,
            gpu_timeout=2.0
        )
        
        await fusion_service.register_fusion_stream("test_stream", config)
        
        assert "test_stream" in fusion_service.fusion_streams
        assert fusion_service.fusion_streams["test_stream"].stream_type == FusionStreamType.VISUAL
        
        await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_gpu_provider_initialization(self, fusion_service):
        """Test GPU provider initialization"""
        await fusion_service.start()
        
        assert len(fusion_service.gpu_providers) > 0
        
        # Check that providers are running
        for provider in fusion_service.gpu_providers.values():
            assert provider._running is True
        
        await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_fusion_data_processing(self, fusion_service):
        """Test fusion data processing"""
        await fusion_service.start()
        
        # Create fusion data
        fusion_data = FusionData(
            stream_id="test_stream",
            stream_type=FusionStreamType.VISUAL,
            data={"test": "data"},
            timestamp=time.time(),
            requires_gpu=True
        )
        
        # Process data
        await fusion_service._submit_to_gpu_provider(fusion_data)
        
        # Wait for processing
        await asyncio.sleep(1.0)
        
        # Check metrics
        assert fusion_service.fusion_metrics["total_fusions"] >= 1
        
        await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_comprehensive_metrics(self, fusion_service):
        """Test comprehensive metrics collection"""
        await fusion_service.start()
        
        # Get metrics
        metrics = fusion_service.get_comprehensive_metrics()
        
        assert "timestamp" in metrics
        assert "system_status" in metrics
        assert "stream_metrics" in metrics
        assert "gpu_metrics" in metrics
        assert "fusion_metrics" in metrics
        assert "active_fusion_streams" in metrics
        assert "registered_gpu_providers" in metrics
        
        await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_backpressure_monitoring(self, fusion_service):
        """Test backpressure monitoring"""
        await fusion_service.start()
        
        # Enable backpressure
        fusion_service.backpressure_enabled = True
        
        # Simulate high load
        fusion_service.global_queue_size = 8000  # High queue size
        fusion_service.max_global_queue_size = 10000
        
        # Run monitoring check
        await fusion_service._check_backpressure()
        
        # Should have handled backpressure
        # (This is a simplified test - in reality would check slow streams)
        
        await fusion_service.stop()


class TestIntegrationScenarios:
    """Integration tests for complete scenarios"""
    
    @pytest.mark.asyncio
    async def test_multi_stream_fusion_workflow(self):
        """Test complete multi-stream fusion workflow"""
        fusion_service = MultiModalWebSocketFusion()
        await fusion_service.start()
        
        try:
            # Register multiple streams
            stream_configs = [
                ("visual_stream", FusionStreamType.VISUAL),
                ("text_stream", FusionStreamType.TEXT),
                ("audio_stream", FusionStreamType.AUDIO)
            ]
            
            for stream_id, stream_type in stream_configs:
                config = FusionStreamConfig(stream_type=stream_type)
                await fusion_service.register_fusion_stream(stream_id, config)
            
            # Process fusion data for each stream
            for stream_id, stream_type in stream_configs:
                fusion_data = FusionData(
                    stream_id=stream_id,
                    stream_type=stream_type,
                    data={"test": f"data_{stream_type.value}"},
                    timestamp=time.time(),
                    requires_gpu=stream_type in [FusionStreamType.VISUAL, FusionStreamType.AUDIO]
                )
                
                if fusion_data.requires_gpu:
                    await fusion_service._submit_to_gpu_provider(fusion_data)
                else:
                    await fusion_service._process_cpu_fusion(fusion_data)
            
            # Wait for processing
            await asyncio.sleep(2.0)
            
            # Check results
            metrics = fusion_service.get_comprehensive_metrics()
            assert metrics["fusion_metrics"]["total_fusions"] >= 3
            
        finally:
            await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_slow_gpu_provider_handling(self):
        """Test handling of slow GPU providers"""
        fusion_service = MultiModalWebSocketFusion()
        await fusion_service.start()
        
        try:
            # Make one GPU provider slow
            if "gpu_1" in fusion_service.gpu_providers:
                provider = fusion_service.gpu_providers["gpu_1"]
                # Simulate slow processing by increasing processing time
                original_process = provider._process_request
                
                async def slow_process(request_data):
                    await asyncio.sleep(1.0)  # Add delay
                    return await original_process(request_data)
                
                provider._process_request = slow_process
            
            # Submit fusion data
            fusion_data = FusionData(
                stream_id="test_stream",
                stream_type=FusionStreamType.VISUAL,
                data={"test": "data"},
                timestamp=time.time(),
                requires_gpu=True
            )
            
            # Should select fastest available provider
            await fusion_service._submit_to_gpu_provider(fusion_data)
            
            # Wait for processing
            await asyncio.sleep(2.0)
            
            # Check that processing completed
            assert fusion_service.fusion_metrics["total_fusions"] >= 1
            
        finally:
            await fusion_service.stop()
    
    @pytest.mark.asyncio
    async def test_system_under_load(self):
        """Test system behavior under high load"""
        fusion_service = MultiModalWebSocketFusion()
        await fusion_service.start()
        
        try:
            # Submit many fusion requests
            tasks = []
            for i in range(50):
                fusion_data = FusionData(
                    stream_id=f"stream_{i % 5}",
                    stream_type=FusionStreamType.VISUAL,
                    data={"test": f"data_{i}"},
                    timestamp=time.time(),
                    requires_gpu=True
                )
                
                task = asyncio.create_task(
                    fusion_service._submit_to_gpu_provider(fusion_data)
                )
                tasks.append(task)
            
            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for processing
            await asyncio.sleep(3.0)
            
            # Check system handled load
            metrics = fusion_service.get_comprehensive_metrics()
            
            # Should have processed many requests
            assert metrics["fusion_metrics"]["total_fusions"] >= 10
            
            # System should still be responsive
            assert metrics["system_status"] == "running"
            
        finally:
            await fusion_service.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
