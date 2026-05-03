"""
Standardized error response middleware for FastAPI
"""

from typing import Callable

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware to standardize error responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            logger.warning(
                "HTTP exception",
                status_code=e.status_code,
                detail=e.detail,
                path=request.url.path,
                method=request.method,
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
            logger.error(
                "Unhandled exception",
                exc=str(e),
                path=request.url.path,
                method=request.method,
                exc_info=True,
            )
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
