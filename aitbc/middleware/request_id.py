"""
Request ID correlation middleware for structured logging
"""

import uuid

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger
from aitbc.http_client.client import set_request_id

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


class RequestIDMiddleware:
    """Middleware to add request ID to all requests for correlation.

    Pure ASGI rather than ``BaseHTTPMiddleware``: the base class spawns an
    anyio task and copies contextvars on every request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.header_name = "X-Request-ID"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        set_request_id(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        scope["state"]["correlation_id"] = request_id  # Alias for correlation tracking

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

        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                name = self.header_name.lower().encode()
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != name]
                headers.append((name, request_id.encode()))
                message = dict(message, headers=headers)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status = 500
            raise
        finally:
            if is_quiet and status < 400:
                logger.debug("Request completed - ID: %s, Status: %s", request_id, status)
            elif status >= 500:
                logger.warning("Request completed - ID: %s, Status: %s, Path: %s", request_id, status, path)
            elif status >= 400:
                logger.warning("Request completed - ID: %s, Status: %s, Path: %s", request_id, status, path)
            else:
                logger.debug("Request completed - ID: %s, Status: %s", request_id, status)
