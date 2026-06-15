"""
Distributed tracing utilities for AITBC
Provides OpenTelemetry integration for distributed tracing
"""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)
try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    logger.warning("OpenTelemetry not available, tracing will be disabled")


@dataclass
class SpanContext:
    """Span context for distributed tracing"""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None


class TracingManager:
    """
    Distributed tracing manager using OpenTelemetry.
    Provides distributed tracing capabilities across services.
    """

    def __init__(self, service_name: str, jaeger_host: str = "localhost", jaeger_port: int = 6831, enabled: bool = True):
        """
        Initialize tracing manager

        Args:
            service_name: Name of the service
            jaeger_host: Jaeger agent host
            jaeger_port: Jaeger agent port
            enabled: Whether tracing is enabled
        """
        self.service_name = service_name
        self.jaeger_host = jaeger_host
        self.jaeger_port = jaeger_port
        self.enabled = enabled and OPENTELEMETRY_AVAILABLE
        self._tracer = None
        self._provider = None
        if self.enabled:
            self._initialize_tracing()

    def _initialize_tracing(self) -> None:
        """Initialize OpenTelemetry tracing"""
        try:
            resource = Resource.create(
                {"service.name": self.service_name, "service.version": "1.0.0", "deployment.environment": "production"}
            )
            self._provider = TracerProvider(resource=resource)
            jaeger_exporter = JaegerExporter(agent_host_name=self.jaeger_host, agent_port=self.jaeger_port)
            self._provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            trace.set_tracer_provider(self._provider)
            self._tracer = trace.get_tracer(__name__)
            try:
                HTTPXClientInstrumentor().instrument()
                logger.info("Instrumented HTTPX client for tracing")
            except Exception as e:
                logger.warning("Failed to instrument HTTPX: %s", e)
            try:
                SQLAlchemyInstrumentor().instrument()
                logger.info("Instrumented SQLAlchemy for tracing")
            except Exception as e:
                logger.warning("Failed to instrument SQLAlchemy: %s", e)
            logger.info("OpenTelemetry tracing initialized for %s", self.service_name)
        except Exception as e:
            logger.error("Failed to initialize OpenTelemetry: %s", e)
            self.enabled = False

    def get_tracer(self):
        """
        Get OpenTelemetry tracer

        Returns:
            Tracer instance or None if not enabled
        """
        return self._tracer if self.enabled else None

    def start_span(self, name: str, attributes: dict[str, Any] | None = None):
        """
        Start a new span

        Args:
            name: Span name
            attributes: Span attributes

        Returns:
            Span context or None if not enabled
        """
        if not self.enabled or not self._tracer:
            return None
        span = self._tracer.start_span(name, attributes=attributes or {})
        return span

    def end_span(self, span) -> None:
        """
        End a span

        Args:
            span: Span to end
        """
        if span:
            span.end()

    @contextmanager
    def trace(self, name: str, attributes: dict[str, Any] | None = None):
        """
        Context manager for tracing code blocks

        Args:
            name: Span name
            attributes: Span attributes

        Yields:
            Span or None
        """
        span = self.start_span(name, attributes)
        try:
            yield span
        finally:
            self.end_span(span)

    def shutdown(self) -> None:
        """Shutdown tracing provider"""
        if self._provider:
            self._provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown")


def traced(name: str | None = None, attributes: dict[str, Any] | None = None):
    """
    Decorator to trace function execution

    Args:
        name: Span name (uses function name if None)
        attributes: Span attributes

    Returns:
        Decorated function with tracing
    """

    def decorator(func: Callable) -> Callable:

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not OPENTELEMETRY_AVAILABLE:
                return func(*args, **kwargs)
            tracer = trace.get_tracer(__name__)
            span_name = name or f"{func.__module__}.{func.__name__}"
            with tracer.start_as_current_span(span_name, attributes=attributes or {}):
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.record_exception(e)
                        current_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise

        return wrapper

    return decorator


class TraceContext:
    """
    Trace context for manual tracing.
    Provides methods for manual span creation and context propagation.
    """

    @staticmethod
    def get_current_span():
        """
        Get current span from context

        Returns:
            Current span or None
        """
        if not OPENTELEMETRY_AVAILABLE:
            return None
        return trace.get_current_span()

    @staticmethod
    def add_event(name: str, attributes: dict[str, Any] | None = None) -> None:
        """
        Add event to current span

        Args:
            name: Event name
            attributes: Event attributes
        """
        if not OPENTELEMETRY_AVAILABLE:
            return
        span = trace.get_current_span()
        if span:
            span.add_event(name, attributes=attributes or {})

    @staticmethod
    def set_attribute(key: str, value: Any) -> None:
        """
        Set attribute on current span

        Args:
            key: Attribute key
            value: Attribute value
        """
        if not OPENTELEMETRY_AVAILABLE:
            return
        span = trace.get_current_span()
        if span:
            span.set_attribute(key, value)

    @staticmethod
    def set_error(exception: Exception) -> None:
        """
        Set error on current span

        Args:
            exception: Exception to record
        """
        if not OPENTELEMETRY_AVAILABLE:
            return
        span = trace.get_current_span()
        if span:
            span.record_exception(exception)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


_global_tracing_manager: TracingManager | None = None


def initialize_tracing(
    service_name: str, jaeger_host: str = "localhost", jaeger_port: int = 6831, enabled: bool = True
) -> TracingManager:
    """
    Initialize global tracing manager

    Args:
        service_name: Name of the service
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
        enabled: Whether tracing is enabled

    Returns:
        TracingManager instance
    """
    global _global_tracing_manager
    _global_tracing_manager = TracingManager(service_name, jaeger_host, jaeger_port, enabled)
    return _global_tracing_manager


def get_tracing_manager() -> TracingManager | None:
    """
    Get global tracing manager instance

    Returns:
        TracingManager instance or None
    """
    return _global_tracing_manager


def shutdown_tracing() -> None:
    """Shutdown global tracing manager"""
    global _global_tracing_manager
    if _global_tracing_manager:
        _global_tracing_manager.shutdown()
        _global_tracing_manager = None
