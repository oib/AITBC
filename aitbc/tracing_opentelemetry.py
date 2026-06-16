"""
OpenTelemetry Configuration for AITBC Services
Centralized tracing configuration for distributed tracing
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes


class TracingConfig:
    """OpenTelemetry tracing configuration"""

    def __init__(
        self,
        service_name: str,
        service_version: str = "0.1.0",
        otlp_endpoint: str | None = None,
        use_http: bool = False,
        enable_console: bool = False,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self.use_http = use_http or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc") == "http"
        self.enable_console = enable_console or os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true"

        self._provider: TracerProvider | None = None
        self._tracer: trace.Tracer | None = None

    def initialize(self) -> trace.Tracer:
        """Initialize OpenTelemetry tracing"""
        # Create resource with service info
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: self.service_name,
                ResourceAttributes.SERVICE_VERSION: self.service_version,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter
        otlp_exporter: OTLPHttpSpanExporter | OTLPSpanExporter
        if self.use_http:
            otlp_exporter = OTLPHttpSpanExporter(endpoint=f"{self.otlp_endpoint}/v1/traces")
        else:
            otlp_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)

        provider = TracerProvider(
            resource=Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: self.service_name,
                    ResourceAttributes.SERVICE_VERSION: self.service_version,
                    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
                }
            )
        )

        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Add console exporter for debugging
        if self.enable_console:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Set as global tracer provider
        trace.set_tracer_provider(provider)
        self._provider = provider
        self._tracer = trace.get_tracer(self.service_name, self.service_version)

        return self._tracer

    def get_tracer(self) -> trace.Tracer:
        """Get tracer instance"""
        if self._tracer is None:
            return self.initialize()
        return self._tracer

    def instrument_app(self, app: object, **kwargs: object) -> None:
        """Instrument FastAPI app with OpenTelemetry"""
        FastAPIInstrumentor.instrument_app(app, tracer_provider=self._provider, **kwargs)  # type: ignore[arg-type]

    def instrument_requests(self, **kwargs: object) -> None:
        """Instrument requests library"""
        RequestsInstrumentor().instrument(tracer_provider=self._provider, **kwargs)

    def instrument_redis(self, **kwargs: object) -> None:
        """Instrument Redis client"""
        RedisInstrumentor().instrument(tracer_provider=self._provider, **kwargs)  # type: ignore[arg-type]

    def instrument_sqlalchemy(self, engine: object, **kwargs: object) -> None:
        """Instrument SQLAlchemy engine"""
        SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=self._provider, **kwargs)

    def shutdown(self) -> None:
        """Shutdown tracer provider"""
        if self._provider:
            self._provider.shutdown()


# Global tracing config instances
_tracing_configs: dict[str, TracingConfig] = {}


def get_tracing_config(
    service_name: str,
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    use_http: bool = False,
    enable_console: bool = False,
) -> TracingConfig:
    """Get or create tracing config for a service"""
    if service_name not in _tracing_configs:
        _tracing_configs[service_name] = TracingConfig(
            service_name=service_name,
            service_version=service_version,
            otlp_endpoint=otlp_endpoint,
            use_http=use_http,
            enable_console=enable_console,
        )
    return _tracing_configs[service_name]


def initialize_tracing(
    service_name: str,
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    use_http: bool = False,
    enable_console: bool = False,
) -> trace.Tracer:
    """Initialize tracing for a service and return tracer"""
    config = get_tracing_config(
        service_name=service_name,
        service_version=service_version,
        otlp_endpoint=otlp_endpoint,
        use_http=use_http,
        enable_console=enable_console,
    )
    return config.initialize()


# Convenience function for quick setup
def setup_opentelemetry(
    service_name: str,
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    use_http: bool = False,
    enable_console: bool = False,
    app: object = None,
    engine: object = None,
) -> trace.Tracer:
    """Quick setup for OpenTelemetry with common instrumentations"""
    config = TracingConfig(
        service_name=service_name,
        service_version=service_version,
        otlp_endpoint=otlp_endpoint,
        use_http=use_http,
        enable_console=enable_console,
    )
    tracer = config.initialize()
    if app is not None:
        config.instrument_app(app)
    config.instrument_requests()
    config.instrument_redis()
    if engine is not None:
        config.instrument_sqlalchemy(engine)
    return tracer
