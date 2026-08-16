"""FastAPI wrapper around the existing simple_exchange handlers.

This replaces the stdlib ``http.server`` backend with FastAPI. The existing
``ExchangeAPIHandler`` is reused via a thin request/response adapter so the
business logic (B1/B2/B3 fixes) is preserved.
"""

import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import Response

from aitbc.aitbc_logging import configure_logging, get_logger
from .db import init_db
from .handlers import ExchangeAPIHandler
from .handlers.base import MAX_BODY_BYTES

configure_logging(level="INFO", service_name="exchange", to_file=True)
logger = get_logger(__name__)


class _HandlerHeaders(dict):
    """Case-insensitive header map that still has .get like BaseHTTPRequestHandler."""

    def __init__(self, mapping: dict[str, str]):
        super().__init__({k.lower(): v for k, v in mapping.items()})

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return super().get(key.lower(), default)


class FastAPIRequestAdapter(ExchangeAPIHandler):
    """Adapts a FastAPI Request so ExchangeAPIHandler can dispatch unchanged."""

    def __init__(self, request: Request, method: str, body: bytes, raw_path: str):
        # Do not call BaseHTTPRequestHandler.__init__ — we do not need a server socket.
        self.request = request
        self.command = method
        # raw_path is the request target before Starlette collapses '//'.
        query = request.url.query
        self.path = raw_path + (f"?{query}" if query else "")
        headers = dict(request.headers.items())
        headers.setdefault("content-length", str(len(body)))
        # ponytail: BaseHTTPRequestHandler.headers is typed as email.message.Message in stubs.
        self.headers = cast(Any, _HandlerHeaders(headers))
        self.rfile = io.BytesIO(body)
        self.wfile: io.BytesIO = io.BytesIO()
        self._response_status = 200
        self._response_headers: list[tuple[str, str]] = []

    def send_response(self, code, message=None):
        self._response_status = code

    def send_header(self, keyword, value):
        self._response_headers.append((keyword, value))

    def end_headers(self):
        pass

    def send_error(self, code, message=None, explain=None):
        self._response_status = code
        self._response_headers = [("Content-Type", "application/json")]
        error_body = {"error": message or "Error"}
        self.wfile.write(json.dumps(error_body).encode())

    def get_response(self) -> Response:
        body = self.wfile.getvalue()
        headers = dict(self._response_headers)
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        return Response(content=body, status_code=self._response_status, headers=headers)


def _raw_path(request: Request) -> str:
    raw = request.scope.get("raw_path")
    decoded = ""
    if isinstance(raw, bytes | bytearray):
        decoded = raw.decode("latin-1").split("?", 1)[0]
    path = decoded or request.scope.get("path") or request.url.path
    # HTTPServer collapsed '//' before do_GET; keep '..' so that guard still 400s.
    if path.startswith(".."):
        return path
    while path.startswith("//"):
        path = path[1:]
    return path or "/"


async def _dispatch(request: Request, method: str) -> Response:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(
            content=json.dumps({"error": f"Request body too large (max {MAX_BODY_BYTES} bytes)"}),
            status_code=413,
            media_type="application/json",
        )
    adapter = FastAPIRequestAdapter(request, method, body, _raw_path(request))

    if method == "GET":
        adapter.do_GET()
    elif method == "POST":
        adapter.do_POST()
    elif method == "DELETE":
        adapter.do_DELETE()
    elif method == "OPTIONS":
        adapter.do_OPTIONS()
    else:
        return Response(status_code=405, content=b'{"error":"Method not allowed"}')

    return adapter.get_response()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the exchange database on startup."""
    logger.info("Starting AITBC Exchange Service")
    init_db()
    yield
    logger.info("Shutting down AITBC Exchange Service")


app = FastAPI(
    title="AITBC Trade Exchange",
    description="Simple exchange service for AITBC",
    version="0.1.0",
    lifespan=lifespan,
)


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def dispatch_read(request: Request, full_path: str) -> Response:
    """Public read routes (auth enforced inside handler where appropriate)."""
    return await _dispatch(request, request.method)


@app.api_route("/{full_path:path}", methods=["POST", "PUT", "DELETE"])
async def dispatch_write(request: Request, full_path: str) -> Response:
    """Write auth stays in ExchangeAPIHandler._require_api_key so unknown
    POST/DELETE still 404 instead of 401-before-route."""
    return await _dispatch(request, request.method)
