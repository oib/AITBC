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

Paid-call policy (APIGW-OLLAMA-DEPTH2-1, #1613):

- The JSON body is parsed once and validated before anything reaches
  ollama: ``model`` is required, must be in ``OLLAMA_GATE_ALLOWED_MODELS``
  when that allowlist is configured, and must equal the model the paid job
  was issued for (``job.model`` from the market access-token verify
  response) — a token for a llama3.2 job cannot buy a 70B run.
- Resource-heavy request fields are bounded: ``options`` keys that size
  VRAM/RAM/context (``num_ctx``, ``num_predict``, ``num_gpu``, ``num_batch``,
  ``num_thread``, ``num_keep``, ``repeat_last_n``) are capped by env-tunable
  ceilings, and ``keep_alive`` is capped in seconds so a caller cannot pin
  models in VRAM indefinitely (``-1``/forever is rejected).
- Concurrency is bounded: a global semaphore
  (``OLLAMA_GATE_MAX_CONCURRENT``) caps simultaneous upstream streams and a
  second call for the same job id gets an immediate 429 — one client cannot
  stack streams on one job or starve the shop's parallel slots. Callers
  waiting on the global bound time out after ``OLLAMA_GATE_QUEUE_TIMEOUT``
  seconds with 429. Both primitives are ``threading``-based so they behave
  identically under anyio/asyncio test portals.

Streaming is passed through (ollama answers NDJSON chunks), so the proxy
reads and yields the body instead of buffering it.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from typing import Annotated, Any

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
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
# OLLAMA-GATE-BODY-1 (#1480): the gated proxy used to ``await request.body()``
# with no ceiling — one request could make the sidecar allocate an arbitrary
# body whole. Inference bodies (prompts + optional images) are legitimately
# large but nowhere near this; 32 MiB is generous headroom. Enforced twice:
# on Content-Length up front, and again while streaming so a missing or
# dishonest header cannot bypass it.
MAX_BODY_BYTES = int(os.environ.get("OLLAMA_GATE_MAX_BODY_BYTES", str(32 * 1024 * 1024)))

# ── Paid-call policy knobs (APIGW-OLLAMA-DEPTH2-1, #1613) ──────────────────


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


# Comma-separated model allowlist. Empty (the default) allows any model the
# job binding permits — the per-job model check still applies.
_ALLOWED_MODELS = frozenset(m.strip() for m in os.environ.get("OLLAMA_GATE_ALLOWED_MODELS", "").split(",") if m.strip())

# Global bound on simultaneous gated upstream streams; the rest queue up to
# OLLAMA_GATE_QUEUE_TIMEOUT and then get a 429.
_MAX_CONCURRENT = max(1, _env_int("OLLAMA_GATE_MAX_CONCURRENT", 4))
_QUEUE_TIMEOUT = max(0.0, _env_float("OLLAMA_GATE_QUEUE_TIMEOUT", 30.0))
# Bound on tracked per-job locks — a caller cannot mint unbounded lock entries
# by rotating job ids (each entry is tiny, but the map must not grow forever).
_MAX_TRACKED_JOBS = max(1, _env_int("OLLAMA_GATE_MAX_TRACKED_JOBS", 4096))

# Resource ceilings for options that size VRAM/RAM/context. (env, default, min)
_MAX_NUM_CTX = max(1, _env_int("OLLAMA_GATE_MAX_NUM_CTX", 32768))
_MAX_NUM_PREDICT = max(1, _env_int("OLLAMA_GATE_MAX_NUM_PREDICT", 8192))
_MAX_NUM_GPU = max(0, _env_int("OLLAMA_GATE_MAX_NUM_GPU", 48))
_MAX_NUM_BATCH = max(1, _env_int("OLLAMA_GATE_MAX_NUM_BATCH", 256))
_MAX_NUM_THREAD = max(1, _env_int("OLLAMA_GATE_MAX_NUM_THREAD", 32))
_OPTION_CAPS: dict[str, tuple[int, int]] = {
    "num_ctx": (_MAX_NUM_CTX, 512),
    "num_predict": (_MAX_NUM_PREDICT, 1),
    "num_gpu": (_MAX_NUM_GPU, 0),
    "num_batch": (_MAX_NUM_BATCH, 1),
    "num_thread": (_MAX_NUM_THREAD, 1),
    "num_keep": (_MAX_NUM_CTX, 0),
    "repeat_last_n": (_MAX_NUM_CTX, -1),
}

# keep_alive pins a model in memory; cap the pin duration. -1 (forever) and
# durations over the cap are rejected; 0 (unload immediately) stays allowed.
_MAX_KEEP_ALIVE_SECONDS = max(0.0, _env_float("OLLAMA_GATE_MAX_KEEP_ALIVE_SECONDS", 3600.0))
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)?$")
_DURATION_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

# Paid inference routes — gated. Everything else ollama serves is not proxied.
_GATED_POSTS = ("/api/generate", "/api/chat", "/api/embed", "/api/embeddings")
_PUBLIC_GETS = ("/api/tags", "/api/version")

_HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding"}

_client: httpx.AsyncClient | None = None
# Concurrency primitives are threading-based on purpose: asyncio.Lock /
# Semaphore bind to the first event loop that awaits them, which breaks under
# per-test anyio portals; threading primitives are loop-agnostic and the
# check-and-add below is already atomic under the GIL.
_inflight = threading.BoundedSemaphore(_MAX_CONCURRENT)
_inflight_jobs: set[str] = set()
_jobs_mu = threading.Lock()


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


