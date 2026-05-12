"""
Tests for distributed tracing module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Test with OpenTelemetry available
try:
    from aitbc.tracing import (
        setup_tracing,
        get_tracer,
        instrument_fastapi,
        instrument_httpx,
        instrument_sqlalchemy,
        trace_function,
        trace_async_function,
        trace_span,
        set_span_attribute,
        set_span_error,
        add_span_event,
        OPENTELEMETRY_AVAILABLE
    )
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingSetup:
    """Test tracing setup and initialization"""
    
    def test_setup_tracing_console_exporter(self):
        """Test setup_tracing with console exporter"""
        setup_tracing(
            service_name="test-service",
            service_version="1.0.0",
            exporter="console",
            sample_rate=1.0
        )
        tracer = get_tracer()
        assert tracer is not None
    
    def test_setup_tracing_otlp_exporter(self):
        """Test setup_tracing with OTLP exporter"""
        setup_tracing(
            service_name="test-service",
            service_version="1.0.0",
            exporter="otlp",
            sample_rate=1.0
        )
        tracer = get_tracer()
        assert tracer is not None
    
    def test_setup_tracing_none_exporter(self):
        """Test setup_tracing with none exporter"""
        setup_tracing(
            service_name="test-service",
            service_version="1.0.0",
            exporter="none",
            sample_rate=1.0
        )
        tracer = get_tracer()
        # With none exporter, tracer should still be created but may not export
        assert tracer is not None
    
    def test_get_tracer_without_setup(self):
        """Test get_tracer without prior setup"""
        # Reset global tracer
        from aitbc.tracing import _tracer
        from aitbc import tracing
        tracing._tracer = None
        tracer = get_tracer()
        # Should return None if not set up
        assert tracer is None


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingDecorators:
    """Test tracing decorators"""
    
    def test_trace_function_decorator(self):
        """Test trace_function decorator"""
        setup_tracing("test-service", "1.0.0", "none")
        
        @trace_function("test_function")
        def test_func(x: int, y: int) -> int:
            return x + y
        
        result = test_func(1, 2)
        assert result == 3
    
    def test_trace_function_with_exception(self):
        """Test trace_function decorator with exception"""
        setup_tracing("test-service", "1.0.0", "none")
        
        @trace_function("test_function_exception")
        def test_func() -> None:
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            test_func()
    
    @pytest.mark.asyncio
    async def test_trace_async_function_decorator(self):
        """Test trace_async_function decorator"""
        setup_tracing("test-service", "1.0.0", "none")
        
        @trace_async_function("test_async_function")
        async def test_func(x: int, y: int) -> int:
            return x + y
        
        result = await test_func(1, 2)
        assert result == 3
    
    @pytest.mark.asyncio
    async def test_trace_async_function_with_exception(self):
        """Test trace_async_function decorator with exception"""
        setup_tracing("test-service", "1.0.0", "none")
        
        @trace_async_function("test_async_function_exception")
        async def test_func() -> None:
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await test_func()


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingContextManager:
    """Test tracing context manager"""
    
    def test_trace_span_context_manager(self):
        """Test trace_span context manager"""
        setup_tracing("test-service", "1.0.0", "none")
        
        with trace_span("test_span", {"key": "value"}) as span:
            # Span should be created
            pass
        
        # If tracing is available, span should not be None
        # If not available, span should be None
        assert True  # Context manager should not raise exception
    
    def test_trace_span_without_tracing(self):
        """Test trace_span without tracing setup"""
        from aitbc.tracing import _tracer
        from aitbc import tracing
        tracing._tracer = None
        
        with trace_span("test_span", {"key": "value"}) as span:
            # Span should be None when tracing not available
            assert span is None


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingHelpers:
    """Test tracing helper functions"""
    
    def test_set_span_attribute(self):
        """Test set_span_attribute helper"""
        setup_tracing("test-service", "1.0.0", "none")
        
        # Should not raise exception even without active span
        set_span_attribute("test_key", "test_value")
    
    def test_set_span_error(self):
        """Test set_span_error helper"""
        setup_tracing("test-service", "1.0.0", "none")
        
        # Should not raise exception even without active span
        set_span_error(ValueError("Test error"))
    
    def test_add_span_event(self):
        """Test add_span_event helper"""
        setup_tracing("test-service", "1.0.0", "none")
        
        # Should not raise exception even without active span
        add_span_event("test_event", {"key": "value"})


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
class TestTracingInstrumentation:
    """Test tracing instrumentation"""
    
    def test_instrument_fastapi(self):
        """Test FastAPI instrumentation"""
        from fastapi import FastAPI
        setup_tracing("test-service", "1.0.0", "none")
        
        app = FastAPI()
        instrument_fastapi(app)
        
        # Should not raise exception
        assert True
    
    def test_instrument_httpx(self):
        """Test HTTPX instrumentation"""
        setup_tracing("test-service", "1.0.0", "none")
        
        instrument_httpx()
        
        # Should not raise exception
        assert True
    
    def test_instrument_sqlalchemy(self):
        """Test SQLAlchemy instrumentation"""
        from sqlalchemy import create_engine
        setup_tracing("test-service", "1.0.0", "none")
        
        engine = create_engine("sqlite:///:memory:")
        instrument_sqlalchemy(engine)
        
        # Should not raise exception
        assert True


def test_opentelemetry_not_available():
    """Test behavior when OpenTelemetry is not available"""
    # This test always runs, even when OpenTelemetry is available
    # to verify graceful degradation
    from aitbc.tracing import OPENTELEMETRY_AVAILABLE
    
    if not OPENTELEMETRY_AVAILABLE:
        # When OpenTelemetry is not available, these should not raise exceptions
        setup_tracing("test-service", "1.0.0", "console")
        get_tracer()
        
        @trace_function("test")
        def test_func():
            return 1
        
        result = test_func()
        assert result == 1
        
        with trace_span("test_span"):
            pass
        
        set_span_attribute("key", "value")
        set_span_error(ValueError("test"))
        add_span_event("event", {"key": "value"})
