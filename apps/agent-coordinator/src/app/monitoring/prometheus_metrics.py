"""
Prometheus Metrics Implementation for AITBC Agent Coordinator
Implements comprehensive metrics collection and monitoring
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)

@dataclass
class MetricValue:
    """Represents a metric value with timestamp"""
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)

class Counter:
    """Prometheus-style counter metric"""

    def __init__(self, name: str, description: str, labels: list[str] | None = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.values: dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()

    def inc(self, value: float = 1.0, **label_values: str) -> None:
        """Increment counter by value"""
        with self.lock:
            key = self._make_key(**label_values)
            self.values[key] += value

    def get_value(self, **label_values: str) -> float:
        """Get current counter value"""
        with self.lock:
            key = self._make_key(**label_values)
            return self.values.get(key, 0.0)

    def get_all_values(self) -> dict[str, float]:
        """Get all counter values"""
        with self.lock:
            return dict(self.values)

    def reset(self, **label_values: str) -> None:
        """Reset counter value"""
        with self.lock:
            key = self._make_key(**label_values)
            if key in self.values:
                del self.values[key]

    def reset_all(self) -> None:
        """Reset all counter values"""
        with self.lock:
            self.values.clear()

    def _make_key(self, **label_values: str) -> str:
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

    def __init__(self, name: str, description: str, labels: list[str] | None = None):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.values: dict[str, float] = defaultdict(float)
        self.lock = threading.Lock()

    def set(self, value: float, **label_values: str) -> None:
        """Set gauge value"""
        with self.lock:
            key = self._make_key(**label_values)
            self.values[key] = value

    def inc(self, value: float = 1.0, **label_values: str) -> None:
        """Increment gauge by value"""
        with self.lock:
            key = self._make_key(**label_values)
            self.values[key] += value

    def dec(self, value: float = 1.0, **label_values: str) -> None:
        """Decrement gauge by value"""
        with self.lock:
            key = self._make_key(**label_values)
            self.values[key] -= value

    def get_value(self, **label_values: str) -> float:
        """Get current gauge value"""
        with self.lock:
            key = self._make_key(**label_values)
            return self.values.get(key, 0.0)

    def get_all_values(self) -> dict[str, float]:
        """Get all gauge values"""
        with self.lock:
            return dict(self.values)

    def reset_all(self) -> None:
        """Reset all gauge values"""
        with self.lock:
            self.values.clear()

    def _make_key(self, **label_values: str) -> str:
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

    def __init__(self, name: str, description: str, buckets: list[float] | None = None, labels: list[str] | None = None) -> None:
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.labels = labels or []
        self.values: defaultdict[str, defaultdict[float | str, int]] = defaultdict(lambda: defaultdict(int))  # {key: {bucket: count}}
        self.counts: defaultdict[str, int] = defaultdict(int)  # {key: total_count}
        self.sums: defaultdict[str, float] = defaultdict(float)  # {key: total_sum}
        self.lock = threading.Lock()

    def observe(self, value: float, **label_values: str) -> None:
        """Observe a value"""
        with self.lock:
            key = self._make_key(**label_values)

            # Increment total count and sum
            self.counts[key] += 1
            self.sums[key] += value

            # Find appropriate bucket
            for bucket in self.buckets:
                if value <= bucket:
                    self.values[key][str(bucket)] += 1

            # Always increment infinity bucket
            self.values[key]["inf"] += 1

    def get_bucket_counts(self, **label_values: str) -> dict[str, int]:
        """Get bucket counts for labels"""
        with self.lock:
            key = self._make_key(**label_values)
            bucket_data: defaultdict[float | str, int] = self.values.get(key, defaultdict(int))
            return {str(k): v for k, v in bucket_data.items()}

    def get_count(self, **label_values: str) -> int:
        """Get total count for labels"""
        with self.lock:
            key = self._make_key(**label_values)
            return self.counts.get(key, 0)

    def get_sum(self, **label_values: str) -> float:
        """Get sum of values for labels"""
        with self.lock:
            key = self._make_key(**label_values)
            return self.sums.get(key, 0.0)

    def _make_key(self, **label_values: str) -> str:
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

    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.gauges: dict[str, Gauge] = {}
        self.histograms: dict[str, Histogram] = {}
        self.lock = threading.Lock()

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Counter:
        """Create or get counter"""
        with self.lock:
            if name not in self.counters:
                self.counters[name] = Counter(name, description, labels)
            return self.counters[name]

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Gauge:
        """Create or get gauge"""
        with self.lock:
            if name not in self.gauges:
                self.gauges[name] = Gauge(name, description, labels)
            return self.gauges[name]

    def histogram(self, name: str, description: str, buckets: list[float] | None = None, labels: list[str] | None = None) -> Histogram:
        """Create or get histogram"""
        with self.lock:
            if name not in self.histograms:
                self.histograms[name] = Histogram(name, description, buckets, labels)
            return self.histograms[name]

    def get_all_metrics(self) -> dict[str, Any]:
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
                    "buckets": [str(b) for b in histogram.buckets],
                    "counts": dict(histogram.counts),
                    "sums": dict(histogram.sums)
                }

            return metrics

    def reset_all(self) -> None:
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

    def __init__(self, registry: MetricsRegistry) -> None:
        self.registry = registry
        self.start_time = time.time()
        self.request_times: deque[float] = deque(maxlen=1000)
        self.error_counts: defaultdict[str, int] = defaultdict(int)

        # Initialize metrics
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
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

    def record_request(self, method: str, endpoint: str, status_code: int, duration: float) -> None:
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

    def record_agent_registration(self) -> None:
        """Record agent registration"""
        self.registry.counter("agent_registrations_total", "Total agent registrations").inc()

    def record_agent_unregistration(self) -> None:
        """Record agent unregistration"""
        self.registry.counter("agent_unregistrations_total", "Total agent unregistrations").inc()

    def update_agent_count(self, total: int, active: int, inactive: int) -> None:
        """Update agent counts"""
        self.registry.gauge("agents_total", "Total number of agents", ["status"]).set(total, status="total")
        self.registry.gauge("agents_total", "Total number of agents", ["status"]).set(active, status="active")
        self.registry.gauge("agents_total", "Total number of agents", ["status"]).set(inactive, status="inactive")

    def record_task_submission(self) -> None:
        """Record task submission"""
        self.registry.counter("tasks_submitted_total", "Total tasks submitted").inc()
        self.registry.gauge("tasks_active", "Number of active tasks").inc()

    def record_task_completion(self, task_type: str, duration: float) -> None:
        """Record task completion"""
        self.registry.counter("tasks_completed_total", "Total tasks completed").inc()
        self.registry.gauge("tasks_active", "Number of active tasks").dec()
        self.registry.histogram("task_duration_seconds", "Task execution duration", [1.0, 5.0, 10.0, 30.0, 60.0, 300.0], ["task_type"]).observe(duration, task_type=task_type)

    def record_ai_operation(self, operation_type: str, status: str, duration: float | None = None) -> None:
        """Record AI operation"""
        self.registry.counter("ai_operations_total", "Total AI operations", ["operation_type", "status"]).inc(
            operation_type=operation_type,
            status=status
        )

        if duration is not None:
            self.registry.histogram("ai_prediction_duration_seconds", "AI prediction duration", [0.1, 0.5, 1.0, 2.0, 5.0]).observe(duration)

    def update_ai_model_count(self, model_type: str, count: int) -> None:
        """Update AI model count"""
        self.registry.gauge("ai_models_total", "Total AI models", ["model_type"]).set(count, model_type=model_type)

    def record_consensus_proposal(self, status: str, duration: float | None = None) -> None:
        """Record consensus proposal"""
        self.registry.counter("consensus_proposals_total", "Total consensus proposals", ["status"]).inc(status=status)

        if duration is not None:
            self.registry.histogram("consensus_duration_seconds", "Consensus decision duration", [1.0, 5.0, 10.0, 30.0]).observe(duration)

    def update_consensus_node_count(self, total: int, active: int) -> None:
        """Update consensus node counts"""
        self.registry.gauge("consensus_nodes_total", "Total consensus nodes", ["status"]).set(total, status="total")
        self.registry.gauge("consensus_nodes_total", "Total consensus nodes", ["status"]).set(active, status="active")

    def update_system_metrics(self, memory_bytes: int, cpu_percent: float) -> None:
        """Update system metrics"""
        self.registry.gauge("system_memory_usage_bytes", "Memory usage in bytes").set(memory_bytes)
        self.registry.gauge("system_cpu_usage_percent", "CPU usage percentage").set(cpu_percent)
        self.registry.gauge("system_uptime_seconds", "System uptime in seconds").set(time.time() - self.start_time)

    def update_load_balancer_strategy(self, strategy: str) -> None:
        """Update load balancer strategy"""
        # Reset all strategy gauges
        for s in ["round_robin", "least_connections", "weighted", "random"]:
            self.registry.gauge("load_balancer_strategy", "Current load balancing strategy", ["strategy"]).set(0, strategy=s)

        # Set current strategy
        self.registry.gauge("load_balancer_strategy", "Current load balancing strategy", ["strategy"]).set(1, strategy=strategy)

    def record_load_balancer_assignment(self, strategy: str, decision_time: float) -> None:
        """Record load balancer assignment"""
        self.registry.counter("load_balancer_assignments_total", "Total load balancer assignments", ["strategy"]).inc(strategy=strategy)
        self.registry.histogram("load_balancer_decision_time_seconds", "Load balancer decision time", [0.001, 0.005, 0.01, 0.025, 0.05]).observe(decision_time)

    def record_message_sent(self, message_type: str, status: str, size: int) -> None:
        """Record message sent"""
        self.registry.counter("messages_sent_total", "Total messages sent", ["message_type", "status"]).inc(
            message_type=message_type,
            status=status
        )
        self.registry.histogram("message_size_bytes", "Message size in bytes", [100, 1000, 10000, 100000]).observe(size)

    def update_active_connections(self, count: int) -> None:
        """Update active connections count"""
        self.registry.gauge("active_connections", "Number of active connections").set(count)

    def get_performance_summary(self) -> dict[str, Any]:
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