def _keep_alive_seconds(value: Any) -> float | None:
    """Seconds for an ollama keep_alive value, or None when out of bounds."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        match = _DURATION_RE.fullmatch(value.strip())
        if match is None:
            return None
        seconds = float(match.group(1)) * _DURATION_UNIT[match.group(2) or "s"]
    else:
        return None
    if seconds < 0 or seconds > _MAX_KEEP_ALIVE_SECONDS:
        return None
    return seconds


def _validate_options(options: Any) -> tuple[int, str] | None:
    """Bound resource-heavy ``options`` keys; other keys pass through."""
    if not isinstance(options, dict):
        return 400, "options must be an object"
    for key, value in options.items():
        cap = _OPTION_CAPS.get(str(key))
        if cap is None:
            continue
        limit, minimum = cap
        if isinstance(value, bool) or not isinstance(value, int):
            return 400, f"option {key} must be an integer"
        if value < minimum or value > limit:
            return 400, f"option {key} out of bounds"
    return None


def _validate_paid_body(payload: Any, job: dict[str, Any]) -> tuple[int, str] | None:
    """Return ``(status, error)`` when the gated request body violates policy."""
    if not isinstance(payload, dict):
        return 400, "request body must be a JSON object"
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 256:
        return 400, "model is required"
    if _ALLOWED_MODELS and model not in _ALLOWED_MODELS:
        return 403, "model is not available on this shop"
    # Job<->model binding: the access token was issued for one paid model;
    # body.model must be exactly that model. Jobs minted before the market
    # verify response carried `model` have nothing to bind against.
    job_model = job.get("model")
    if isinstance(job_model, str) and job_model and model != job_model:
        return 403, "model does not match the paid job"
    options = payload.get("options")
    if options is not None:
        error = _validate_options(options)
        if error is not None:
            return error
    if "keep_alive" in payload and _keep_alive_seconds(payload["keep_alive"]) is None:
        return 400, "keep_alive out of bounds"
    return None


async def _read_bounded_body(request: Request) -> bytes:
    """Request body under MAX_BODY_BYTES, or 413 — header check plus stream cap."""
    length = request.headers.get("content-length")
    if length is not None:
        try:
            declared = int(length)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length") from None
        if declared < 0:
            raise HTTPException(status_code=400, detail="invalid content-length")
        if declared > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request body too large")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request body too large")
        chunks.append(chunk)
    return b"".join(chunks)


async def _proxy_gated(request: Request, path: str, job: dict[str, Any]) -> Response:
    """Stream a gated POST to the ollama backend and stream the answer back."""
    assert _client is not None
    body = await _read_bounded_body(request)
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"error": "request body must be valid JSON"})
    policy_error = _validate_paid_body(payload, job)
    if policy_error is not None:
        status_code, message = policy_error
        logger.info("ollama-gate policy reject on %s: %s", path, message)
        return JSONResponse(status_code=status_code, content={"error": message})
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


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


async def _dispatch_gated(request: Request, path: str, job: dict[str, Any]) -> Response:
    """Bound concurrency: one in-flight call per job, capped globally."""
    job_id = str(job.get("job_id") or request.headers.get("X-Job-Id") or "")
    # Per-job serialization by rejection: a second call for the same paid job
    # gets an immediate 429 instead of queueing behind a possibly 10-minute
    # generate. Check-and-add is atomic — no await between them.
    with _jobs_mu:
        if job_id in _inflight_jobs:
            return _error(429, "job already has a call in flight")
        if len(_inflight_jobs) >= _MAX_TRACKED_JOBS:
            logger.warning("ollama-gate tracked-job bound reached; rejecting %s", job_id)
            return _error(429, "too many tracked jobs")
        _inflight_jobs.add(job_id)
    try:
        # The semaphore wait runs in a worker thread so the event loop is not
        # blocked; bounded so callers get a 429 instead of hanging behind a
        # long generate.
        acquired = await asyncio.to_thread(_inflight.acquire, True, _QUEUE_TIMEOUT)
        if not acquired:
            return _error(429, "gate queue timeout")
        try:
            return await _proxy_gated(request, path, job)
        finally:
            _inflight.release()  # noqa: unawaited-async — threading.BoundedSemaphore.release is sync
    finally:
        with _jobs_mu:
            _inflight_jobs.discard(job_id)


def _gated_handler(path: str):
    async def _handler(request: Request, job: Annotated[dict[str, Any], Depends(require_job_access)]) -> Response:
        return await _dispatch_gated(request, path, job)

    return _handler


for _path in _GATED_POSTS:
    # One route object per path so the OpenAPI surface names them; all share
    # the same handler and the same dependency (injected as `job` so the
    # handler can bind body.model to the paid job's model).
    app.add_api_route(_path, _gated_handler(_path), methods=["POST"])


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error on %s: %s: %s", request.url.path, type(exc).__name__, exc)
    return JSONResponse(status_code=500, content={"error": "internal gate error"})


if __name__ == "__main__":
    uvicorn.run(app, host=OLLAMA_GATE_BIND, port=OLLAMA_GATE_PORT, log_level="info")
