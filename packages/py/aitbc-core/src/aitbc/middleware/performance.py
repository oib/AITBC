"""
Performance logging middleware for tracking request timing
"""

import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aitbc.logging import get_logger

logger = get_logger(__name__)


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request performance metrics"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.perf_counter() - start_time
        
        # Log performance metrics
        logger.info(
            "Request performance",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        
        # Add performance header
        response.headers["X-Process-Time"] = f"{duration:.3f}"
        
        return response
