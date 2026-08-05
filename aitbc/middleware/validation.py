"""
Request validation middleware for FastAPI
"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate incoming requests."""

    def __init__(
        self,
        app: ASGIApp,
        max_request_size: int = 10 * 1024 * 1024,  # 10MB default
    ) -> None:
        super().__init__(app)
        self.max_request_size = max_request_size

    async def _read_body_with_limit(self, request: Request) -> bytes:
        """Read the request body up to max_request_size + 1 bytes."""
        body = b""
        limit = self.max_request_size + 1
        async for chunk in request.stream():
            body += chunk
            if len(body) > limit:
                logger.warning(
                    "Request too large: client=%s",
                    request.client.host if request.client else "unknown",
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"Request too large. Maximum size is {self.max_request_size} bytes",
                )
        return body

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # ponytail: actual body read limits chunked / spoofed Content-Length
        request._body = await self._read_body_with_limit(request)

        # Process request
        response = await call_next(request)

        return response
