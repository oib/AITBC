"""
Request ID correlation middleware for structured logging
"""

import uuid
from typing import Callable

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
        # Generate or retrieve request ID
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        
        # Add request ID to request state for use in endpoints
        request.state.request_id = request_id
        
        # Log request start (standard logging doesn't support .bind())
        logger.info(
            f"Incoming request - ID: {request_id}, Method: {request.method}, Path: {request.url.path}, Client: {request.client.host if request.client else 'unknown'}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers[self.header_name] = request_id
        
        # Log request completion
        logger.info(
            f"Request completed - ID: {request_id}, Status: {response.status_code}"
        )
        
        return response
