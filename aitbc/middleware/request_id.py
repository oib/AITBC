"""
Request ID correlation middleware for structured logging
"""

import uuid
from collections.abc import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests for correlation"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id
        logger.info(
            "Incoming request - ID: %s, Method: %s, Path: %s, Client: %s",
            request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        response = await call_next(request)
        response.headers[self.header_name] = request_id
        logger.info("Request completed - ID: %s, Status: %s", request_id, response.status_code)
        return response
