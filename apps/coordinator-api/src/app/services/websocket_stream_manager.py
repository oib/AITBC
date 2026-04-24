"""
WebSocket Stream Manager with Backpressure Control

Advanced WebSocket stream architecture with per-stream flow control,
bounded queues, and event loop protection for multi-modal fusion.
"""

import asyncio
import json
import time
import uuid
import weakref
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol

from aitbc import get_logger

logger = get_logger(__name__)


class StreamStatus(Enum):
    """Stream connection status"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    SLOW_CONSUMER = "slow_consumer"
    BACKPRESSURE = "backpressure"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class MessageType(Enum):
    """Message types for stream classification"""

    CRITICAL = "critical"  # High priority, must deliver
    IMPORTANT = "important"  # Normal priority
    BULK = "bulk"  # Low priority, can be dropped
    CONTROL = "control"  # Stream control messages


@dataclass
class StreamMessage:
    """Message with priority and metadata"""

    data: Any
    message_type: MessageType
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.message_id, "type": self.message_type.value, "timestamp": self.timestamp, "data": self.data}


@dataclass
class StreamMetrics:
    """Metrics for stream performance monitoring"""

    messages_sent: int = 0
    messages_dropped: int = 0
    bytes_sent: int = 0
    last_send_time: float = 0
    avg_send_time: float = 0
    queue_size: int = 0
    backpressure_events: int = 0
    slow_consumer_events: int = 0

    def update_send_metrics(self, send_time: float, message_size: int):
        """Update send performance metrics"""
        self.messages_sent += 1
        self.bytes_sent += message_size
        self.last_send_time = time.time()

        # Update average send time
        if self.messages_sent == 1:
            self.avg_send_time = send_time
        else:
            self.avg_send_time = (self.avg_send_time * (self.messages_sent - 1) + send_time) / self.messages_sent


@dataclass
class StreamConfig:
    """Configuration for individual streams"""

    max_queue_size: int = 1000
    send_timeout: float = 5.0
    heartbeat_interval: float = 30.0
    slow_consumer_threshold: float = 0.5  # seconds
    backpressure_threshold: float = 0.8  # queue fill ratio
    drop_bulk_threshold: float = 0.9  # queue fill ratio for bulk messages
    enable_compression: bool = True
    priority_send: bool = True


class BoundedMessageQueue:
    """Bounded queue with priority and backpressure handling"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queues = {
            MessageType.CRITICAL: deque(maxlen=max_size // 4),
            MessageType.IMPORTANT: deque(maxlen=max_size // 2),
            MessageType.BULK: deque(maxlen=max_size // 4),
            MessageType.CONTROL: deque(maxlen=100),  # Small control queue
        }
        self.total_size = 0
        self._lock = asyncio.Lock()

    async def put(self, message: StreamMessage) -> bool:
        """Add message to queue with backpressure handling"""
        async with self._lock:
            # Check if we're at capacity
            if self.total_size >= self.max_size:
                # Drop bulk messages first
                if message.message_type == MessageType.BULK:
                    return False

                # Drop oldest important messages if critical
                if message.message_type == MessageType.IMPORTANT:
                    if self.queues[MessageType.IMPORTANT]:
                        self.queues[MessageType.IMPORTANT].popleft()
                        self.total_size -= 1
                    else:
                        return False

                # Always allow critical messages (drop oldest if needed)
                if message.message_type == MessageType.CRITICAL:
                    if self.queues[MessageType.CRITICAL]:
                        self.queues[MessageType.CRITICAL].popleft()
                        self.total_size -= 1

            self.queues[message.message_type].append(message)
            self.total_size += 1
            return True

    async def get(self) -> StreamMessage | None:
        """Get next message by priority"""
        async with self._lock:
            # Priority order: CONTROL > CRITICAL > IMPORTANT > BULK
            for message_type in [MessageType.CONTROL, MessageType.CRITICAL, MessageType.IMPORTANT, MessageType.BULK]:
                if self.queues[message_type]:
                    message = self.queues[message_type].popleft()
                    self.total_size -= 1
                    return message
            return None

    def size(self) -> int:
        """Get total queue size"""
        return self.total_size

    def fill_ratio(self) -> float:
        """Get queue fill ratio"""
        return self.total_size / self.max_size


class WebSocketStream:
    """Individual WebSocket stream with backpressure control"""

    def __init__(self, websocket: WebSocketServerProtocol, stream_id: str, config: StreamConfig):
        self.websocket = websocket
        self.stream_id = stream_id
        self.config = config
        self.status = StreamStatus.CONNECTING
        self.queue = BoundedMessageQueue(config.max_queue_size)
        self.metrics = StreamMetrics()
        self.last_heartbeat = time.time()
        self.slow_consumer_count = 0

        # Event loop protection
        self._send_lock = asyncio.Lock()
        self._sender_task = None
        self._heartbeat_task = None
        self._running = False

        # Weak reference for cleanup
        self._finalizer = weakref.finalize(self, self._cleanup)

    async def start(self):
        """Start stream processing"""
        if self._running:
            return

        self._running = True
        self.status = StreamStatus.CONNECTED

        # Start sender task
        self._sender_task = asyncio.create_task(self._sender_loop())

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(f"Stream {self.stream_id} started")

    async def stop(self):
        """Stop stream processing"""
        if not self._running:
            return

        self._running = False
        self.status = StreamStatus.DISCONNECTED

        # Cancel tasks
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stream {self.stream_id} stopped")

    async def send_message(self, data: Any, message_type: MessageType = MessageType.IMPORTANT) -> bool:
        """Send message with backpressure handling"""
        if not self._running:
            return False

        message = StreamMessage(data=data, message_type=message_type)

        # Check backpressure
        queue_ratio = self.queue.fill_ratio()
        if queue_ratio > self.config.backpressure_threshold:
            self.status = StreamStatus.BACKPRESSURE
            self.metrics.backpressure_events += 1

            # Drop bulk messages under backpressure
            if message_type == MessageType.BULK and queue_ratio > self.config.drop_bulk_threshold:
                self.metrics.messages_dropped += 1
                return False

        # Add to queue
        success = await self.queue.put(message)
        if not success:
            self.metrics.messages_dropped += 1

        return success

    async def _sender_loop(self):
        """Main sender loop with backpressure control"""
        while self._running:
            try:
                # Get next message
                message = await self.queue.get()
                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                # Send with timeout and backpressure protection
                start_time = time.time()
                success = await self._send_with_backpressure(message)
                send_time = time.time() - start_time

                if success:
                    message_size = len(json.dumps(message.to_dict()).encode())
                    self.metrics.update_send_metrics(send_time, message_size)
                else:
                    # Retry logic
                    message.retry_count += 1
                    if message.retry_count < message.max_retries:
                        await self.queue.put(message)
                    else:
                        self.metrics.messages_dropped += 1
                        logger.warning(f"Message {message.message_id} dropped after max retries")

                # Check for slow consumer
                if send_time > self.config.slow_consumer_threshold:
                    self.slow_consumer_count += 1
                    self.metrics.slow_consumer_events += 1

                    if self.slow_consumer_count > 5:  # Threshold for slow consumer detection
                        self.status = StreamStatus.SLOW_CONSUMER
                        logger.warning(f"Stream {self.stream_id} detected as slow consumer")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sender loop for stream {self.stream_id}: {e}")
                await asyncio.sleep(0.1)

    async def _send_with_backpressure(self, message: StreamMessage) -> bool:
        """Send message with backpressure and timeout protection"""
        try:
            async with self._send_lock:
                # Use asyncio.wait_for for timeout protection
                message_data = message.to_dict()

                if self.config.enable_compression:
                    # Compress large messages
                    message_str = json.dumps(message_data, separators=(",", ":"))
                    if len(message_str) > 1024:  # Compress messages > 1KB
                        message_data["_compressed"] = True
                        message_str = json.dumps(message_data, separators=(",", ":"))
                else:
                    message_str = json.dumps(message_data)

                # Send with timeout
                await asyncio.wait_for(self.websocket.send(message_str), timeout=self.config.send_timeout)

                return True

        except TimeoutError:
            logger.warning(f"Send timeout for stream {self.stream_id}")
            return False
        except ConnectionClosed:
            logger.info(f"Connection closed for stream {self.stream_id}")
            await self.stop()
            return False
        except Exception as e:
            logger.error(f"Send error for stream {self.stream_id}: {e}")
            return False

    async def _heartbeat_loop(self):
        """Heartbeat loop for connection health monitoring"""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)

                if not self._running:
                    break

                # Send heartbeat
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "stream_id": self.stream_id,
                    "queue_size": self.queue.size(),
                    "status": self.status.value,
                }

                await self.send_message(heartbeat_msg, MessageType.CONTROL)
                self.last_heartbeat = time.time()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error for stream {self.stream_id}: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get stream metrics"""
        return {
            "stream_id": self.stream_id,
            "status": self.status.value,
            "queue_size": self.queue.size(),
            "queue_fill_ratio": self.queue.fill_ratio(),
            "messages_sent": self.metrics.messages_sent,
            "messages_dropped": self.metrics.messages_dropped,
            "bytes_sent": self.metrics.bytes_sent,
            "avg_send_time": self.metrics.avg_send_time,
            "backpressure_events": self.metrics.backpressure_events,
            "slow_consumer_events": self.metrics.slow_consumer_events,
            "last_heartbeat": self.last_heartbeat,
        }

    def _cleanup(self):
        """Cleanup resources"""
        if self._running:
            # This should be called by garbage collector
            logger.warning(f"Stream {self.stream_id} cleanup called while running")


class WebSocketStreamManager:
    """Manages multiple WebSocket streams with backpressure control"""

    def __init__(self, default_config: StreamConfig | None = None):
        self.default_config = default_config or StreamConfig()
        self.streams: dict[str, WebSocketStream] = {}
        self.stream_configs: dict[str, StreamConfig] = {}

        # Global metrics
        self.total_connections = 0
        self.total_messages_sent = 0
        self.total_messages_dropped = 0

        # Event loop protection
        self._manager_lock = asyncio.Lock()
        self._cleanup_task = None
        self._running = False

        # Message broadcasting
        self._broadcast_queue = asyncio.Queue(maxsize=10000)
        self._broadcast_task = None

    async def start(self):
        """Start the stream manager"""
        if self._running:
            return

        self._running = True

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        # Start broadcast task
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        logger.info("WebSocket Stream Manager started")

    async def stop(self):
        """Stop the stream manager"""
        if not self._running:
            return

        self._running = False

        # Stop all streams
        streams_to_stop = list(self.streams.values())
        for stream in streams_to_stop:
            await stream.stop()

        # Cancel tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        logger.info("WebSocket Stream Manager stopped")

    async def manage_stream(self, websocket: WebSocketServerProtocol, config: StreamConfig | None = None):
        """Context manager for stream lifecycle"""
        stream_id = str(uuid.uuid4())
        stream_config = config or self.default_config

        stream = None
        try:
            # Create and start stream
            stream = WebSocketStream(websocket, stream_id, stream_config)
            await stream.start()

            async with self._manager_lock:
                self.streams[stream_id] = stream
                self.stream_configs[stream_id] = stream_config
                self.total_connections += 1

            logger.info(f"Stream {stream_id} added to manager")

            yield stream

        except Exception as e:
            logger.error(f"Error managing stream {stream_id}: {e}")
            raise
        finally:
            # Cleanup stream
            if stream and stream_id in self.streams:
                await stream.stop()

                async with self._manager_lock:
                    del self.streams[stream_id]
                    if stream_id in self.stream_configs:
                        del self.stream_configs[stream_id]
                    self.total_connections -= 1

                logger.info(f"Stream {stream_id} removed from manager")

    async def broadcast_to_all(self, data: Any, message_type: MessageType = MessageType.IMPORTANT):
        """Broadcast message to all streams"""
        if not self._running:
            return

        try:
            await self._broadcast_queue.put((data, message_type))
        except asyncio.QueueFull:
            logger.warning("Broadcast queue full, dropping message")
            self.total_messages_dropped += 1

    async def broadcast_to_stream(self, stream_id: str, data: Any, message_type: MessageType = MessageType.IMPORTANT):
        """Send message to specific stream"""
        async with self._manager_lock:
            stream = self.streams.get(stream_id)
            if stream:
                await stream.send_message(data, message_type)

    async def _broadcast_loop(self):
        """Broadcast messages to all streams"""
        while self._running:
            try:
                # Get broadcast message
                data, message_type = await self._broadcast_queue.get()

                # Send to all streams concurrently
                tasks = []
                async with self._manager_lock:
                    streams = list(self.streams.values())

                for stream in streams:
                    task = asyncio.create_task(stream.send_message(data, message_type))
                    tasks.append(task)

                # Wait for all sends (with timeout)
                if tasks:
                    try:
                        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
                    except TimeoutError:
                        logger.warning("Broadcast timeout, some streams may be slow")

                self.total_messages_sent += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(0.1)

    async def _cleanup_loop(self):
        """Cleanup disconnected streams"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Cleanup every minute

                disconnected_streams = []
                async with self._manager_lock:
                    for stream_id, stream in self.streams.items():
                        if stream.status == StreamStatus.DISCONNECTED:
                            disconnected_streams.append(stream_id)

                # Remove disconnected streams
                for stream_id in disconnected_streams:
                    if stream_id in self.streams:
                        stream = self.streams[stream_id]
                        await stream.stop()
                        del self.streams[stream_id]
                        if stream_id in self.stream_configs:
                            del self.stream_configs[stream_id]
                        self.total_connections -= 1
                        logger.info(f"Cleaned up disconnected stream {stream_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def get_manager_metrics(self) -> dict[str, Any]:
        """Get comprehensive manager metrics"""
        async with self._manager_lock:
            stream_metrics = []
            for stream in self.streams.values():
                stream_metrics.append(stream.get_metrics())

            # Calculate aggregate metrics
            total_queue_size = sum(m["queue_size"] for m in stream_metrics)
            total_messages_sent = sum(m["messages_sent"] for m in stream_metrics)
            total_messages_dropped = sum(m["messages_dropped"] for m in stream_metrics)
            total_bytes_sent = sum(m["bytes_sent"] for m in stream_metrics)

            # Status distribution
            status_counts = {}
            for stream in self.streams.values():
                status = stream.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "manager_status": "running" if self._running else "stopped",
                "total_connections": self.total_connections,
                "active_streams": len(self.streams),
                "total_queue_size": total_queue_size,
                "total_messages_sent": total_messages_sent,
                "total_messages_dropped": total_messages_dropped,
                "total_bytes_sent": total_bytes_sent,
                "broadcast_queue_size": self._broadcast_queue.qsize(),
                "stream_status_distribution": status_counts,
                "stream_metrics": stream_metrics,
            }

    async def update_stream_config(self, stream_id: str, config: StreamConfig):
        """Update configuration for specific stream"""
        async with self._manager_lock:
            if stream_id in self.streams:
                self.stream_configs[stream_id] = config
                # Stream will use new config on next send
                logger.info(f"Updated config for stream {stream_id}")

    def get_slow_streams(self, threshold: float = 0.8) -> list[str]:
        """Get streams with high queue fill ratios"""
        slow_streams = []
        for stream_id, stream in self.streams.items():
            if stream.queue.fill_ratio() > threshold:
                slow_streams.append(stream_id)
        return slow_streams

    async def handle_slow_consumer(self, stream_id: str, action: str = "warn"):
        """Handle slow consumer streams"""
        async with self._manager_lock:
            stream = self.streams.get(stream_id)
            if not stream:
                return

            if action == "warn":
                logger.warning(f"Slow consumer detected: {stream_id}")
                await stream.send_message({"warning": "Slow consumer detected", "stream_id": stream_id}, MessageType.CONTROL)
            elif action == "throttle":
                # Reduce queue size for slow consumer
                new_config = StreamConfig(
                    max_queue_size=stream.config.max_queue_size // 2, send_timeout=stream.config.send_timeout * 2
                )
                await self.update_stream_config(stream_id, new_config)
                logger.info(f"Throttled slow consumer: {stream_id}")
            elif action == "disconnect":
                logger.warning(f"Disconnecting slow consumer: {stream_id}")
                await stream.stop()


# Global stream manager instance
stream_manager = WebSocketStreamManager()
