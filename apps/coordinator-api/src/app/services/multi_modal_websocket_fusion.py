"""
Multi-Modal WebSocket Fusion Service

Advanced WebSocket stream architecture for multi-modal fusion with
per-stream backpressure handling and GPU provider flow control.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

import numpy as np

from aitbc import get_logger

logger = get_logger(__name__)
from .websocket_stream_manager import MessageType, StreamConfig, stream_manager


class FusionStreamType(Enum):
    """Types of fusion streams"""

    VISUAL = "visual"
    TEXT = "text"
    AUDIO = "audio"
    SENSOR = "sensor"
    CONTROL = "control"
    METRICS = "metrics"


class GPUProviderStatus(Enum):
    """GPU provider status"""

    AVAILABLE = "available"
    BUSY = "busy"
    SLOW = "slow"
    OVERLOADED = "overloaded"
    OFFLINE = "offline"


@dataclass
class FusionStreamConfig:
    """Configuration for fusion streams"""

    stream_type: FusionStreamType
    max_queue_size: int = 500
    gpu_timeout: float = 2.0
    fusion_timeout: float = 5.0
    batch_size: int = 8
    enable_gpu_acceleration: bool = True
    priority: int = 1  # Higher number = higher priority

    def to_stream_config(self) -> StreamConfig:
        """Convert to WebSocket stream config"""
        return StreamConfig(
            max_queue_size=self.max_queue_size,
            send_timeout=self.fusion_timeout,
            heartbeat_interval=30.0,
            slow_consumer_threshold=0.5,
            backpressure_threshold=0.7,
            drop_bulk_threshold=0.85,
            enable_compression=True,
            priority_send=True,
        )


@dataclass
class FusionData:
    """Multi-modal fusion data"""

    stream_id: str
    stream_type: FusionStreamType
    data: Any
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_gpu: bool = False
    processing_priority: int = 1


@dataclass
class GPUProviderMetrics:
    """GPU provider performance metrics"""

    provider_id: str
    status: GPUProviderStatus
    avg_processing_time: float
    queue_size: int
    gpu_utilization: float
    memory_usage: float
    error_rate: float
    last_update: float


class GPUProviderFlowControl:
    """Flow control for GPU providers"""

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self.metrics = GPUProviderMetrics(
            provider_id=provider_id,
            status=GPUProviderStatus.AVAILABLE,
            avg_processing_time=0.0,
            queue_size=0,
            gpu_utilization=0.0,
            memory_usage=0.0,
            error_rate=0.0,
            last_update=time.time(),
        )

        # Flow control queues
        self.input_queue = asyncio.Queue(maxsize=100)
        self.output_queue = asyncio.Queue(maxsize=100)
        self.control_queue = asyncio.Queue(maxsize=50)

        # Flow control parameters
        self.max_concurrent_requests = 4
        self.current_requests = 0
        self.slow_threshold = 2.0  # seconds
        self.overload_threshold = 0.8  # queue fill ratio

        # Performance tracking
        self.request_times = []
        self.error_count = 0
        self.total_requests = 0

        # Flow control task
        self._flow_control_task = None
        self._running = False

    async def start(self):
        """Start flow control"""
        if self._running:
            return

        self._running = True
        self._flow_control_task = asyncio.create_task(self._flow_control_loop())
        logger.info(f"GPU provider flow control started: {self.provider_id}")

    async def stop(self):
        """Stop flow control"""
        if not self._running:
            return

        self._running = False

        if self._flow_control_task:
            self._flow_control_task.cancel()
            try:
                await self._flow_control_task
            except asyncio.CancelledError:
                pass

        logger.info(f"GPU provider flow control stopped: {self.provider_id}")

    async def submit_request(self, data: FusionData) -> str | None:
        """Submit request with flow control"""
        if not self._running:
            return None

        # Check provider status
        if self.metrics.status == GPUProviderStatus.OFFLINE:
            logger.warning(f"GPU provider {self.provider_id} is offline")
            return None

        # Check backpressure
        if self.input_queue.qsize() / self.input_queue.maxsize > self.overload_threshold:
            self.metrics.status = GPUProviderStatus.OVERLOADED
            logger.warning(f"GPU provider {self.provider_id} is overloaded")
            return None

        # Submit request
        request_id = str(uuid4())
        request_data = {"request_id": request_id, "data": data, "timestamp": time.time()}

        try:
            await asyncio.wait_for(self.input_queue.put(request_data), timeout=1.0)
            return request_id
        except TimeoutError:
            logger.warning(f"Request timeout for GPU provider {self.provider_id}")
            return None

    async def get_result(self, request_id: str, timeout: float = 5.0) -> Any | None:
        """Get processing result"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Check output queue
                result = await asyncio.wait_for(self.output_queue.get(), timeout=0.1)

                if result.get("request_id") == request_id:
                    return result.get("data")

                # Put back if not our result
                await self.output_queue.put(result)

            except TimeoutError:
                continue

        return None

    async def _flow_control_loop(self):
        """Main flow control loop"""
        while self._running:
            try:
                # Get next request
                request_data = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)

                # Check concurrent request limit
                if self.current_requests >= self.max_concurrent_requests:
                    # Re-queue request
                    await self.input_queue.put(request_data)
                    await asyncio.sleep(0.1)
                    continue

                # Process request
                self.current_requests += 1
                self.total_requests += 1

                asyncio.create_task(self._process_request(request_data))

            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Flow control error for {self.provider_id}: {e}")
                await asyncio.sleep(0.1)

    async def _process_request(self, request_data: dict[str, Any]):
        """Process individual request"""
        request_id = request_data["request_id"]
        data: FusionData = request_data["data"]
        start_time = time.time()

        try:
            # Simulate GPU processing
            if data.requires_gpu:
                # Simulate GPU processing time
                processing_time = np.random.uniform(0.5, 3.0)
                await asyncio.sleep(processing_time)

                # Simulate GPU result
                result = {
                    "processed_data": f"gpu_processed_{data.stream_type}",
                    "processing_time": processing_time,
                    "gpu_utilization": np.random.uniform(0.3, 0.9),
                    "memory_usage": np.random.uniform(0.4, 0.8),
                }
            else:
                # CPU processing
                processing_time = np.random.uniform(0.1, 0.5)
                await asyncio.sleep(processing_time)

                result = {"processed_data": f"cpu_processed_{data.stream_type}", "processing_time": processing_time}

            # Update metrics
            actual_time = time.time() - start_time
            self._update_metrics(actual_time, success=True)

            # Send result
            await self.output_queue.put({"request_id": request_id, "data": result, "timestamp": time.time()})

        except Exception as e:
            logger.error(f"Request processing error for {self.provider_id}: {e}")
            self._update_metrics(time.time() - start_time, success=False)

            # Send error result
            await self.output_queue.put({"request_id": request_id, "error": str(e), "timestamp": time.time()})

        finally:
            self.current_requests -= 1

    def _update_metrics(self, processing_time: float, success: bool):
        """Update provider metrics"""
        # Update processing time
        self.request_times.append(processing_time)
        if len(self.request_times) > 100:
            self.request_times.pop(0)

        self.metrics.avg_processing_time = np.mean(self.request_times)

        # Update error rate
        if not success:
            self.error_count += 1

        self.metrics.error_rate = self.error_count / max(self.total_requests, 1)

        # Update queue sizes
        self.metrics.queue_size = self.input_queue.qsize()

        # Update status
        if self.metrics.error_rate > 0.1:
            self.metrics.status = GPUProviderStatus.OFFLINE
        elif self.metrics.avg_processing_time > self.slow_threshold:
            self.metrics.status = GPUProviderStatus.SLOW
        elif self.metrics.queue_size > self.input_queue.maxsize * 0.8:
            self.metrics.status = GPUProviderStatus.OVERLOADED
        elif self.current_requests >= self.max_concurrent_requests:
            self.metrics.status = GPUProviderStatus.BUSY
        else:
            self.metrics.status = GPUProviderStatus.AVAILABLE

        self.metrics.last_update = time.time()

    def get_metrics(self) -> dict[str, Any]:
        """Get provider metrics"""
        return {
            "provider_id": self.provider_id,
            "status": self.metrics.status.value,
            "avg_processing_time": self.metrics.avg_processing_time,
            "queue_size": self.metrics.queue_size,
            "current_requests": self.current_requests,
            "max_concurrent_requests": self.max_concurrent_requests,
            "error_rate": self.metrics.error_rate,
            "total_requests": self.total_requests,
            "last_update": self.metrics.last_update,
        }


