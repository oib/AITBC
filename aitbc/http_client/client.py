"""
HTTP client wrapper for request ID propagation
"""

import contextvars
from collections.abc import Mapping
from typing import Any

import httpx
from starlette.requests import Request

# Context variable to store the current request ID
request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context"""
    request_id_context.set(request_id)


def get_request_id() -> str:
    """Get the current request ID from context"""
    return request_id_context.get()


class RequestIDPropagatingClient(httpx.AsyncClient):
    """HTTP client that propagates X-Request-ID header to outbound requests"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.header_name = "X-Request-ID"

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with X-Request-ID propagation"""
        # Get current request ID from context
        request_id = get_request_id()

        # Add X-Request-ID header if available
        if request_id:
            if headers is None:
                headers = {}
            headers = dict(headers)  # Convert to mutable dict
            headers[self.header_name] = request_id

        return await super().request(method, url, headers=headers, **kwargs)


class RequestIDMiddleware:
    """Middleware to set request ID in context for propagation"""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.header_name = "X-Request-ID"

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI middleware to set request ID in context"""
        if scope["type"] == "http":
            # Extract request ID from headers
            headers = dict(scope.get("headers", []))
            request_id = headers.get(self.header_name.lower().encode()) or str(__import__("uuid").uuid4())

            # Set request ID in context
            token = request_id_context.set(request_id.decode() if isinstance(request_id, bytes) else request_id)

            try:
                await self.app(scope, receive, send)
            finally:
                # Reset context
                request_id_context.reset(token)
        else:
            await self.app(scope, receive, send)


def get_request_id_from_request(request: Request) -> str:
    """Extract request ID from FastAPI request"""
    return request.headers.get("X-Request-ID") or str(__import__("uuid").uuid4())


def setup_request_id_context(request: Request) -> None:
    """Set request ID in context from FastAPI request"""
    request_id = get_request_id_from_request(request)
    set_request_id(request_id)
