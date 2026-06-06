"""
AITBC Distributed Tracing Module
OpenTelemetry-based distributed tracing for AITBC applications
"""

import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# OpenTelemetry imports (optional - gracefully handle if not installed)
try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

# Global tracer instance
_tracer: object | None = None
_tracer_provider: object | None = None


def setup_tracing(
    service_name: str,
    service_version: str = "1.0.0",
    exporter: str = "console",
    sample_rate: float = 1.0
) -> None:
    """
    Setup OpenTelemetry tracing for the service
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        exporter: Exporter type ('console', 'otlp', 'none')
        sample_rate: Sampling rate (0.0 to 1.0)
    """
    global _tracer, _tracer_provider

    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry not available, tracing disabled")
        return

    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: service_name,
        "service.version": service_version,
        "deployment.environment": os.getenv("APP_ENV", "development")
    })

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Configure exporter based on type
    if exporter == "console":
        span_processor = BatchSpanProcessor(ConsoleSpanExporter())
        _tracer_provider.add_span_processor(span_processor)
    elif exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
            span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            _tracer_provider.add_span_processor(span_processor)
        except ImportError:
            logger.warning("OTLP exporter not available, falling back to console")
            span_processor = BatchSpanProcessor(ConsoleSpanExporter())
            _tracer_provider.add_span_processor(span_processor)

    # Set global tracer provider
    trace.set_tracer_provider(_tracer_provider)

    # Get tracer
    _tracer = trace.get_tracer(__name__)

    logger.info(f"Tracing enabled for {service_name} with {exporter} exporter")


def get_tracer() -> object | None:
    """
    Get the global tracer instance
    
    Returns:
        Tracer instance or None if not configured
    """
    return _tracer


def instrument_fastapi(app) -> None:
    """
    Instrument FastAPI application with tracing
    
    Args:
        app: FastAPI application instance
    """
    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry not available, FastAPI instrumentation disabled")
        return

    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_httpx() -> None:
    """Instrument HTTPX client with tracing"""
    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry not available, HTTPX instrumentation disabled")
        return

    try:
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument HTTPX: {e}")


def instrument_sqlalchemy(engine) -> None:
    """
    Instrument SQLAlchemy engine with tracing
    
    Args:
        engine: SQLAlchemy engine instance
    """
    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry not available, SQLAlchemy instrumentation disabled")
        return

    try:
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("SQLAlchemy instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument SQLAlchemy: {e}")


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None
):
    """
    Context manager for creating a trace span
    
    Args:
        name: Span name
        attributes: Span attributes
        
    Yields:
        Span object if tracing is available
    """
    if not OPENTELEMETRY_AVAILABLE or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        yield span


def trace_function(name: str | None = None):
    """
    Decorator for tracing function execution
    
    Args:
        name: Span name (defaults to function name)
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        if not OPENTELEMETRY_AVAILABLE or _tracer is None:
            return func

        span_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(span_name) as span:
                # Add function arguments as attributes (if small)
                try:
                    if args and len(args) < 3:
                        span.set_attribute("args", str(args))
                    if kwargs and len(kwargs) < 3:
                        span.set_attribute("kwargs", str(kwargs))
                except Exception:
                    pass

                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def trace_async_function(name: str | None = None):
    """
    Decorator for tracing async function execution
    
    Args:
        name: Span name (defaults to function name)
        
    Returns:
        Decorated async function
    """
    def decorator(func: Callable) -> Callable:
        if not OPENTELEMETRY_AVAILABLE or _tracer is None:
            return func

        span_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        async def wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(span_name) as span:
                # Add function arguments as attributes (if small)
                try:
                    if args and len(args) < 3:
                        span.set_attribute("args", str(args))
                    if kwargs and len(kwargs) < 3:
                        span.set_attribute("kwargs", str(kwargs))
                except Exception:
                    pass

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def set_span_attribute(key: str, value: Any) -> None:
    """
    Set an attribute on the current span
    
    Args:
        key: Attribute key
        value: Attribute value
    """
    if not OPENTELEMETRY_AVAILABLE:
        return

    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute(key, str(value))


def set_span_error(exception: Exception) -> None:
    """
    Record an exception on the current span
    
    Args:
        exception: Exception to record
    """
    if not OPENTELEMETRY_AVAILABLE:
        return

    current_span = trace.get_current_span()
    if current_span:
        current_span.set_status(Status(StatusCode.ERROR, str(exception)))
        current_span.record_exception(exception)


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """
    Add an event to the current span
    
    Args:
        name: Event name
        attributes: Event attributes
    """
    if not OPENTELEMETRY_AVAILABLE:
        return

    current_span = trace.get_current_span()
    if current_span:
        current_span.add_event(name, attributes or {})
