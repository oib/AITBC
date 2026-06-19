"""
Prometheus metrics middleware for HTTP request/response instrumentation.

Tracks:
- Request latency histograms by method and endpoint
- Total request counter by method, endpoint, and status
- Error rate counter (4xx and 5xx responses)
- In-flight request gauge
"""

from collections.abc import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from typing import cast

# Default registry metrics (not using custom registry to avoid conflicts)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP errors (4xx and 5xx)",
    ["method", "endpoint", "status_code"],
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for all HTTP requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import time

        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time

        method = request.method
        # Use route path template if available, otherwise use raw path
        endpoint = request.url.path
        if hasattr(request.state, "route_path"):
            endpoint = request.state.route_path
        status_code = str(response.status_code)

        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()

        REQUEST_LATENCY.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).observe(duration)

        # Track errors (4xx and 5xx)
        if response.status_code >= 400:
            ERROR_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()

        return cast(Response, response)
