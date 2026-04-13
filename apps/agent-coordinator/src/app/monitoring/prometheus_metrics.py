"""
Prometheus Metrics Implementation for AITBC Agent Coordinator
Implements comprehensive metrics collection and monitoring
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
import logging
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)

@dataclass
class MetricValue:
    """Represents a metric value with timestamp"""
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)

class Counter:
    """Prometheus-style counter metric"""
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.values: Dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()
    
    def inc(self, value: float = 1.0, **label_values: str) -> None:
        """Increment counter by value"""
        with self.lock:
            key = self._make_key(label_values)
            self.values[key] += value
    
    def get_value(self, **label_values: str) -> float:
        """Get current counter value"""
        with self.lock:
            key = self._make_key(label_values)
            return self.values.get(key, 0.0)
    
    def get_all_values(self) -> Dict[str, float]:
        """Get all counter values"""
        with self.lock:
            return dict(self.values)
    
    def reset(self, **label_values):
        """Reset counter value"""
        with self.lock:
            key = self._make_key(label_values)
            if key in self.values:
                del self.values[key]
    
    def reset_all(self):
        """Reset all counter values"""
        with self.lock:
            self.values.clear()
    
    def _make_key(self, label_values: Dict[str, str]) -> str:
        """Create key from label values"""
        if not self.labels:
            return "_default"
        
        key_parts = []
        for label in self.labels:
            value = label_values.get(label, "")
            key_parts.append(f"{label}={value}")
        
        return ",".join(key_parts)

class Gauge:
    """Prometheus-style gauge metric"""
    
    def __init__(self, name: str, description: str, labels: Optional[List[str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.values: Dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()
    
    def set(self, value: float, **label_values: str) -> None:
        """Set gauge value"""
        with self.lock:
            key = self._make_key(label_values)
            self.values[key] = value
    
    def inc(self, value: float = 1.0, **label_values):
        """Increment gauge by value"""
        with self.lock:
            key = self._make_key(label_values)
            self.values[key] += value
    
    def dec(self, value: float = 1.0, **label_values):
        """Decrement gauge by value"""
        with self.lock:
            key = self._make_key(label_values)
            self.values[key] -= value
    
    def get_value(self, **label_values) -> float:
        """Get current gauge value"""
        with self.lock:
            key = self._make_key(label_values)
            return self.values.get(key, 0.0)
    
    def get_all_values(self) -> Dict[str, float]:
        """Get all gauge values"""
        with self.lock:
            return dict(self.values)
    
    def _make_key(self, label_values: Dict[str, str]) -> str:
        """Create key from label values"""
        if not self.labels:
            return "_default"
        
        key_parts = []
        for label in self.labels:
            value = label_values.get(label, "")
            key_parts.append(f"{label}={value}")
        
        return ",".join(key_parts)

class Histogram:
    """Prometheus-style histogram metric"""
    
    def __init__(self, name: str, description: str, buckets: List[float] = None, labels: List[str] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.labels = labels or []
        self.values = defaultdict(lambda: defaultdict(int))  # {key: {bucket: count}}
        self.counts = defaultdict(int)  # {key: total_count}
        self.sums = defaultdict(float)  # {key: total_sum}
        self.lock = threading.Lock()
    
    def observe(self, value: float, **label_values):
        """Observe a value"""
        with self.lock:
            key = self._make_key(label_values)
            
            # Increment total count and sum
            self.counts[key] += 1
            self.sums[key] += value
            
            # Find appropriate bucket
            for bucket in self.buckets:
                if value <= bucket:
                    self.values[key][bucket] += 1
            
            # Always increment infinity bucket
            self.values[key]["inf"] += 1
    
    def get_bucket_counts(self, **label_values) -> Dict[str, int]:
        """Get bucket counts for labels"""
        with self.lock:
            key = self._make_key(label_values)
            return dict(self.values.get(key, {}))
    
    def get_count(self, **label_values) -> int:
        """Get total count for labels"""
        with self.lock:
            key = self._make_key(label_values)
            return self.counts.get(key, 0)
    
    def get_sum(self, **label_values) -> float:
        """Get sum of values for labels"""
        with self.lock:
            key = self._make_key(label_values)
            return self.sums.get(key, 0.0)
    
    def _make_key(self, label_values: Dict[str, str]) -> str:
        """Create key from label values"""
        if not self.labels:
            return "_default"
        
        key_parts = []
        for label in self.labels:
            value = label_values.get(label, "")
            key_parts.append(f"{label}={value}")
        
        return ",".join(key_parts)

class MetricsRegistry:
    """Central metrics registry"""
    
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
        self.lock = threading.Lock()
    
    def counter(self, name: str, description: str, labels: List[str] = None) -> Counter:
        """Create or get counter"""
        with self.lock:
            if name not in self.counters:
                self.counters[name] = Counter(name, description, labels)
            return self.counters[name]
    
    def gauge(self, name: str, description: str, labels: List[str] = None) -> Gauge:
        """Create or get gauge"""
        with self.lock:
            if name not in self.gauges:
                self.gauges[name] = Gauge(name, description, labels)
            return self.gauges[name]
    
    def histogram(self, name: str, description: str, buckets: List[float] = None, labels: List[str] = None) -> Histogram:
        """Create or get histogram"""
        with self.lock:
            if name not in self.histograms:
                self.histograms[name] = Histogram(name, description, buckets, labels)
            return self.histograms[name]
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics in Prometheus format"""
        with self.lock:
            metrics = {}
            
            # Add counters
            for name, counter in self.counters.items():
                metrics[name] = {
                    "type": "counter",
                    "description": counter.description,
                    "values": counter.get_all_values()
                }
            
            # Add gauges
            for name, gauge in self.gauges.items():
                metrics[name] = {
                    "type": "gauge",
                    "description": gauge.description,
                    "values": gauge.get_all_values()
                }
            
            # Add histograms
            for name, histogram in self.histograms.items():
                metrics[name] = {
                    "type": "histogram",
                    "description": histogram.description,
                    "buckets": histogram.buckets,
                    "counts": dict(histogram.counts),
                    "sums": dict(histogram.sums)
                }
            
            return metrics
    
    def reset_all(self):
        """Reset all metrics"""
        with self.lock:
            for counter in self.counters.values():
                counter.reset_all()
            
            for gauge in self.gauges.values():
                gauge.values.clear()
            
            for histogram in self.histograms.values():
                histogram.values.clear()
                histogram.counts.clear()
                histogram.sums.clear()

