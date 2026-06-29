import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from aitbc.aitbc_logging import get_logger

from .auth.middleware import security_headers
from .monitoring.prometheus_metrics import performance_monitor

logger = get_logger(__name__)


def register_middleware(app: Any) -> None:
    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def observability_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """v0.6.5: Request/response logging + error metrics in one place.

        Logs every request with method, path, status, and duration.
        Elevates error-level logging for 5xx responses so all future
        releases inherit structured observability without per-route logging.
        """
        start_time = time.time()
        method = request.method
        path = request.url.path

        # Skip noisy endpoints
        if path in ("/health", "/ws/status", "/api/v1/agent/ws/status"):
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "REQUEST %s %s → 500 (unhandled: %s) [%.3fs]",
                method,
                path,
                e,
                duration,
            )
            raise

        duration = time.time() - start_time
        status_code = response.status_code

        # Record performance metrics
        performance_monitor.record_request(
            method=method,
            endpoint=path,
            status_code=status_code,
            duration=duration,
        )

        # Structured logging — INFO for success, WARNING for 4xx, ERROR for 5xx
        if status_code >= 500:
            logger.error("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)
        elif status_code >= 400:
            logger.warning("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)
        else:
            logger.info("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)

        return response

    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def security_headers_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = security_headers.get_security_headers()
        for header, value in headers.items():
            response.headers[header] = value
        return response
