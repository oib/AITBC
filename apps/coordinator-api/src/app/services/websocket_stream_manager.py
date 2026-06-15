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
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from websockets.legacy.server import WebSocketServerProtocol
WebSocketServerProtocol = Any  # type: ignore[assignment, misc]
from aitbc import get_logger

logger = get_logger(__name__)

class StreamStatus(Enum):
    """Stream connection status"""
    CONNECTING = 'connecting'
    CONNECTED = 'connected'
    SLOW_CONSUMER = 'slow_consumer'
    BACKPRESSURE = 'backpressure'
    DISCONNECTED = 'disconnected'
    ERROR = 'error'

class MessageType(Enum):
    """Message types for stream classification"""
    CRITICAL = 'critical'
    IMPORTANT = 'important'
    BULK = 'bulk'
    CONTROL = 'control'

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
        return {'id': self.message_id, 'type': self.message_type.value, 'timestamp': self.timestamp, 'data': self.data}

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

    def update_send_metrics(self, send_time: float, message_size: int) -> None:
        """Update send performance metrics"""
        self.messages_sent += 1
        self.bytes_sent += message_size
        self.last_send_time = time.time()
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
    slow_consumer_threshold: float = 0.5
    backpressure_threshold: float = 0.8
    drop_bulk_threshold: float = 0.9
    enable_compression: bool = True
    priority_send: bool = True

