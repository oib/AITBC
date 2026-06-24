"""
Request ID correlation middleware for structured logging
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

_QUIET_PATHS = frozenset(
    {
        "/health",
        "/prometheus",
        "/prometheus/",
        "/metrics",
        "/metrics/",
    }
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests for correlation"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.correlation_id = request_id  # Alias for correlation tracking

        path = request.url.path
        is_quiet = path in _QUIET_PATHS or path.startswith("/v1/miners/poll")

        if not is_quiet:
            logger.info(
                "Incoming request - ID: %s, Method: %s, Path: %s, Client: %s",
                request_id,
                request.method,
                path,
                request.client.host if request.client else "unknown",
            )

        response = await call_next(request)
        response.headers[self.header_name] = request_id

        status = response.status_code
        if is_quiet and status < 400:
            logger.debug("Request completed - ID: %s, Status: %s", request_id, status)
        elif status >= 500:
            logger.warning("Request completed - ID: %s, Status: %s, Path: %s", request_id, status, path)
        elif status >= 400:
            logger.info("Request completed - ID: %s, Status: %s, Path: %s", request_id, status, path)
        else:
            logger.debug("Request completed - ID: %s, Status: %s", request_id, status)

        return response
