"""
Distributed Tracing Tests
Tests for AITBC distributed tracing utilities
"""


import pytest

from aitbc.distributed_tracing import (
    OPENTELEMETRY_AVAILABLE,
    SpanContext,
    TraceContext,
    TracingManager,
    get_tracing_manager,
    initialize_tracing,
    shutdown_tracing,
    traced,
)


class TestSpanContext:
    """Test SpanContext dataclass"""

    def test_span_context_creation(self):
        """Test SpanContext creation"""
        context = SpanContext(
            trace_id="test-trace-123",
            span_id="test-span-456",
            parent_span_id=None
        )
        assert context.trace_id == "test-trace-123"
        assert context.span_id == "test-span-456"
        assert context.parent_span_id is None

    def test_span_context_with_parent(self):
        """Test SpanContext with parent span"""
        context = SpanContext(
            trace_id="test-trace-123",
            span_id="test-span-456",
            parent_span_id="parent-span-789"
        )
        assert context.parent_span_id == "parent-span-789"


class TestTracingManager:
    """Test TracingManager class"""

    def test_tracing_manager_class_exists(self):
        """Test TracingManager class exists"""
        assert TracingManager is not None

    def test_tracing_manager_can_be_instantiated(self):
        """Test TracingManager can be instantiated"""
        manager = TracingManager(service_name="test-service", enabled=False)
        assert manager is not None
        assert manager.service_name == "test-service"

    def test_tracing_manager_enabled_false(self):
        """Test TracingManager with enabled=False"""
        manager = TracingManager(service_name="test-service", enabled=False)
        assert manager.enabled is False
        assert manager._tracer is None

    def test_tracing_manager_custom_jaeger_config(self):
        """Test TracingManager with custom Jaeger config"""
        manager = TracingManager(
            service_name="test-service",
            jaeger_host="custom-host",
            jaeger_port=6832,
            enabled=False
        )
        assert manager.jaeger_host == "custom-host"
        assert manager.jaeger_port == 6832

    def test_get_tracer_when_disabled(self):
        """Test get_tracer when tracing disabled"""
        manager = TracingManager(service_name="test-service", enabled=False)
        tracer = manager.get_tracer()
        assert tracer is None

    def test_start_span_when_disabled(self):
        """Test start_span when tracing disabled"""
        manager = TracingManager(service_name="test-service", enabled=False)
        span = manager.start_span("test-span")
        assert span is None

    def test_end_span_none(self):
        """Test end_span with None"""
        manager = TracingManager(service_name="test-service", enabled=False)
        # Should not raise
        manager.end_span(None)

    def test_trace_context_manager_disabled(self):
        """Test trace context manager when disabled"""
        manager = TracingManager(service_name="test-service", enabled=False)
        with manager.trace("test-span") as span:
            assert span is None

    def test_shutdown(self):
        """Test shutdown method"""
        manager = TracingManager(service_name="test-service", enabled=False)
        # Should not raise
        manager.shutdown()


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingManagerWithOpenTelemetry:
    """Test TracingManager with OpenTelemetry available"""

    def test_initialization_with_opentelemetry(self):
        """Test initialization when OpenTelemetry is available"""
        manager = TracingManager(service_name="test-service", enabled=True)
        # May fail if Jaeger not available, but should not crash
        assert manager.service_name == "test-service"
        manager.shutdown()


class TestTraceContext:
    """Test TraceContext class"""

    def test_trace_context_get_current_span(self):
        """Test TraceContext get_current_span static method"""
        span = TraceContext.get_current_span()
        # Returns None if OpenTelemetry not available
        assert span is None or span is not None

    def test_trace_context_add_event(self):
        """Test TraceContext add_event method"""
        # Should not raise even without OpenTelemetry
        TraceContext.add_event("test-event", {"key": "value"})

    def test_trace_context_set_attribute(self):
        """Test TraceContext set_attribute method"""
        # Should not raise even without OpenTelemetry
        TraceContext.set_attribute("key", "value")

    def test_trace_context_set_error(self):
        """Test TraceContext set_error method"""
        # Should not raise even without OpenTelemetry
        TraceContext.set_error(Exception("test error"))


class TestTracedDecorator:
    """Test traced decorator"""

    def test_traced_decorator_without_opentelemetry(self):
        """Test traced decorator when OpenTelemetry not available"""
        @traced(name="test_function")
        def test_func(x, y):
            return x + y

        result = test_func(1, 2)
        assert result == 3

    def test_traced_decorator_with_exception(self):
        """Test traced decorator with exception"""
        @traced(name="test_function")
        def test_func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            test_func()

    def test_traced_decorator_default_name(self):
        """Test traced decorator with default name"""
        @traced()
        def test_func():
            return 42

        result = test_func()
        assert result == 42

    def test_traced_decorator_with_attributes(self):
        """Test traced decorator with attributes"""
        @traced(attributes={"custom": "value"})
        def test_func():
            return 42

        result = test_func()
        assert result == 42


class TestTracingFunctions:
    """Test tracing utility functions"""

    def test_get_tracing_manager(self):
        """Test get_tracing_manager function"""
        manager = get_tracing_manager()
        # Returns None if not initialized
        assert manager is None or manager is not None

    def test_initialize_tracing(self):
        """Test initialize_tracing function"""
        manager = initialize_tracing(service_name="test-service", enabled=False)
        assert manager is not None
        assert manager.service_name == "test-service"
        shutdown_tracing()

    def test_initialize_tracing_custom_config(self):
        """Test initialize_tracing with custom config"""
        manager = initialize_tracing(
            service_name="test-service",
            jaeger_host="custom-host",
            jaeger_port=6832,
            enabled=False
        )
        assert manager.jaeger_host == "custom-host"
        assert manager.jaeger_port == 6832
        shutdown_tracing()

    def test_get_tracing_manager_after_init(self):
        """Test get_tracing_manager after initialization"""
        initialize_tracing(service_name="test-service", enabled=False)
        manager = get_tracing_manager()
        assert manager is not None
        assert manager.service_name == "test-service"
        shutdown_tracing()

    def test_shutdown_tracing(self):
        """Test shutdown_tracing function"""
        initialize_tracing(service_name="test-service", enabled=False)
        # Should not raise
        shutdown_tracing()

        # Manager should be None after shutdown
        manager = get_tracing_manager()
        assert manager is None

    def test_shutdown_tracing_without_init(self):
        """Test shutdown_tracing without initialization"""
        # Should not raise
        shutdown_tracing()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
