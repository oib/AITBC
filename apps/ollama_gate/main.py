"""
AITBC Ollama shop gate (OLLAMA-PROXY-GATE-1, #841).

Ollama itself is a bare HTTP backend with no auth. This sidecar sits
between node2's nginx ``/ollama/`` location and ``127.0.0.1:11434`` and
applies the same per-job access-token gate as ffmpeg/whisper/hermes
(SHOP-ENDPOINTS-NO-PAYMENT-GATE-1, #803): a buyer call must carry
``X-Access-Key`` + ``X-Access-Secret`` + ``X-Job-Id`` for a paid job.

Only the inference routes a paid offer can legitimately use are exposed;
model-management routes (/api/pull, /api/create, /api/delete, /api/copy,
/api/push, /api/blobs) are not proxied at all and answer 404 here.
``/api/tags`` and ``/api/version`` stay public — model discovery is not
paid work — and ``/health`` is the unit's own probe.

Streaming is passed through (ollama answers NDJSON chunks), so the proxy
reads and yields the body instead of buffering it.
"""

from __future__ import annotations

import os
from typing import Any

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response, StreamingResponse  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.shop_gate import require_job_access  # noqa: E402

configure_logging(level="INFO", service_name="ollama-gate", to_file=True)
logger = get_logger(__name__)

OLLAMA_BACKEND = os.environ.get("OLLAMA_BACKEND_URL", "http://127.0.0.1:11434")
OLLAMA_GATE_PORT = int(os.environ.get("OLLAMA_GATE_PORT", "8271"))
OLLAMA_GATE_BIND = os.environ.get("OLLAMA_GATE_BIND_HOST", "127.0.0.1")
# A generate call can run for a long time; the backend read timeout must
# outlive the longest plausible streamed response, not a request budget.
BACKEND_TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=10.0)

# Paid inference routes — gated. Everything else ollama serves is not proxied.
_GATED_POSTS = ("/api/generate", "/api/chat", "/api/embed", "/api/embeddings")
_PUBLIC_GETS = ("/api/tags", "/api/version")

_HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding"}


_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _client
    _client = httpx.AsyncClient(base_url=OLLAMA_BACKEND, timeout=BACKEND_TIMEOUT)
    logger.info("ollama-gate up: backend=%s", OLLAMA_BACKEND)
    yield
    if _client is not None:
        await _client.aclose()


app = FastAPI(title="AITBC Ollama Gate", version="1.0.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return create_simple_health_response("ollama-gate")


@app.get("/api/version")
async def public_version() -> Response:
    return await _proxy_get("/api/version")


@app.get("/api/tags")
async def public_tags() -> Response:
    return await _proxy_get("/api/tags")


async def _proxy_get(path: str) -> Response:
    assert _client is not None
    resp = await _client.get(path)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


async def _proxy_gated(request: Request, path: str) -> Response:
    """Stream a gated POST to the ollama backend and stream the answer back."""
    assert _client is not None
    body = await request.body()
    upstream = await _client.send(
        _client.build_request("POST", path, content=body, headers={"content-type": "application/json"}),
        stream=True,
    )
    headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP}

    async def _stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        headers=headers,
        media_type=upstream.headers.get("content-type"),
    )


def _gated_handler(path: str):
    async def _handler(request: Request) -> Response:
        return await _proxy_gated(request, path)

    return _handler


for _path in _GATED_POSTS:
    # One route object per path so the OpenAPI surface names them; all share
    # the same handler and the same dependency.
    app.add_api_route(
        _path,
        _gated_handler(_path),
        methods=["POST"],
        dependencies=[Depends(require_job_access)],
    )


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error on %s: %s: %s", request.url.path, type(exc).__name__, exc)
    return JSONResponse(status_code=500, content={"error": "internal gate error"})


if __name__ == "__main__":
    uvicorn.run(app, host=OLLAMA_GATE_BIND, port=OLLAMA_GATE_PORT, log_level="info")
