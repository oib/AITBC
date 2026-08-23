"""Exporter registration for metrics/log sinks."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from aitbc.aitbc_logging import get_logger

REGISTERED_EXPORTERS: list[str] = []
_exporter_instances: dict[str, Any] = {}
logger = get_logger(__name__)


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler that merges prometheus_client and legacy metrics."""

    def do_GET(self) -> None:
        if self.path == "/metrics":
            from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

            from ..metrics import metrics_registry

            default = generate_latest(REGISTRY)
            legacy = metrics_registry.render_prometheus().encode()
            if legacy.strip():
                body = default + b"\n" + legacy
            else:
                body = default
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        logger.debug(format, *args)


def register_exporters(exporters: Iterable[str]) -> None:
    """Attach exporters for observability pipelines.

    Wires up Prometheus registrations, log shippers, or tracing exporters.
    """
    for exporter_name in exporters:
        if exporter_name not in REGISTERED_EXPORTERS:
            try:
                _initialize_exporter(exporter_name)
                REGISTERED_EXPORTERS.append(exporter_name)
                logger.info("Registered exporter: %s", exporter_name)
            except Exception as e:
                logger.warning("Failed to initialize exporter %s: %s", exporter_name, e)


def _initialize_exporter(exporter_name: str) -> None:
    """Initialize a specific exporter."""
    if exporter_name == "prometheus":
        _initialize_prometheus()
    elif exporter_name == "log_shipper":
        _initialize_log_shipper()
    elif exporter_name == "tracing":
        _initialize_tracing()
    else:
        logger.debug("Unknown exporter type: %s, skipping initialization", exporter_name)


def _initialize_prometheus() -> None:
    """Initialize Prometheus metrics exporter for the blockchain node process."""
    try:
        import os

        port = int(os.environ.get("AITBC_NODE_METRICS_PORT", 9009))
        server = ThreadingHTTPServer(("", port), _MetricsHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _exporter_instances["prometheus"] = server
        logger.info("Prometheus exporter started on port %s", port)
    except Exception as e:
        logger.warning("Failed to start Prometheus exporter: %s", e)


def _initialize_log_shipper() -> None:
    """Initialize log shipping exporter."""
    try:
        import os

        log_endpoint = os.environ.get("LOG_SHIPPER_ENDPOINT")
        if log_endpoint:
            logger.info("Log shipper configured for endpoint: %s", log_endpoint)
        else:
            logger.debug("LOG_SHIPPER_ENDPOINT not configured, skipping log shipper")
    except Exception as e:
        logger.warning("Failed to initialize log shipper: %s", e)


def _initialize_tracing() -> None:
    """Initialize distributed tracing exporter."""
    try:
        import os

        from opentelemetry import trace
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        jaeger_host = os.environ.get("JAEGER_HOST", "localhost")
        jaeger_port = int(os.environ.get("JAEGER_PORT", 6831))
        trace.set_tracer_provider(TracerProvider())
        tracer_provider = trace.get_tracer_provider()
        jaeger_exporter = JaegerExporter(agent_host_name=jaeger_host, agent_port=jaeger_port)
        span_processor = BatchSpanProcessor(jaeger_exporter)
        tracer_provider.add_span_processor(span_processor)  # type: ignore[attr-defined]
        logger.info("Jaeger tracing exporter configured: %s:%s", jaeger_host, jaeger_port)
    except ImportError:
        logger.warning("opentelemetry packages not installed, skipping tracing exporter")
    except Exception as e:
        logger.warning("Failed to initialize tracing exporter: %s", e)


def get_registered_exporters() -> list[str]:
    """Get list of registered exporter names."""
    return REGISTERED_EXPORTERS.copy()
