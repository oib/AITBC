"""
Standardized error response middleware for FastAPI
"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware to standardize error responses"""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            logger.warning(
                "HTTP exception - Status: %s, Detail: %s, Path: %s, Method: %s",
                e.status_code,
                e.detail,
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "type": "http_error",
                        "message": e.detail,
                        "status_code": e.status_code,
                        "path": request.url.path,
                    }
                },
            )
        except Exception as e:
            logger.error("Unhandled exception: %s at %s", e, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_error",
                        "message": "An internal server error occurred",
                        "status_code": 500,
                        "path": request.url.path,
                    }
                },
            )
