"""
Tests for AITBC distributed tracing module (distributed_tracing.py)
This module has 0% coverage and 134 statements.
"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

distributed_tracing = load_module_from_path(
    "aitbc.distributed_tracing",
    Path("/opt/aitbc/aitbc/distributed_tracing.py")
)


# ============================================================================
# SpanContext Tests
# ============================================================================

class TestSpanContext:
    """Test SpanContext dataclass"""

    def test_span_context_initialization(self):
        context = distributed_tracing.SpanContext(
            trace_id="trace123",
            span_id="span456"
        )
        assert context.trace_id == "trace123"
        assert context.span_id == "span456"
        assert context.parent_span_id is None

    def test_span_context_with_parent(self):
        context = distributed_tracing.SpanContext(
            trace_id="trace123",
            span_id="span456",
            parent_span_id="parent789"
        )
        assert context.parent_span_id == "parent789"


# ============================================================================
# TracingManager Tests
# ============================================================================

class TestTracingManager:
    """Test TracingManager class"""

    def test_initialization_disabled_when_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.TracingManager(
                service_name="test-service",
                enabled=True
            )
            assert manager.enabled is False
            assert manager._tracer is None
            assert manager._provider is None

    def test_initialization_disabled_explicitly(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        assert manager.enabled is False
        assert manager._tracer is None

    def test_initialization_with_defaults(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.TracingManager(
                service_name="test-service"
            )
            assert manager.service_name == "test-service"
            assert manager.jaeger_host == "localhost"
            assert manager.jaeger_port == 6831

    def test_initialization_custom_jaeger(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.TracingManager(
                service_name="test-service",
                jaeger_host="jaeger.example.com",
                jaeger_port=6832
            )
            assert manager.jaeger_host == "jaeger.example.com"
            assert manager.jaeger_port == 6832

    def test_get_tracer_when_disabled(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        tracer = manager.get_tracer()
        assert tracer is None

    def test_start_span_when_disabled(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        span = manager.start_span("test-span")
        assert span is None

    def test_end_span_none(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        # Should not raise
        manager.end_span(None)

    def test_end_span_mock(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        mock_span = Mock()
        manager.end_span(mock_span)
        mock_span.end.assert_called_once()

    def test_trace_context_manager_disabled(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        with manager.trace("test-span") as span:
            assert span is None

    def test_shutdown_none_provider(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        # Should not raise
        manager.shutdown()

    def test_shutdown_with_provider(self):
        manager = distributed_tracing.TracingManager(
            service_name="test-service",
            enabled=False
        )
        manager._provider = Mock()
        manager.shutdown()
        manager._provider.shutdown.assert_called_once()


# ============================================================================
# Traced Decorator Tests
# ============================================================================

class TestTracedDecorator:
    """Test traced decorator"""

    def test_traced_decorator_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            @distributed_tracing.traced(name="test_function")
            def test_func(x, y):
                return x + y
            
            result = test_func(1, 2)
            assert result == 3

    def test_traced_decorator_without_name(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            @distributed_tracing.traced()
            def test_func(x, y):
                return x + y
            
            result = test_func(1, 2)
            assert result == 3

    def test_traced_decorator_with_attributes(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            @distributed_tracing.traced(attributes={"key": "value"})
            def test_func(x):
                return x
            
            result = test_func(42)
            assert result == 42

    def test_traced_decorator_exception_handling(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            @distributed_tracing.traced()
            def test_func():
                raise ValueError("Test error")
            
            with pytest.raises(ValueError, match="Test error"):
                test_func()


# ============================================================================
# TraceContext Tests
# ============================================================================

class TestTraceContext:
    """Test TraceContext class"""

    def test_get_current_span_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            span = distributed_tracing.TraceContext.get_current_span()
            assert span is None

    def test_add_event_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            # Should not raise
            distributed_tracing.TraceContext.add_event("test_event")

    def test_add_event_with_attributes_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            # Should not raise
            distributed_tracing.TraceContext.add_event("test_event", {"key": "value"})

    def test_set_attribute_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            # Should not raise
            distributed_tracing.TraceContext.set_attribute("key", "value")

    def test_set_error_opentelemetry_unavailable(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            # Should not raise
            distributed_tracing.TraceContext.set_error(ValueError("Test error"))


# ============================================================================
# Global Functions Tests
# ============================================================================

class TestGlobalFunctions:
    """Test global tracing functions"""

    def test_initialize_tracing(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.initialize_tracing(
                service_name="test-service",
                jaeger_host="localhost",
                jaeger_port=6831,
                enabled=True
            )
            assert manager is not None
            assert manager.service_name == "test-service"

    def test_initialize_tracing_custom_jaeger(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.initialize_tracing(
                service_name="test-service",
                jaeger_host="jaeger.example.com",
                jaeger_port=6832
            )
            assert manager.jaeger_host == "jaeger.example.com"
            assert manager.jaeger_port == 6832

    def test_get_tracing_manager_none(self):
        distributed_tracing._global_tracing_manager = None
        manager = distributed_tracing.get_tracing_manager()
        assert manager is None

    def test_get_tracing_manager_exists(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            distributed_tracing._global_tracing_manager = distributed_tracing.TracingManager(
                service_name="test-service"
            )
            manager = distributed_tracing.get_tracing_manager()
            assert manager is not None

    def test_shutdown_tracing_none(self):
        distributed_tracing._global_tracing_manager = None
        # Should not raise
        distributed_tracing.shutdown_tracing()

    def test_shutdown_tracing_with_manager(self):
        with patch.object(distributed_tracing, 'OPENTELEMETRY_AVAILABLE', False):
            manager = distributed_tracing.TracingManager(service_name="test-service")
            distributed_tracing._global_tracing_manager = manager
            distributed_tracing.shutdown_tracing()
            assert distributed_tracing._global_tracing_manager is None
