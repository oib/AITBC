"""FastAPI wrapper around the existing simple_exchange handlers.

This replaces the stdlib ``http.server`` backend with FastAPI and uses the
shared ``aitbc.auth.APIKeyAuthenticator`` for write operations. The existing
``ExchangeAPIHandler`` is reused via a thin request/response adapter so the
business logic (B1/B2/B3 fixes) is preserved.
"""

import io
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.auth import APIKeyAuthenticator
from aitbc.health_checks import create_simple_health_response
from aitbc.middleware import setup_cors

from .db import init_db
from .handlers import ExchangeAPIHandler

configure_logging(level="INFO", service_name="exchange", to_file=True)
logger = get_logger(__name__)


# ponytail: header name matches the existing ExchangeAPIHandler._require_api_key()
# expectation so both the FastAPI dependency and the adapter's check succeed.
require_exchange_api_key = APIKeyAuthenticator(
    expected_key=os.environ.get("EXCHANGE_API_KEY"),
    auth_enabled=True,
    header_name="X-Api-Key",
    success_role="exchange_admin",
)


class FastAPIRequestAdapter(ExchangeAPIHandler):
    """Adapts a FastAPI Request so ExchangeAPIHandler can dispatch unchanged."""

    def __init__(self, request: Request, method: str, body: bytes):
        # Do not call BaseHTTPRequestHandler.__init__ — we do not need a server socket.
        self.request = request
        self.command = method
        self.path = str(request.url)
        self.headers = request.headers
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
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


async def _dispatch(request: Request, method: str) -> Response:
    body = await request.body()
    adapter = FastAPIRequestAdapter(request, method, body)

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

# ponytail: allow_credentials=False because wildcard origins are used.
setup_cors(app, allow_origins=["*"], allow_credentials=False)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return create_simple_health_response("exchange")


@app.api_route("/{full_path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def dispatch_read(request: Request, full_path: str) -> Response:
    """Public read routes (auth enforced inside handler where appropriate)."""
    return await _dispatch(request, request.method)


@app.api_route(
    "/{full_path:path}",
    methods=["POST", "PUT", "DELETE"],
    dependencies=[Depends(require_exchange_api_key)],
)
async def dispatch_write(request: Request, full_path: str) -> Response:
    """Write routes require a valid X-Api-Key via aitbc.auth.APIKeyAuthenticator."""
    return await _dispatch(request, request.method)
