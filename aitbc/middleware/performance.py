"""
Performance logging middleware for tracking request timing
"""

import time

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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

# Threshold (ms) above which a request is logged at WARNING (slow request).
_SLOW_REQUEST_MS = 1000.0


class PerformanceLoggingMiddleware:
    """Middleware to log request performance metrics.

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
        start_time = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                # Header for client-side observability; duration so far since
                # the body may stream after this message.
                process_time = f"{time.perf_counter() - start_time:.3f}"
                headers = list(message.get("headers", []))
                headers.append((b"x-process-time", process_time.encode()))
                message = dict(message, headers=headers)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start_time
            duration_ms = round(duration * 1000, 2)

            path = request.url.path
            is_quiet = path in _QUIET_PATHS or path.startswith("/v1/miners/poll")

            if is_quiet and status < 400 and duration_ms < _SLOW_REQUEST_MS:
                log = logger.debug
            elif status >= 500 or duration_ms >= _SLOW_REQUEST_MS or status >= 400:
                log = logger.warning
            else:
                log = logger.debug
            log(
                "Request performance - Method: %s, Path: %s, Status: %s, Duration: %sms",
                request.method,
                path,
                status,
                duration_ms,
            )
