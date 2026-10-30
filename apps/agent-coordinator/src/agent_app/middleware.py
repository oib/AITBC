import time
from typing import Any

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger
from aitbc.auth import security_headers

from .monitoring.prometheus_metrics import performance_monitor

logger = get_logger(__name__)

_SKIP_PATHS = frozenset({"/health", "/ws/status", "/api/v1/agent/ws/status"})


class ObservabilityASGIMiddleware:
    """v0.6.5: Request/response logging + error metrics in one place.

    Pure ASGI rather than ``@app.middleware("http")``: the decorator path
    goes through ``BaseHTTPMiddleware``, which spawns an anyio task and
    copies contextvars on every request. Status is read off the
    ``http.response.start`` message via a send wrapper.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        method = request.method
        path = request.url.path
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return
        start_time = time.time()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "REQUEST %s %s → 500 (unhandled: %s) [%.3fs]",
                method,
                path,
                e,
                duration,
            )
            raise

        duration = time.time() - start_time

        # Record performance metrics
        performance_monitor.record_request(
            method=method,
            endpoint=path,
            status_code=status_code,
            duration=duration,
        )

        # Structured logging — INFO for success, WARNING for 4xx, ERROR for 5xx
        if status_code >= 500:
            logger.error("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)
        elif status_code >= 400:
            logger.warning("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)
        else:
            logger.info("REQUEST %s %s → %d [%.3fs]", method, path, status_code, duration)


class SecurityHeadersASGIMiddleware:
    """Pure ASGI security-headers injection via a send wrapper."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = security_headers.get_security_headers()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers", []))
                for header, value in headers.items():
                    raw.append((header.encode(), value.encode()))
                message = dict(message, headers=raw)
            await send(message)

        await self.app(scope, receive, send_wrapper)


def register_middleware(app: Any) -> None:
    app.add_middleware(ObservabilityASGIMiddleware)
    app.add_middleware(SecurityHeadersASGIMiddleware)
