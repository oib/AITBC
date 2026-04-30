"""
Request ID correlation middleware for structured logging
"""

import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..app_logging import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests for correlation"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or retrieve request ID
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        
        # Add request ID to request state for use in endpoints
        request.state.request_id = request_id
        
        # Bind request ID to logger context
        logger = get_logger(__name__).bind(request_id=request_id)
        
        # Log request start
        logger.info(
            "Incoming request",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers[self.header_name] = request_id
        
        # Log request completion
        logger.info(
            "Request completed",
            status_code=response.status_code,
        )
        
        return response
