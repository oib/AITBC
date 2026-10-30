"""
Standardized error response middleware for FastAPI
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware:
    """Middleware to standardize error responses.

    Pure ASGI rather than ``BaseHTTPMiddleware``: the base class spawns an
    anyio task and copies contextvars on every request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except HTTPException as e:
            logger.warning(
                "HTTP exception - Status: %s, Detail: %s, Path: %s, Method: %s",
                e.status_code,
                e.detail,
                request.url.path,
                request.method,
            )
            if response_started:
                raise
            await JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "type": "http_error",
                        "message": e.detail,
                        "status_code": e.status_code,
                        "path": request.url.path,
                    }
                },
            )(scope, receive, send)
        except Exception as e:
            logger.error("Unhandled exception: %s at %s", e, request.url.path)
            if response_started:
                # ServerErrorMiddleware (or another inner layer) already sent a
                # response; a second http.response.start is a protocol error.
                raise
            await JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_error",
                        "message": "An internal server error occurred",
                        "status_code": 500,
                        "path": request.url.path,
                    }
                },
            )(scope, receive, send)
