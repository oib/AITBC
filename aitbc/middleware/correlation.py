"""
Correlation ID middleware for distributed tracing.

This middleware adds X-Request-ID headers to all requests for end-to-end tracing
across microservice boundaries.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation IDs to all HTTP requests.

    - Extracts X-Request-ID from incoming headers if present
    - Generates new UUID if not present
    - Adds correlation_id to request state for logging
    - Adds X-Request-ID to response headers
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Add to request state for access in endpoints and logging
        request.state.correlation_id = correlation_id
        request.state.request_id = correlation_id  # Alias for request tracking

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Request-ID"] = correlation_id

        return response
