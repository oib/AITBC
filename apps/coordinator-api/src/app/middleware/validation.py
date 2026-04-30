"""
Request validation middleware for FastAPI
"""

from typing import Callable

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..app_logging import get_logger

logger = get_logger(__name__)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate incoming requests"""

    def __init__(
        self,
        app: ASGIApp,
        max_request_size: int = 10 * 1024 * 1024,  # 10MB default
        max_response_size: int = 10 * 1024 * 1024,  # 10MB default
    ) -> None:
        super().__init__(app)
        self.max_request_size = max_request_size
        self.max_response_size = max_response_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Validate request size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    logger.warning(
                        "Request too large",
                        content_length=size,
                        max_size=self.max_request_size,
                        client=request.client.host if request.client else "unknown",
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request too large. Maximum size is {self.max_request_size} bytes",
                    )
            except ValueError:
                logger.warning("Invalid content-length header", content_length=content_length)

        # Process request
        response = await call_next(request)

        # Validate response size
        response_size = len(response.body)
        if response_size > self.max_response_size:
            logger.warning(
                "Response too large",
                response_size=response_size,
                max_size=self.max_response_size,
                path=request.url.path,
            )
            raise HTTPException(
                status_code=500,
                detail="Response too large",
            )

        return response
