"""
Request validation middleware for FastAPI
"""

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class RequestValidationMiddleware:
    """Middleware to validate incoming requests.

    Pure ASGI rather than ``BaseHTTPMiddleware``: the base class spawns an
    anyio task and copies contextvars on every request.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_request_size: int = 10 * 1024 * 1024,  # 10MB default
    ) -> None:
        self.app = app
        self.max_request_size = max_request_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else "unknown"

        # Read the actual request body; this enforces the size limit regardless of
        # a chunked transfer or a spoofed Content-Length header.
        body = b""
        limit = self.max_request_size + 1
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
            if len(body) > limit:
                logger.warning("Request too large: client=%s", client_host)
                await JSONResponse(
                    status_code=413,
                    content={"detail": f"Request too large. Maximum size is {self.max_request_size} bytes"},
                )(scope, receive, send)
                return

        # Replay the buffered body to the downstream app.
        body_sent = False

        async def replay_receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
