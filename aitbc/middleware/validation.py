"""
Request validation middleware for FastAPI
"""

import json
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def _json_safe(value: Any) -> Any:
    """Render ``value`` so ``json.dumps`` can always serialize it.

    Literal ``NaN``/``Infinity`` JSON floats parse into Python floats that
    strict JSON cannot carry — FastAPI's default 422 body echoes them back
    verbatim in ``input``/``ctx`` and the response itself dies with
    "Out of range float values are not JSON compliant" (#1676). Non-finite
    floats become their repr; anything else unserializable likewise.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)


def register_request_validation_error_handler(app: FastAPI) -> None:
    """Install a JSON-safe ``RequestValidationError`` handler (#1676).

    FastAPI's built-in 422 response echoes ``exc.errors()`` verbatim; a body
    containing literal ``NaN``/``Infinity`` therefore 500s instead of 422ing.
    This handler keeps the default ``{"detail": [...]}`` shape but sanitizes
    every field value, so the error body always serializes.
    """

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        try:
            errors = exc.errors()
        except Exception:
            # Defensive: a pathological error object must not 500 the 422 path.
            errors = []
        detail = [{str(k): _json_safe(v) for k, v in error.items()} for error in errors]
        return JSONResponse(status_code=422, content={"detail": detail})


class RequestValidationMiddleware:
    """Middleware to validate incoming requests.

    Pure ASGI rather than ``BaseHTTPMiddleware``: the base class spawns an
    anyio task and copies contextvars on every request.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_request_size: int = 10 * 1024 * 1024,  # 10MB default
        exempt_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.max_request_size = max_request_size
        self.exempt_prefixes = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Routes with their own size governance (e.g. streamed uploads) skip
        # the buffer-and-cap path entirely — exempting them here keeps a 100MB
        # upload from being buffered into memory before the route's own
        # limiter ever sees it (#1234).
        if scope.get("path", "").startswith(self.exempt_prefixes):
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
