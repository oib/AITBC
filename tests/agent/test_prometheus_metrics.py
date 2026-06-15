"""
Prometheus Metrics Module Tests
Tests for Counter, Gauge, Histogram, MetricsRegistry, and PerformanceMonitor
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest  # noqa: E402
from app.monitoring.prometheus_metrics import (  # noqa: E402
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    MetricValue,
    PerformanceMonitor,
    metrics_registry,
    performance_monitor,
)


class TestMetricValue:
    """Test MetricValue dataclass"""

    def test_metric_value_creation(self):
        """Test creating a metric value"""
        from datetime import datetime

        value = MetricValue(value=42.5, timestamp=datetime.now(), labels={"label1": "value1"})

        assert value.value == 42.5
        assert value.labels == {"label1": "value1"}

    def test_metric_value_default_labels(self):
        """Test metric value with default labels"""
        from datetime import datetime

        value = MetricValue(value=10.0, timestamp=datetime.now())

        assert value.labels == {}


class TestCounter:
    """Test Counter metric"""

    def test_counter_creation(self):
        """Test creating a counter"""
        counter = Counter("test_counter", "Test counter metric")

        assert counter.name == "test_counter"
        assert counter.description == "Test counter metric"
        assert counter.labels == []
        assert counter.get_value() == 0.0

    def test_counter_with_labels(self):
        """Test creating a counter with labels"""
        counter = Counter("test_counter", "Test counter", labels=["method", "endpoint"])

        assert counter.labels == ["method", "endpoint"]

    def test_counter_increment(self):
        """Test incrementing counter"""
        counter = Counter("test_counter", "Test counter")

        counter.inc()
        assert counter.get_value() == 1.0

        counter.inc(5.0)
        assert counter.get_value() == 6.0

    def test_counter_increment_with_labels(self):
        """Test incrementing counter with labels"""
        counter = Counter("test_counter", "Test counter", labels=["method"])

        counter.inc(method="GET")
        assert counter.get_value(method="GET") == 1.0

        counter.inc(2.0, method="POST")
        assert counter.get_value(method="POST") == 2.0

    def test_counter_get_all_values(self):
        """Test getting all counter values"""
        counter = Counter("test_counter", "Test counter", labels=["method"])

        counter.inc(method="GET")
        counter.inc(method="POST")

        values = counter.get_all_values()
        assert len(values) == 2
        assert "method=GET" in values
        assert "method=POST" in values

    def test_counter_reset(self):
        """Test resetting counter"""
        counter = Counter("test_counter", "Test counter", labels=["method"])

        counter.inc(method="GET")
        assert counter.get_value(method="GET") == 1.0

        counter.reset(method="GET")
        assert counter.get_value(method="GET") == 0.0

    def test_counter_reset_all(self):
        """Test resetting all counter values"""
        counter = Counter("test_counter", "Test counter", labels=["method"])

        counter.inc(method="GET")
        counter.inc(method="POST")

        counter.reset_all()
        assert len(counter.get_all_values()) == 0


class TestGauge:
    """Test Gauge metric"""

    def test_gauge_creation(self):
        """Test creating a gauge"""
        gauge = Gauge("test_gauge", "Test gauge metric")

        assert gauge.name == "test_gauge"
        assert gauge.description == "Test gauge metric"
        assert gauge.labels == []
        assert gauge.get_value() == 0.0

    def test_gauge_set(self):
        """Test setting gauge value"""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.set(42.0)
        assert gauge.get_value() == 42.0

        gauge.set(100.0)
        assert gauge.get_value() == 100.0

    def test_gauge_set_with_labels(self):
        """Test setting gauge with labels"""
        gauge = Gauge("test_gauge", "Test gauge", labels=["status"])

        gauge.set(5, status="active")
        assert gauge.get_value(status="active") == 5

    def test_gauge_increment(self):
        """Test incrementing gauge"""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.inc()
        assert gauge.get_value() == 1.0

        gauge.inc(5.0)
        assert gauge.get_value() == 6.0

    def test_gauge_decrement(self):
        """Test decrementing gauge"""
        gauge = Gauge("test_gauge", "Test gauge")

        gauge.set(10.0)
        gauge.dec()
        assert gauge.get_value() == 9.0

        gauge.dec(5.0)
        assert gauge.get_value() == 4.0

    def test_gauge_get_all_values(self):
        """Test getting all gauge values"""
        gauge = Gauge("test_gauge", "Test gauge", labels=["status"])

        gauge.set(5, status="active")
        gauge.set(10, status="inactive")

        values = gauge.get_all_values()
        assert len(values) == 2


class TestHistogram:
    """Test Histogram metric"""

    def test_histogram_creation(self):
        """Test creating a histogram"""
        histogram = Histogram("test_histogram", "Test histogram metric")

        assert histogram.name == "test_histogram"
        assert histogram.description == "Test histogram metric"
        assert len(histogram.buckets) > 0
        assert histogram.get_count() == 0

    def test_histogram_custom_buckets(self):
        """Test creating histogram with custom buckets"""
        custom_buckets = [0.1, 0.5, 1.0, 5.0]
        histogram = Histogram("test_histogram", "Test histogram", buckets=custom_buckets)

        assert histogram.buckets == custom_buckets

    def test_histogram_observe(self):
        """Test observing values"""
        histogram = Histogram("test_histogram", "Test histogram")

        histogram.observe(0.01)
        histogram.observe(0.5)
        histogram.observe(2.0)

        assert histogram.get_count() == 3
        assert histogram.get_sum() == 2.51

    def test_histogram_observe_with_labels(self):
        """Test observing values with labels"""
        histogram = Histogram("test_histogram", "Test histogram", labels=["operation"])

        histogram.observe(0.5, operation="read")
        histogram.observe(1.0, operation="write")

        assert histogram.get_count(operation="read") == 1
        assert histogram.get_count(operation="write") == 1

    def test_histogram_bucket_counts(self):
        """Test getting bucket counts"""
        histogram = Histogram("test_histogram", "Test histogram")

        histogram.observe(0.01)
        histogram.observe(0.5)
        histogram.observe(2.0)

        bucket_counts = histogram.get_bucket_counts()
        assert "0.01" in bucket_counts
        assert "0.5" in bucket_counts
        assert "inf" in bucket_counts

    def test_histogram_infinity_bucket(self):
        """Test that infinity bucket always increments"""
        histogram = Histogram("test_histogram", "Test histogram")

        histogram.observe(1000.0)

        bucket_counts = histogram.get_bucket_counts()
        assert bucket_counts["inf"] == 1


class TestMetricsRegistry:
    """Test MetricsRegistry"""

    def test_registry_creation(self):
        """Test creating a registry"""
        registry = MetricsRegistry()

        assert registry.counters == {}
        assert registry.gauges == {}
        assert registry.histograms == {}

    def test_registry_counter(self):
        """Test creating/getting counter from registry"""
        registry = MetricsRegistry()

        counter1 = registry.counter("test_counter", "Test counter")
        counter2 = registry.counter("test_counter", "Test counter")

        # Should return same instance
        assert counter1 is counter2
        assert "test_counter" in registry.counters

    def test_registry_gauge(self):
        """Test creating/getting gauge from registry"""
        registry = MetricsRegistry()

        gauge1 = registry.gauge("test_gauge", "Test gauge")
        gauge2 = registry.gauge("test_gauge", "Test gauge")

        # Should return same instance
        assert gauge1 is gauge2
        assert "test_gauge" in registry.gauges

    def test_registry_histogram(self):
        """Test creating/getting histogram from registry"""
        registry = MetricsRegistry()

        histogram1 = registry.histogram("test_histogram", "Test histogram")
        histogram2 = registry.histogram("test_histogram", "Test histogram")

        # Should return same instance
        assert histogram1 is histogram2
        assert "test_histogram" in registry.histograms

    def test_registry_get_all_metrics(self):
        """Test getting all metrics from registry"""
        registry = MetricsRegistry()

        registry.counter("test_counter", "Test counter")
        registry.gauge("test_gauge", "Test gauge")
        registry.histogram("test_histogram", "Test histogram")

        metrics = registry.get_all_metrics()

        assert "test_counter" in metrics
        assert "test_gauge" in metrics
        assert "test_histogram" in metrics
        assert metrics["test_counter"]["type"] == "counter"
        assert metrics["test_gauge"]["type"] == "gauge"
        assert metrics["test_histogram"]["type"] == "histogram"

    def test_registry_reset_all(self):
        """Test resetting all metrics in registry"""
        registry = MetricsRegistry()

        counter = registry.counter("test_counter", "Test counter")
        gauge = registry.gauge("test_gauge", "Test gauge")

        counter.inc()
        gauge.set(10.0)

        registry.reset_all()

        assert counter.get_value() == 0.0
        assert gauge.get_value() == 0.0


class TestPerformanceMonitor:
    """Test PerformanceMonitor"""

    def test_performance_monitor_creation(self):
        """Test creating performance monitor"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        assert monitor.registry is registry
        assert monitor.start_time > 0

    def test_performance_monitor_initializes_metrics(self):
        """Test that performance monitor initializes default metrics"""
        registry = MetricsRegistry()
        PerformanceMonitor(registry)

        metrics = registry.get_all_metrics()

        # Check that key metrics are initialized
        assert "http_requests_total" in metrics
        assert "http_request_duration_seconds" in metrics
        assert "agents_total" in metrics
        assert "tasks_active" in metrics

    def test_record_request(self):
        """Test recording HTTP request"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_request("GET", "/api/test", 200, 0.5)

        # Check counter incremented
        counter = registry.counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
        assert counter.get_value(method="GET", endpoint="/api/test", status="200") == 1

        # Check histogram observed
        histogram = registry.histogram("http_request_duration_seconds", "HTTP request duration")
        assert histogram.get_count(method="GET", endpoint="/api/test") == 1

    def test_record_agent_registration(self):
        """Test recording agent registration"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        # PerformanceMonitor initializes metrics in __init__
        monitor.record_agent_registration()

        # Verify the counter was incremented
        counter = registry.counter("agent_registrations_total", "Total agent registrations")
        assert counter.get_value() == 1

    def test_record_agent_unregistration(self):
        """Test recording agent unregistration"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_agent_unregistration()

        counter = registry.counter("agent_unregistrations_total", "Total agent unregistrations")
        assert counter.get_value() == 1

    def test_update_agent_count(self):
        """Test updating agent counts"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_agent_count(total=10, active=5, inactive=5)

        gauge = registry.gauge("agents_total", "Total number of agents", ["status"])
        assert gauge.get_value(status="total") == 10
        assert gauge.get_value(status="active") == 5
        assert gauge.get_value(status="inactive") == 5

    def test_record_task_submission(self):
        """Test recording task submission"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_task_submission()

        counter = registry.counter("tasks_submitted_total", "Total tasks submitted")
        assert counter.get_value() == 1

        gauge = registry.gauge("tasks_active", "Number of active tasks")
        assert gauge.get_value() == 1

    def test_record_task_completion(self):
        """Test recording task completion"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_task_completion("inference", 5.0)

        counter = registry.counter("tasks_completed_total", "Total tasks completed")
        assert counter.get_value() == 1

        gauge = registry.gauge("tasks_active", "Number of active tasks")
        assert gauge.get_value() == -1  # Decremented

        histogram = registry.histogram(
            "task_duration_seconds", "Task execution duration", [1.0, 5.0, 10.0, 30.0, 60.0, 300.0], ["task_type"]
        )
        assert histogram.get_count(task_type="inference") == 1

    def test_record_ai_operation(self):
        """Test recording AI operation"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_ai_operation("inference", "success", 1.5)

        counter = registry.counter("ai_operations_total", "Total AI operations", ["operation_type", "status"])
        assert counter.get_value(operation_type="inference", status="success") == 1

        histogram = registry.histogram("ai_prediction_duration_seconds", "AI prediction duration", [0.1, 0.5, 1.0, 2.0, 5.0])
        assert histogram.get_count() == 1

    def test_update_ai_model_count(self):
        """Test updating AI model count"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_ai_model_count("llm", 5)

        gauge = registry.gauge("ai_models_total", "Total AI models", ["model_type"])
        assert gauge.get_value(model_type="llm") == 5

    def test_record_consensus_proposal(self):
        """Test recording consensus proposal"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_consensus_proposal("accepted", 2.0)

        counter = registry.counter("consensus_proposals_total", "Total consensus proposals", ["status"])
        assert counter.get_value(status="accepted") == 1

        histogram = registry.histogram("consensus_duration_seconds", "Consensus decision duration", [1.0, 5.0, 10.0, 30.0])
        assert histogram.get_count() == 1

    def test_update_consensus_node_count(self):
        """Test updating consensus node counts"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_consensus_node_count(total=10, active=8)

        gauge = registry.gauge("consensus_nodes_total", "Total consensus nodes", ["status"])
        assert gauge.get_value(status="total") == 10
        assert gauge.get_value(status="active") == 8

    def test_update_system_metrics(self):
        """Test updating system metrics"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_system_metrics(memory_bytes=1024 * 1024 * 512, cpu_percent=50.0)

        gauge = registry.gauge("system_memory_usage_bytes", "Memory usage in bytes")
        assert gauge.get_value() == 1024 * 1024 * 512

        gauge = registry.gauge("system_cpu_usage_percent", "CPU usage percentage")
        assert gauge.get_value() == 50.0

    def test_update_load_balancer_strategy(self):
        """Test updating load balancer strategy"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_load_balancer_strategy("round_robin")

        gauge = registry.gauge("load_balancer_strategy", "Current load balancing strategy", ["strategy"])
        assert gauge.get_value(strategy="round_robin") == 1
        assert gauge.get_value(strategy="least_connections") == 0

    def test_record_load_balancer_assignment(self):
        """Test recording load balancer assignment"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_load_balancer_assignment("round_robin", 0.01)

        counter = registry.counter("load_balancer_assignments_total", "Total load balancer assignments", ["strategy"])
        assert counter.get_value(strategy="round_robin") == 1

        histogram = registry.histogram(
            "load_balancer_decision_time_seconds", "Load balancer decision time", [0.001, 0.005, 0.01, 0.025, 0.05]
        )
        assert histogram.get_count() == 1

    def test_record_message_sent(self):
        """Test recording message sent"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_message_sent("task", "success", 1024)

        counter = registry.counter("messages_sent_total", "Total messages sent", ["message_type", "status"])
        assert counter.get_value(message_type="task", status="success") == 1

        histogram = registry.histogram("message_size_bytes", "Message size in bytes", [100, 1000, 10000, 100000])
        assert histogram.get_count() == 1

    def test_update_active_connections(self):
        """Test updating active connections"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.update_active_connections(42)

        gauge = registry.gauge("active_connections", "Number of active connections")
        assert gauge.get_value() == 42

    def test_get_performance_summary_empty(self):
        """Test getting performance summary with no requests"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        summary = monitor.get_performance_summary()

        assert summary["avg_response_time"] == 0
        assert summary["p95_response_time"] == 0
        assert summary["p99_response_time"] == 0
        assert summary["error_rate"] == 0
        assert summary["total_requests"] == 0

    def test_get_performance_summary_with_data(self):
        """Test getting performance summary with request data"""
        registry = MetricsRegistry()
        monitor = PerformanceMonitor(registry)

        monitor.record_request("GET", "/api/test", 200, 0.1)
        monitor.record_request("GET", "/api/test", 200, 0.2)
        monitor.record_request("GET", "/api/test", 500, 0.3)

        summary = monitor.get_performance_summary()

        assert summary["total_requests"] == 3
        assert summary["total_errors"] == 1
        assert summary["error_rate"] == 1 / 3
        assert summary["avg_response_time"] > 0
        assert summary["uptime_seconds"] > 0


class TestGlobalInstances:
    """Test global metric instances"""

    def test_global_metrics_registry(self):
        """Test global metrics registry instance"""
        assert metrics_registry is not None
        assert isinstance(metrics_registry, MetricsRegistry)

    def test_global_performance_monitor(self):
        """Test global performance monitor instance"""
        assert performance_monitor is not None
        assert isinstance(performance_monitor, PerformanceMonitor)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