class MultiModalWebSocketFusion:
    """Multi-modal fusion service with WebSocket streaming and backpressure control"""

    def __init__(self):
        self.stream_manager = stream_manager
        self.fusion_service = None  # Will be injected
        self.gpu_providers: dict[str, GPUProviderFlowControl] = {}

        # Fusion streams
        self.fusion_streams: dict[str, FusionStreamConfig] = {}
        self.active_fusions: dict[str, dict[str, Any]] = {}

        # Performance metrics
        self.fusion_metrics = {
            "total_fusions": 0,
            "successful_fusions": 0,
            "failed_fusions": 0,
            "avg_fusion_time": 0.0,
            "gpu_utilization": 0.0,
            "memory_usage": 0.0,
        }

        # Backpressure control
        self.backpressure_enabled = True
        self.global_queue_size = 0
        self.max_global_queue_size = 10000

        # Running state
        self._running = False
        self._monitor_task = None

    async def start(self):
        """Start the fusion service"""
        if self._running:
            return

        self._running = True

        # Start stream manager
        await self.stream_manager.start()

        # Initialize GPU providers
        await self._initialize_gpu_providers()

        # Start monitoring
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("Multi-Modal WebSocket Fusion started")

    async def stop(self):
        """Stop the fusion service"""
        if not self._running:
            return

        self._running = False

        # Stop GPU providers
        for provider in self.gpu_providers.values():
            await provider.stop()

        # Stop stream manager
        await self.stream_manager.stop()

        # Stop monitoring
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Multi-Modal WebSocket Fusion stopped")

    async def register_fusion_stream(self, stream_id: str, config: FusionStreamConfig):
        """Register a fusion stream"""
        self.fusion_streams[stream_id] = config
        logger.info(f"Registered fusion stream: {stream_id} ({config.stream_type.value})")

    async def handle_websocket_connection(self, websocket, stream_id: str, stream_type: FusionStreamType):
        """Handle WebSocket connection for fusion stream"""
        config = FusionStreamConfig(stream_type=stream_type, max_queue_size=500, gpu_timeout=2.0, fusion_timeout=5.0)

        async with self.stream_manager.manage_stream(websocket, config.to_stream_config()):
            logger.info(f"Fusion stream connected: {stream_id} ({stream_type.value})")

            try:
                # Handle incoming messages
                async for message in websocket:
                    await self._handle_stream_message(stream_id, stream_type, message)

            except Exception as e:
                logger.error(f"Error in fusion stream {stream_id}: {e}")

    async def _handle_stream_message(self, stream_id: str, stream_type: FusionStreamType, message: str):
        """Handle incoming stream message"""
        try:
            data = json.loads(message)

            # Create fusion data
            fusion_data = FusionData(
                stream_id=stream_id,
                stream_type=stream_type,
                data=data.get("data"),
                timestamp=time.time(),
                metadata=data.get("metadata", {}),
                requires_gpu=data.get("requires_gpu", False),
                processing_priority=data.get("priority", 1),
            )

            # Submit to GPU provider if needed
            if fusion_data.requires_gpu:
                await self._submit_to_gpu_provider(fusion_data)
            else:
                await self._process_cpu_fusion(fusion_data)

        except Exception as e:
            logger.error(f"Error handling stream message: {e}")

    async def _submit_to_gpu_provider(self, fusion_data: FusionData):
        """Submit fusion data to GPU provider"""
        # Select best GPU provider
        provider_id = await self._select_gpu_provider(fusion_data)

        if not provider_id:
            logger.warning("No available GPU providers")
            await self._handle_fusion_error(fusion_data, "No GPU providers available")
            return

        provider = self.gpu_providers[provider_id]

        # Submit request
        request_id = await provider.submit_request(fusion_data)

        if not request_id:
            await self._handle_fusion_error(fusion_data, "GPU provider overloaded")
            return

        # Wait for result
        result = await provider.get_result(request_id, timeout=5.0)

        if result and "error" not in result:
            await self._handle_fusion_result(fusion_data, result)
        else:
            error = result.get("error", "Unknown error") if result else "Timeout"
            await self._handle_fusion_error(fusion_data, error)

    async def _process_cpu_fusion(self, fusion_data: FusionData):
        """Process fusion data on CPU"""
        try:
            # Simulate CPU fusion processing
            processing_time = np.random.uniform(0.1, 0.5)
            await asyncio.sleep(processing_time)

            result = {
                "processed_data": f"cpu_fused_{fusion_data.stream_type}",
                "processing_time": processing_time,
                "fusion_type": "cpu",
            }

            await self._handle_fusion_result(fusion_data, result)

        except Exception as e:
            logger.error(f"CPU fusion error: {e}")
            await self._handle_fusion_error(fusion_data, str(e))

    async def _handle_fusion_result(self, fusion_data: FusionData, result: dict[str, Any]):
        """Handle successful fusion result"""
        # Update metrics
        self.fusion_metrics["total_fusions"] += 1
        self.fusion_metrics["successful_fusions"] += 1

        # Broadcast result
        broadcast_data = {
            "type": "fusion_result",
            "stream_id": fusion_data.stream_id,
            "stream_type": fusion_data.stream_type.value,
            "result": result,
            "timestamp": time.time(),
        }

        await self.stream_manager.broadcast_to_all(broadcast_data, MessageType.IMPORTANT)

        logger.info(f"Fusion completed for {fusion_data.stream_id}")

    async def _handle_fusion_error(self, fusion_data: FusionData, error: str):
        """Handle fusion error"""
        # Update metrics
        self.fusion_metrics["total_fusions"] += 1
        self.fusion_metrics["failed_fusions"] += 1

        # Broadcast error
        error_data = {
            "type": "fusion_error",
            "stream_id": fusion_data.stream_id,
            "stream_type": fusion_data.stream_type.value,
            "error": error,
            "timestamp": time.time(),
        }

        await self.stream_manager.broadcast_to_all(error_data, MessageType.CRITICAL)

        logger.error(f"Fusion error for {fusion_data.stream_id}: {error}")

    async def _select_gpu_provider(self, fusion_data: FusionData) -> str | None:
        """Select best GPU provider based on load and performance"""
        available_providers = []

        for provider_id, provider in self.gpu_providers.items():
            metrics = provider.get_metrics()

            # Check if provider is available
            if metrics["status"] == GPUProviderStatus.AVAILABLE.value:
                available_providers.append((provider_id, metrics))

        if not available_providers:
            return None

        # Select provider with lowest queue size and processing time
        best_provider = min(available_providers, key=lambda x: (x[1]["queue_size"], x[1]["avg_processing_time"]))

        return best_provider[0]

    async def _initialize_gpu_providers(self):
        """Initialize GPU providers"""
        # Create mock GPU providers
        provider_configs = [
            {"provider_id": "gpu_1", "max_concurrent": 4},
            {"provider_id": "gpu_2", "max_concurrent": 2},
            {"provider_id": "gpu_3", "max_concurrent": 6},
        ]

        for config in provider_configs:
            provider = GPUProviderFlowControl(config["provider_id"])
            provider.max_concurrent_requests = config["max_concurrent"]
            await provider.start()
            self.gpu_providers[config["provider_id"]] = provider

        logger.info(f"Initialized {len(self.gpu_providers)} GPU providers")

    async def _monitor_loop(self):
        """Monitor system performance and backpressure"""
        while self._running:
            try:
                # Update global metrics
                await self._update_global_metrics()

                # Check backpressure
                if self.backpressure_enabled:
                    await self._check_backpressure()

                # Monitor GPU providers
                await self._monitor_gpu_providers()

                # Sleep
                await asyncio.sleep(10)  # Monitor every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1)

    async def _update_global_metrics(self):
        """Update global performance metrics"""
        # Get stream manager metrics
        manager_metrics = self.stream_manager.get_manager_metrics()

        # Update global queue size
        self.global_queue_size = manager_metrics["total_queue_size"]

        # Calculate GPU utilization
        total_gpu_util = 0
        total_memory = 0
        active_providers = 0

        for provider in self.gpu_providers.values():
            metrics = provider.get_metrics()
            if metrics["status"] != GPUProviderStatus.OFFLINE.value:
                total_gpu_util += metrics.get("gpu_utilization", 0)
                total_memory += metrics.get("memory_usage", 0)
                active_providers += 1

        if active_providers > 0:
            self.fusion_metrics["gpu_utilization"] = total_gpu_util / active_providers
            self.fusion_metrics["memory_usage"] = total_memory / active_providers

    async def _check_backpressure(self):
        """Check and handle backpressure"""
        if self.global_queue_size > self.max_global_queue_size * 0.8:
            logger.warning("High backpressure detected, applying flow control")

            # Get slow streams
            slow_streams = self.stream_manager.get_slow_streams(threshold=0.8)

            # Handle slow streams
            for stream_id in slow_streams:
                await self.stream_manager.handle_slow_consumer(stream_id, "throttle")

    async def _monitor_gpu_providers(self):
        """Monitor GPU provider health"""
        for provider_id, provider in self.gpu_providers.items():
            metrics = provider.get_metrics()

            # Check for unhealthy providers
            if metrics["status"] == GPUProviderStatus.OFFLINE.value:
                logger.warning(f"GPU provider {provider_id} is offline")

            elif metrics["error_rate"] > 0.1:
                logger.warning(f"GPU provider {provider_id} has high error rate: {metrics['error_rate']}")

            elif metrics["avg_processing_time"] > 5.0:
                logger.warning(f"GPU provider {provider_id} is slow: {metrics['avg_processing_time']}s")

    def get_comprehensive_metrics(self) -> dict[str, Any]:
        """Get comprehensive system metrics"""
        # Get stream manager metrics
        stream_metrics = self.stream_manager.get_manager_metrics()

        # Get GPU provider metrics
        gpu_metrics = {}
        for provider_id, provider in self.gpu_providers.items():
            gpu_metrics[provider_id] = provider.get_metrics()

        # Get fusion metrics
        fusion_metrics = self.fusion_metrics.copy()

        # Calculate success rate
        if fusion_metrics["total_fusions"] > 0:
            fusion_metrics["success_rate"] = fusion_metrics["successful_fusions"] / fusion_metrics["total_fusions"]
        else:
            fusion_metrics["success_rate"] = 0.0

        return {
            "timestamp": time.time(),
            "system_status": "running" if self._running else "stopped",
            "backpressure_enabled": self.backpressure_enabled,
            "global_queue_size": self.global_queue_size,
            "max_global_queue_size": self.max_global_queue_size,
            "stream_metrics": stream_metrics,
            "gpu_metrics": gpu_metrics,
            "fusion_metrics": fusion_metrics,
            "active_fusion_streams": len(self.fusion_streams),
            "registered_gpu_providers": len(self.gpu_providers),
        }


# Global fusion service instance
multimodal_fusion_service = MultiModalWebSocketFusion()