class BoundedMessageQueue:
    """Bounded queue with priority and backpressure handling"""

    def __init__(self, max_size: int=1000):
        self.max_size = max_size
        self.queues: dict[MessageType, deque[StreamMessage]] = {MessageType.CRITICAL: deque(maxlen=max_size // 4), MessageType.IMPORTANT: deque(maxlen=max_size // 2), MessageType.BULK: deque(maxlen=max_size // 4), MessageType.CONTROL: deque(maxlen=100)}
        self.total_size = 0
        self._lock = asyncio.Lock()

    async def put(self, message: StreamMessage) -> bool:
        """Add message to queue with backpressure handling"""
        async with self._lock:
            if self.total_size >= self.max_size:
                if message.message_type == MessageType.BULK:
                    return False
                if message.message_type == MessageType.IMPORTANT:
                    if self.queues[MessageType.IMPORTANT]:
                        self.queues[MessageType.IMPORTANT].popleft()
                        self.total_size -= 1
                    else:
                        return False
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
        self._send_lock = asyncio.Lock()
        self._sender_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = False
        self._finalizer = weakref.finalize(self, self._cleanup)

    async def start(self) -> None:
        """Start stream processing"""
        if self._running:
            return
        self._running = True
        self.status = StreamStatus.CONNECTED
        self._sender_task = asyncio.create_task(self._sender_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info('Stream %s started', self.stream_id)

    async def stop(self) -> None:
        """Stop stream processing"""
        if not self._running:
            return
        self._running = False
        self.status = StreamStatus.DISCONNECTED
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
        logger.info('Stream %s stopped', self.stream_id)

    async def send_message(self, data: Any, message_type: MessageType=MessageType.IMPORTANT) -> bool:
        """Send message with backpressure handling"""
        if not self._running:
            return False
        message = StreamMessage(data=data, message_type=message_type)
        queue_ratio = self.queue.fill_ratio()
        if queue_ratio > self.config.backpressure_threshold:
            self.status = StreamStatus.BACKPRESSURE
            self.metrics.backpressure_events += 1
            if message_type == MessageType.BULK and queue_ratio > self.config.drop_bulk_threshold:
                self.metrics.messages_dropped += 1
                return False
        success = await self.queue.put(message)
        if not success:
            self.metrics.messages_dropped += 1
        return success

    async def _sender_loop(self) -> None:
        """Main sender loop with backpressure control"""
        while self._running:
            try:
                message = await self.queue.get()
                if message is None:
                    await asyncio.sleep(0.01)
                    continue
                start_time = time.time()
                success = await self._send_with_backpressure(message)
                send_time = time.time() - start_time
                if success:
                    message_size = len(json.dumps(message.to_dict()).encode())
                    self.metrics.update_send_metrics(send_time, message_size)
                else:
                    message.retry_count += 1
                    if message.retry_count < message.max_retries:
                        await self.queue.put(message)
                    else:
                        self.metrics.messages_dropped += 1
                        logger.warning('Message %s dropped after max retries', message.message_id)
                if send_time > self.config.slow_consumer_threshold:
                    self.slow_consumer_count += 1
                    self.metrics.slow_consumer_events += 1
                    if self.slow_consumer_count > 5:
                        self.status = StreamStatus.SLOW_CONSUMER
                        logger.warning('Stream %s detected as slow consumer', self.stream_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Error in sender loop for stream %s: %s', self.stream_id, e)
                await asyncio.sleep(0.1)

    async def _send_with_backpressure(self, message: StreamMessage) -> bool:
        """Send message with backpressure and timeout protection"""
        try:
            async with self._send_lock:
                message_data = message.to_dict()
                if self.config.enable_compression:
                    message_str = json.dumps(message_data, separators=(',', ':'))
                    if len(message_str) > 1024:
                        message_data['_compressed'] = True
                        message_str = json.dumps(message_data, separators=(',', ':'))
                else:
                    message_str = json.dumps(message_data)
                await asyncio.wait_for(self.websocket.send(message_str), timeout=self.config.send_timeout)
                return True
        except TimeoutError:
            logger.warning('Send timeout for stream %s', self.stream_id)
            return False
        except ConnectionClosed:
            logger.info('Connection closed for stream %s', self.stream_id)
            await self.stop()
            return False
        except Exception as e:
            logger.error('Send error for stream %s: %s', self.stream_id, e)
            return False

    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop for connection health monitoring"""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                heartbeat_msg = {'type': 'heartbeat', 'timestamp': time.time(), 'stream_id': self.stream_id, 'queue_size': self.queue.size(), 'status': self.status.value}
                await self.send_message(heartbeat_msg, MessageType.CONTROL)
                self.last_heartbeat = time.time()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Heartbeat error for stream %s: %s', self.stream_id, e)

    def get_metrics(self) -> dict[str, Any]:
        """Get stream metrics"""
        return {'stream_id': self.stream_id, 'status': self.status.value, 'queue_size': self.queue.size(), 'queue_fill_ratio': self.queue.fill_ratio(), 'messages_sent': self.metrics.messages_sent, 'messages_dropped': self.metrics.messages_dropped, 'bytes_sent': self.metrics.bytes_sent, 'avg_send_time': self.metrics.avg_send_time, 'backpressure_events': self.metrics.backpressure_events, 'slow_consumer_events': self.metrics.slow_consumer_events, 'last_heartbeat': self.last_heartbeat}

    def _cleanup(self) -> None:
        """Cleanup resources"""
        if self._running:
            logger.warning('Stream %s cleanup called while running', self.stream_id)

class WebSocketStreamManager:
    """Manages multiple WebSocket streams with backpressure control"""

    def __init__(self, default_config: StreamConfig | None=None):
        self.default_config = default_config or StreamConfig()
        self.streams: dict[str, WebSocketStream] = {}
        self.stream_configs: dict[str, StreamConfig] = {}
        self.total_connections = 0
        self.total_messages_sent = 0
        self.total_messages_dropped = 0
        self._manager_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._broadcast_queue: asyncio.Queue[tuple[Any, MessageType]] = asyncio.Queue(maxsize=10000)
        self._broadcast_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the stream manager"""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info('WebSocket Stream Manager started')

    async def stop(self) -> None:
        """Stop the stream manager"""
        if not self._running:
            return
        self._running = False
        streams_to_stop = list(self.streams.values())
        for stream in streams_to_stop:
            await stream.stop()
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
        logger.info('WebSocket Stream Manager stopped')

    async def manage_stream(self, websocket: Any, config: StreamConfig | None=None) -> AsyncGenerator['WebSocketStream']:
        """Context manager for stream lifecycle"""
        stream_id = str(uuid.uuid4())
        stream_config = config or self.default_config
        stream = None
        try:
            stream = WebSocketStream(websocket, stream_id, stream_config)
            await stream.start()
            async with self._manager_lock:
                self.streams[stream_id] = stream
                self.stream_configs[stream_id] = stream_config
                self.total_connections += 1
            logger.info('Stream %s added to manager', stream_id)
            yield stream
        except Exception as e:
            logger.error('Error managing stream %s: %s', stream_id, e)
            raise
        finally:
            if stream and stream_id in self.streams:
                await stream.stop()
                async with self._manager_lock:
                    del self.streams[stream_id]
                    if stream_id in self.stream_configs:
                        del self.stream_configs[stream_id]
                    self.total_connections -= 1
                logger.info('Stream %s removed from manager', stream_id)

    async def broadcast_to_all(self, data: Any, message_type: MessageType=MessageType.IMPORTANT) -> None:
        """Broadcast message to all streams"""
        if not self._running:
            return
        try:
            await self._broadcast_queue.put((data, message_type))
        except asyncio.QueueFull:
            logger.warning('Broadcast queue full, dropping message')
            self.total_messages_dropped += 1

    async def broadcast_to_stream(self, stream_id: str, data: Any, message_type: MessageType=MessageType.IMPORTANT) -> None:
        """Send message to specific stream"""
        async with self._manager_lock:
            stream = self.streams.get(stream_id)
            if stream:
                await stream.send_message(data, message_type)

    async def _broadcast_loop(self) -> None:
        """Broadcast messages to all streams"""
        while self._running:
            try:
                data, message_type = await self._broadcast_queue.get()
                tasks = []
                async with self._manager_lock:
                    streams = list(self.streams.values())
                for stream in streams:
                    task = asyncio.create_task(stream.send_message(data, message_type))
                    tasks.append(task)
                if tasks:
                    try:
                        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
                    except TimeoutError:
                        logger.warning('Broadcast timeout, some streams may be slow')
                self.total_messages_sent += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Error in broadcast loop: %s', e)
                await asyncio.sleep(0.1)

    async def _cleanup_loop(self) -> None:
        """Cleanup disconnected streams"""
        while self._running:
            try:
                await asyncio.sleep(60)
                disconnected_streams = []
                async with self._manager_lock:
                    for stream_id, stream in self.streams.items():
                        if stream.status == StreamStatus.DISCONNECTED:
                            disconnected_streams.append(stream_id)
                for stream_id in disconnected_streams:
                    if stream_id in self.streams:
                        stream = self.streams[stream_id]
                        await stream.stop()
                        del self.streams[stream_id]
                        if stream_id in self.stream_configs:
                            del self.stream_configs[stream_id]
                        self.total_connections -= 1
                        logger.info('Cleaned up disconnected stream %s', stream_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Error in cleanup loop: %s', e)

    async def get_manager_metrics(self) -> dict[str, Any]:
        """Get comprehensive manager metrics"""
        async with self._manager_lock:
            stream_metrics = []
            for stream in self.streams.values():
                stream_metrics.append(stream.get_metrics())
            total_queue_size = sum(m['queue_size'] for m in stream_metrics)
            total_messages_sent = sum(m['messages_sent'] for m in stream_metrics)
            total_messages_dropped = sum(m['messages_dropped'] for m in stream_metrics)
            total_bytes_sent = sum(m['bytes_sent'] for m in stream_metrics)
            status_counts: dict[str, int] = {}
            for stream in self.streams.values():
                status = stream.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            return {'manager_status': 'running' if self._running else 'stopped', 'total_connections': self.total_connections, 'active_streams': len(self.streams), 'total_queue_size': total_queue_size, 'total_messages_sent': total_messages_sent, 'total_messages_dropped': total_messages_dropped, 'total_bytes_sent': total_bytes_sent, 'broadcast_queue_size': self._broadcast_queue.qsize(), 'stream_status_distribution': status_counts, 'stream_metrics': stream_metrics}

    async def update_stream_config(self, stream_id: str, config: StreamConfig) -> None:
        """Update configuration for specific stream"""
        async with self._manager_lock:
            if stream_id in self.streams:
                self.stream_configs[stream_id] = config
                logger.info('Updated config for stream %s', stream_id)

    def get_slow_streams(self, threshold: float=0.8) -> list[str]:
        """Get streams with high queue fill ratios"""
        slow_streams = []
        for stream_id, stream in self.streams.items():
            if stream.queue.fill_ratio() > threshold:
                slow_streams.append(stream_id)
        return slow_streams

    async def handle_slow_consumer(self, stream_id: str, action: str='warn') -> None:
        """Handle slow consumer streams"""
        async with self._manager_lock:
            stream = self.streams.get(stream_id)
            if not stream:
                return
            if action == 'warn':
                logger.warning('Slow consumer detected: %s', stream_id)
                await stream.send_message({'warning': 'Slow consumer detected', 'stream_id': stream_id}, MessageType.CONTROL)
            elif action == 'throttle':
                new_config = StreamConfig(max_queue_size=stream.config.max_queue_size // 2, send_timeout=stream.config.send_timeout * 2)
                await self.update_stream_config(stream_id, new_config)
                logger.info('Throttled slow consumer: %s', stream_id)
            elif action == 'disconnect':
                logger.warning('Disconnecting slow consumer: %s', stream_id)
                await stream.stop()
stream_manager = WebSocketStreamManager()
