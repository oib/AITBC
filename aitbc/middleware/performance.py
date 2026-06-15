"""
Performance logging middleware for tracking request timing
"""

import time
from collections.abc import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request performance metrics"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        logger.info(
            "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
            request.method,
            request.url.path,
            response.status_code,
            round(duration * 1000, 2),
        )
        response.headers["X-Process-Time"] = f"{duration:.3f}"
        return response
