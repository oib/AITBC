"""
Metrics collection for AITBC Enterprise Connectors
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json

from .core import ConnectorConfig


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags or {}
        }


class MetricsCollector:
    """Collects and manages metrics for connectors"""
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Metric storage
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._timers: Dict[str, List[float]] = defaultdict(list)
        
        # Runtime state
        self._running = False
        self._flush_task = None
        self._buffer: List[MetricPoint] = []
        self._buffer_size = 1000
        
        # Aggregated metrics
        self._request_count = 0
        self._error_count = 0
        self._total_duration = 0.0
        self._last_flush = None
    
    async def start(self):
        """Start metrics collection"""
        if self._running:
            return
        
        self._running = True
        self._last_flush = datetime.utcnow()
        
        # Start periodic flush task
        if self.config.metrics_endpoint:
            self._flush_task = asyncio.create_task(self._flush_loop())
        
        self.logger.info("Metrics collection started")
    
    async def stop(self):
        """Stop metrics collection"""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Final flush
        await self._flush_metrics()
        
        self.logger.info("Metrics collection stopped")
    
    def increment(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        """Increment counter metric"""
        key = self._make_key(name, tags)
        self._counters[key] += value
        
        # Add to buffer
        self._add_to_buffer(name, value, tags)
    
    def gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Set gauge metric"""
        key = self._make_key(name, tags)
        self._gauges[key] = value
        
        # Add to buffer
        self._add_to_buffer(name, value, tags)
    
    def histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Add value to histogram"""
        key = self._make_key(name, tags)
        self._histograms[key].append(value)
        
        # Add to buffer
        self._add_to_buffer(name, value, tags)
    
    def timer(self, name: str, duration: float, tags: Dict[str, str] = None):
        """Record timing metric"""
        key = self._make_key(name, tags)
        self._timers[key].append(duration)
        
        # Keep only last 1000 timings
        if len(self._timers[key]) > 1000:
            self._timers[key] = self._timers[key][-1000:]
        
        # Add to buffer
        self._add_to_buffer(f"{name}_duration", duration, tags)
    
    async def record_request(
        self,
        method: str,
        path: str,
        status: int,
        duration: float
    ):
        """Record request metrics"""
        # Update aggregated metrics
        self._request_count += 1
        self._total_duration += duration
        
        if status >= 400:
            self._error_count += 1
        
        # Record detailed metrics
        tags = {
            "method": method,
            "path": path,
            "status": str(status)
        }
        
        self.increment("requests_total", 1.0, tags)
        self.timer("request_duration", duration, tags)
        
        if status >= 400:
            self.increment("errors_total", 1.0, tags)
    
    def get_metric(self, name: str, tags: Dict[str, str] = None) -> Optional[float]:
        """Get current metric value"""
        key = self._make_key(name, tags)
        
        if key in self._counters:
            return self._counters[key]
        elif key in self._gauges:
            return self._gauges[key]
        elif key in self._histograms:
            values = list(self._histograms[key])
            return sum(values) / len(values) if values else 0
        elif key in self._timers:
            values = self._timers[key]
            return sum(values) / len(values) if values else 0
        
        return None
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        return {
            "requests_total": self._request_count,
            "errors_total": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "avg_duration": self._total_duration / max(self._request_count, 1),
            "last_flush": self._last_flush.isoformat() if self._last_flush else None,
            "metrics_count": len(self._counters) + len(self._gauges) + len(self._histograms) + len(self._timers)
        }
    
    def _make_key(self, name: str, tags: Dict[str, str] = None) -> str:
        """Create metric key with tags"""
        if not tags:
            return name
        
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"
    
    def _add_to_buffer(self, name: str, value: float, tags: Dict[str, str] = None):
        """Add metric point to buffer"""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags
        )
        
        self._buffer.append(point)
        
        # Flush if buffer is full
        if len(self._buffer) >= self._buffer_size:
            asyncio.create_task(self._flush_metrics())
    
    async def _flush_loop(self):
        """Periodic flush loop"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Flush every minute
                await self._flush_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Flush loop error: {e}")
    
    async def _flush_metrics(self):
        """Flush metrics to endpoint"""
        if not self.config.metrics_endpoint or not self._buffer:
            return
        
        try:
            import aiohttp
            
            # Prepare metrics payload
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "source": "aitbc-enterprise-sdk",
                "metrics": [asdict(point) for point in self._buffer]
            }
            
            # Send to endpoint
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.metrics_endpoint,
                    json=payload,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        self._buffer.clear()
                        self._last_flush = datetime.utcnow()
                        self.logger.debug(f"Flushed {len(payload['metrics'])} metrics")
                    else:
                        self.logger.error(f"Failed to flush metrics: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Error flushing metrics: {e}")


class PerformanceTracker:
    """Track performance metrics for operations"""
    
    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics
        self._operations: Dict[str, float] = {}
    
    def start_operation(self, operation: str):
        """Start timing an operation"""
        self._operations[operation] = time.time()
    
    def end_operation(self, operation: str, tags: Dict[str, str] = None):
        """End timing an operation"""
        if operation in self._operations:
            duration = time.time() - self._operations[operation]
            del self._operations[operation]
            
            self.metrics.timer(f"operation_{operation}", duration, tags)
            
            return duration
        return None
    
    async def track_operation(self, operation: str, coro, tags: Dict[str, str] = None):
        """Context manager for tracking operations"""
        start = time.time()
        try:
            result = await coro
            success = True
            return result
        except Exception as e:
            success = False
            raise
        finally:
            duration = time.time() - start
            
            metric_tags = {
                "operation": operation,
                "success": str(success),
                **(tags or {})
            }
            
            self.metrics.timer(f"operation_{operation}", duration, metric_tags)
            self.metrics.increment(f"operations_total", 1.0, metric_tags)
