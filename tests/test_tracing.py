"""Tests for aitbc.tracing (fallback paths without OpenTelemetry)"""

from unittest.mock import patch

from aitbc.tracing import (
    OPENTELEMETRY_AVAILABLE,
    get_tracer,
    instrument_fastapi,
    instrument_httpx,
    instrument_sqlalchemy,
    trace_function,
    trace_span,
)


class TestTracingFallbacks:
    def test_opentelemetry_not_available(self):
        assert OPENTELEMETRY_AVAILABLE is False

    def test_get_tracer_none(self):
        assert get_tracer() is None

    def test_setup_tracing_no_opentelemetry(self):
        from aitbc.tracing import setup_tracing

        setup_tracing("test-service")  # should not raise

    def test_instrument_fastapi_no_opentelemetry(self):
        instrument_fastapi(None)  # should not raise

    def test_instrument_httpx_no_opentelemetry(self):
        instrument_httpx()  # should not raise

    def test_instrument_sqlalchemy_no_opentelemetry(self):
        instrument_sqlalchemy(None)  # should not raise

    def test_trace_span_no_opentelemetry(self):
        with trace_span("test") as span:
            assert span is None

    def test_trace_function_no_opentelemetry(self):
        @trace_function()
        def my_func():
            return 42

        assert my_func() == 42

    def test_trace_function_with_name(self):
        @trace_function(name="custom_name")
        def my_func():
            return 42

        assert my_func() == 42


class TestTracingWithMockOpentelemetry:
    def test_trace_span_with_tracer(self):
        with patch("aitbc.tracing.OPENTELEMETRY_AVAILABLE", True):
            with patch("aitbc.tracing._tracer"):
                with trace_span("test") as span:
                    assert span is not None
