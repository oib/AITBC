"""
Correlation ID middleware for distributed tracing.

This middleware adds X-Request-ID headers to all requests for end-to-end tracing
across microservice boundaries.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.http_client.client import set_request_id


class CorrelationIDMiddleware:
    """
    Middleware to add correlation IDs to all HTTP requests.

    - Extracts X-Request-ID from incoming headers if present
    - Generates new UUID if not present
    - Adds correlation_id to request state for logging
    - Adds X-Request-ID to response headers

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

        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(correlation_id)

        # Add to request state for access in endpoints and logging
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        scope["state"]["request_id"] = correlation_id  # Alias for request tracking

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", correlation_id.encode()))
                message = dict(message, headers=headers)
            await send(message)

        # Process request
        await self.app(scope, receive, send_wrapper)