class PerformanceMonitor:
    """Performance monitoring and metrics collection"""
    
    def __init__(self, registry: MetricsRegistry):
        self.registry = registry
        self.start_time = time.time()
        self.request_times = deque(maxlen=1000)
        self.error_counts = defaultdict(int)
        
        # Initialize metrics
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize all performance metrics"""
        # Request metrics
        self.registry.counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
        self.registry.histogram("http_request_duration_seconds", "HTTP request duration", [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0], ["method", "endpoint"])
        
        # Agent metrics
        self.registry.gauge("agents_total", "Total number of agents", ["status"])
        self.registry.counter("agent_registrations_total", "Total agent registrations")
        self.registry.counter("agent_unregistrations_total", "Total agent unregistrations")
        
        # Task metrics
        self.registry.gauge("tasks_active", "Number of active tasks")
        self.registry.counter("tasks_submitted_total", "Total tasks submitted")
        self.registry.counter("tasks_completed_total", "Total tasks completed")
        self.registry.histogram("task_duration_seconds", "Task execution duration", [1.0, 5.0, 10.0, 30.0, 60.0, 300.0], ["task_type"])
        
        # AI/ML metrics
        self.registry.counter("ai_operations_total", "Total AI operations", ["operation_type", "status"])
        self.registry.gauge("ai_models_total", "Total AI models", ["model_type"])
        self.registry.histogram("ai_prediction_duration_seconds", "AI prediction duration", [0.1, 0.5, 1.0, 2.0, 5.0])
        
        # Consensus metrics
        self.registry.gauge("consensus_nodes_total", "Total consensus nodes", ["status"])
        self.registry.counter("consensus_proposals_total", "Total consensus proposals", ["status"])
        self.registry.histogram("consensus_duration_seconds", "Consensus decision duration", [1.0, 5.0, 10.0, 30.0])
        
        # System metrics
        self.registry.gauge("system_memory_usage_bytes", "Memory usage in bytes")
        self.registry.gauge("system_cpu_usage_percent", "CPU usage percentage")
        self.registry.gauge("system_uptime_seconds", "System uptime in seconds")
        
        # Load balancer metrics
        self.registry.gauge("load_balancer_strategy", "Current load balancing strategy", ["strategy"])
        self.registry.counter("load_balancer_assignments_total", "Total load balancer assignments", ["strategy"])
        self.registry.histogram("load_balancer_decision_time_seconds", "Load balancer decision time", [0.001, 0.005, 0.01, 0.025, 0.05])
        
        # Communication metrics
        self.registry.counter("messages_sent_total", "Total messages sent", ["message_type", "status"])
        self.registry.histogram("message_size_bytes", "Message size in bytes", [100, 1000, 10000, 100000])
        self.registry.gauge("active_connections", "Number of active connections")
        
        # Initialize counters and gauges to zero
        self.registry.gauge("agents_total", "Total number of agents", ["status"]).set(0, status="total")
        self.registry.gauge("agents_total", "Total number of agents", ["status"]).set(0, status="active")
        self.registry.gauge("tasks_active", "Number of active tasks").set(0)
        self.registry.gauge("system_uptime_seconds", "System uptime in seconds").set(0)
        self.registry.gauge("active_connections", "Number of active connections").set(0)
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics"""
        self.registry.counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]).inc(
            method=method,
            endpoint=endpoint,
            status=str(status_code)
        )
        
        self.registry.histogram("http_request_duration_seconds", "HTTP request duration", [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0], ["method", "endpoint"]).observe(
            duration,
            method=method,
            endpoint=endpoint
        )
        
        self.request_times.append(duration)
        
        if status_code >= 400:
            self.error_counts[f"{method}_{endpoint}"] += 1
    
    def record_agent_registration(self):
        """Record agent registration"""
        self.registry.counter("agent_registrations_total").inc()
    
    def record_agent_unregistration(self):
        """Record agent unregistration"""
        self.registry.counter("agent_unregistrations_total").inc()
    
    def update_agent_count(self, total: int, active: int, inactive: int):
        """Update agent counts"""
        self.registry.gauge("agents_total").set(total, status="total")
        self.registry.gauge("agents_total").set(active, status="active")
        self.registry.gauge("agents_total").set(inactive, status="inactive")
    
    def record_task_submission(self):
        """Record task submission"""
        self.registry.counter("tasks_submitted_total").inc()
        self.registry.gauge("tasks_active").inc()
    
    def record_task_completion(self, task_type: str, duration: float):
        """Record task completion"""
        self.registry.counter("tasks_completed_total").inc()
        self.registry.gauge("tasks_active").dec()
        self.registry.histogram("task_duration_seconds").observe(duration, task_type=task_type)
    
    def record_ai_operation(self, operation_type: str, status: str, duration: float = None):
        """Record AI operation"""
        self.registry.counter("ai_operations_total").inc(
            operation_type=operation_type,
            status=status
        )
        
        if duration is not None:
            self.registry.histogram("ai_prediction_duration_seconds").observe(duration)
    
    def update_ai_model_count(self, model_type: str, count: int):
        """Update AI model count"""
        self.registry.gauge("ai_models_total").set(count, model_type=model_type)
    
    def record_consensus_proposal(self, status: str, duration: float = None):
        """Record consensus proposal"""
        self.registry.counter("consensus_proposals_total").inc(status=status)
        
        if duration is not None:
            self.registry.histogram("consensus_duration_seconds").observe(duration)
    
    def update_consensus_node_count(self, total: int, active: int):
        """Update consensus node counts"""
        self.registry.gauge("consensus_nodes_total").set(total, status="total")
        self.registry.gauge("consensus_nodes_total").set(active, status="active")
    
    def update_system_metrics(self, memory_bytes: int, cpu_percent: float):
        """Update system metrics"""
        self.registry.gauge("system_memory_usage_bytes", "Memory usage in bytes").set(memory_bytes)
        self.registry.gauge("system_cpu_usage_percent", "CPU usage percentage").set(cpu_percent)
        self.registry.gauge("system_uptime_seconds", "System uptime in seconds").set(time.time() - self.start_time)
    
    def update_load_balancer_strategy(self, strategy: str):
        """Update load balancer strategy"""
        # Reset all strategy gauges
        for s in ["round_robin", "least_connections", "weighted", "random"]:
            self.registry.gauge("load_balancer_strategy").set(0, strategy=s)
        
        # Set current strategy
        self.registry.gauge("load_balancer_strategy").set(1, strategy=strategy)
    
    def record_load_balancer_assignment(self, strategy: str, decision_time: float):
        """Record load balancer assignment"""
        self.registry.counter("load_balancer_assignments_total").inc(strategy=strategy)
        self.registry.histogram("load_balancer_decision_time_seconds").observe(decision_time)
    
    def record_message_sent(self, message_type: str, status: str, size: int):
        """Record message sent"""
        self.registry.counter("messages_sent_total").inc(
            message_type=message_type,
            status=status
        )
        self.registry.histogram("message_size_bytes").observe(size)
    
    def update_active_connections(self, count: int):
        """Update active connections count"""
        self.registry.gauge("active_connections").set(count)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        if not self.request_times:
            return {
                "avg_response_time": 0,
                "p95_response_time": 0,
                "p99_response_time": 0,
                "error_rate": 0,
                "total_requests": 0,
                "uptime_seconds": time.time() - self.start_time
            }
        
        sorted_times = sorted(self.request_times)
        total_requests = len(self.request_times)
        total_errors = sum(self.error_counts.values())
        
        return {
            "avg_response_time": sum(sorted_times) / len(sorted_times),
            "p95_response_time": sorted_times[int(len(sorted_times) * 0.95)],
            "p99_response_time": sorted_times[int(len(sorted_times) * 0.99)],
            "error_rate": total_errors / total_requests if total_requests > 0 else 0,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "uptime_seconds": time.time() - self.start_time
        }

# Global instances
metrics_registry = MetricsRegistry()
performance_monitor = PerformanceMonitor(metrics_registry)
