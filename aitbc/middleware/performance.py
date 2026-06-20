"""
Performance logging middleware for tracking request timing
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# High-frequency paths logged at DEBUG to avoid log spam.
_QUIET_PATHS = frozenset(
    {
        "/health",
        "/prometheus",
        "/prometheus/",
        "/metrics",
        "/metrics/",
    }
)

# Threshold (ms) above which a request is logged at WARNING (slow request).
_SLOW_REQUEST_MS = 1000.0


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request performance metrics"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        duration_ms = round(duration * 1000, 2)

        path = request.url.path
        is_quiet = path in _QUIET_PATHS or path.startswith("/v1/miners/poll")
        status = response.status_code

        # Always set the header for client-side observability
        response.headers["X-Process-Time"] = f"{duration:.3f}"

        # Log at appropriate level:
        # - DEBUG for quiet paths and fast successful requests
        # - WARNING for slow requests (>1s) or 5xx errors
        # - INFO for 4xx errors
        if is_quiet and status < 400 and duration_ms < _SLOW_REQUEST_MS:
            logger.debug(
                "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
                request.method,
                path,
                status,
                duration_ms,
            )
        elif status >= 500 or duration_ms >= _SLOW_REQUEST_MS:
            logger.warning(
                "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
                request.method,
                path,
                status,
                duration_ms,
            )
        elif status >= 400:
            logger.info(
                "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
                request.method,
                path,
                status,
                duration_ms,
            )
        else:
            logger.debug(
                "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
                request.method,
                path,
                status,
                duration_ms,
            )

        return response
