"""AI Service for job operations."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import math
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import field_validator
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

from aitbc.aitbc_logging import get_logger

from .domain.jobs import Job, JobState
from .executor import ensure_schema, execute_jobs_enabled, run_executor_loop, schedule_job
from .storage import get_session

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if execute_jobs_enabled():
        await ensure_schema()
        task = asyncio.create_task(run_executor_loop(stop))
    yield
    if task is not None:
        stop.set()  # noqa: unawaited-async — asyncio.Event.set is synchronous
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="AITBC AI Service",
    description="AI job operations service",
    version="1.0.0",
    lifespan=_lifespan,
)

# The multimodal/optimization routes below are stubs: they return canned
# values and perform no real work. Every response is labelled so a caller
# cannot mistake the figures for real results (#1477).
_SIMULATION_NOTICE = "This endpoint is a stub: it returns canned values and performs no real work. Do not rely on the figures."

# Tenant isolation (#1478): client_id is never taken from the request when
# auth is on — it is derived from the bearer credential. AITBC_AI_CLIENT_KEYS
# is a comma-separated list of "api_key:client_id" pairs; each key maps to
# exactly one tenant. AITBC_AI_REQUIRE_AUTH=false restores the legacy
# unauthenticated dev mode where the client_id query param is honoured.
security = HTTPBearer(auto_error=False)
REQUIRE_AUTH = os.getenv("AITBC_AI_REQUIRE_AUTH", "true").lower() == "true"

_CLIENT_KEYS: dict[str, str] = {}
for _pair in os.getenv("AITBC_AI_CLIENT_KEYS", "").split(","):
    _key, _sep, _cid = _pair.strip().partition(":")
    if _sep and _key.strip() and _cid.strip():
        _CLIENT_KEYS[_key.strip()] = _cid.strip()
del _pair, _key, _sep, _cid


async def get_client_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    client_id: str = "default_client",
) -> str:
    """Resolve the tenant for a request.

    With auth enabled the tenant comes only from the credential mapping —
    a caller-supplied client_id is ignored, which closes the cross-tenant
    IDOR. With auth disabled (explicit dev opt-out) the query param is
    honoured as before.
    """
    if not REQUIRE_AUTH:
        return client_id
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication credentials")
    if not _CLIENT_KEYS:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI service client keys not configured")
    for key, cid in _CLIENT_KEYS.items():
        if hmac.compare_digest(credentials.credentials, key):
            return cid
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication credentials")


_TERMINAL_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELED, JobState.EXPIRED}

# #2913: bounds for the examples service — request bodies, task_data and
# per-client active jobs were all unbounded.
MAX_BODY_BYTES = int(os.getenv("AITBC_AI_MAX_BODY_BYTES", "1048576"))
TASK_DATA_MAX_BYTES = int(os.getenv("AITBC_AI_MAX_TASK_DATA_BYTES", "65536"))
MAX_ACTIVE_JOBS_PER_CLIENT = int(os.getenv("AITBC_AI_MAX_ACTIVE_JOBS", "1000"))


class _BodyTooLarge(Exception):
    pass


async def _send_413(send) -> None:
    body = b'{"detail":"request body too large"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _declared_body_length(scope) -> int:
    try:
        return int(dict(scope.get("headers") or []).get(b"content-length", b"0") or 0)
    except (TypeError, ValueError):
        return 0


class _BodySizeLimitMiddleware:
    """Pure-ASGI request-body cap (#2913).

    Rejects on a declared Content-Length up front and counts streamed
    (chunked) bodies as they are consumed — an oversized chunked body
    aborts the request rather than reaching a handler unbounded.
    """

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if _declared_body_length(scope) > self.max_bytes:
            await _send_413(send)
            return
        await self._call_http(scope, receive, send)

    async def _call_http(self, scope, receive, send) -> None:
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        response_started = False

        async def watched_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, watched_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_413(send)


app.add_middleware(_BodySizeLimitMiddleware)


async def _expire_if_due(session: AsyncSession, job: Job) -> bool:
    """Lazily transition a non-terminal job past ``expires_at`` to EXPIRED.

    Nothing else in this service reaches JobState.EXPIRED, so expiry is
    enforced on read (#1475). Returns True when the job was expired.
    """
    if job.state in _TERMINAL_STATES or job.expires_at is None:
        return False
    expires_at = job.expires_at if job.expires_at.tzinfo else job.expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) < expires_at:
        return False
    job.state = JobState.EXPIRED
    job.completed_at = datetime.now(UTC)
    await session.commit()
    return True


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "aitbc-ai"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "AITBC AI Service", "version": "1.0.0", "status": "operational"}


async def get_session_dep():
    """Dependency for database session."""
    async with get_session() as session:
        yield session


class JobCreate(SQLModel):
    task_type: str
    task_data: dict = Field(default_factory=dict)
    payment_amount: float = Field(default=0.0, ge=0)
    payment_currency: str = "aitbc_token"
    priority: int = Field(default=0, ge=-1000, le=1000)
    expires_at: datetime | None = None

    @field_validator("payment_amount")
    @classmethod
    def _payment_amount_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("payment_amount must be finite")
        return value

    @field_validator("task_data")
    @classmethod
    def _task_data_bounded(cls, value: dict) -> dict:
        # #2913: task_data lands in a DB row — bound its serialized size.
        if len(json.dumps(value, default=str)) > TASK_DATA_MAX_BYTES:
            raise ValueError(f"task_data exceeds the {TASK_DATA_MAX_BYTES}-byte cap")
        return value


class JobView(SQLModel):
    id: str
    client_id: str
    task_type: str
    state: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None
    error: str | None = None
    payment_status: str = "none"


class JobResult(SQLModel):
    id: str
    result: dict | None = None
    error: str | None = None
    completed_at: datetime | None = None
    receipt: dict | None = None


@app.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED)
async def submit_job(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    req: JobCreate,
    client_id: Annotated[str, Depends(get_client_id)],
):
    """Submit a job for execution."""
    active_count = (
        await session.execute(
            select(func.count(Job.id)).where(
                Job.client_id == client_id,
                Job.state.in_([JobState.PENDING, JobState.RUNNING]),
            )
        )
    ).scalar_one()
    if active_count >= MAX_ACTIVE_JOBS_PER_CLIENT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many active jobs for client")
    try:
        job = Job(
            client_id=client_id,
            task_type=req.task_type,
            task_data=req.task_data,
            payment_amount=req.payment_amount,
            priority=req.priority,
            expires_at=req.expires_at,
            state=JobState.PENDING,
            created_at=datetime.now(UTC),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        if execute_jobs_enabled():
            schedule_job(job.id)
        return JobView(
            id=job.id,
            client_id=job.client_id,
            task_type=job.task_type,
            state=job.state,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            error=job.error,
            payment_status=job.payment_status,
        )
    except Exception as e:
        logger.error("Submit job error: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/jobs/{job_id}", response_model=JobView)
async def get_job(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    job_id: str,
    client_id: Annotated[str, Depends(get_client_id)],
):
    """Get job status."""
    try:
        result = await session.execute(select(Job).where(Job.id == job_id, Job.client_id == client_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        await _expire_if_due(session, job)
        return JobView(
            id=job.id,
            client_id=job.client_id,
            task_type=job.task_type,
            state=job.state,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            error=job.error,
            payment_status=job.payment_status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get job error: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/jobs/{job_id}/result", response_model=JobResult)
async def get_job_result(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    job_id: str,
    client_id: Annotated[str, Depends(get_client_id)],
):
    """Get job result."""
    try:
        result = await session.execute(select(Job).where(Job.id == job_id, Job.client_id == client_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        await _expire_if_due(session, job)
        if job.state not in _TERMINAL_STATES:
            raise HTTPException(status_code=425, detail="Job not ready")
        return JobResult(id=job.id, result=job.result, error=job.error, completed_at=job.completed_at, receipt=job.receipt)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get job result error: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/jobs/{job_id}/cancel", response_model=JobView)
async def cancel_job(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    job_id: str,
    client_id: Annotated[str, Depends(get_client_id)],
):
    """Cancel a job."""
    try:
        result = await session.execute(select(Job).where(Job.id == job_id, Job.client_id == client_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        await _expire_if_due(session, job)
        if job.state in _TERMINAL_STATES:
            raise HTTPException(status_code=400, detail="Job already completed")
        job.state = JobState.CANCELED
        job.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(job)
        return JobView(
            id=job.id,
            client_id=job.client_id,
            task_type=job.task_type,
            state=job.state,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job.result,
            error=job.error,
            payment_status=job.payment_status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cancel job error: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/jobs")
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    client_id: Annotated[str, Depends(get_client_id)],
    limit: int = Query(10, ge=1, le=200),
    state: str | None = None,
):
    """List jobs with filtering."""
    try:
        query = select(Job).where(Job.client_id == client_id)
        if state:
            query = query.where(Job.state == state)
        query = query.order_by(Job.created_at.desc()).limit(limit)
        result = await session.execute(query)
        jobs = result.scalars().all()
        return {
            "jobs": [
                JobView(
                    id=job.id,
                    client_id=job.client_id,
                    task_type=job.task_type,
                    state=job.state,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    result=job.result,
                    error=job.error,
                    payment_status=job.payment_status,
                )
                for job in jobs
            ],
            "limit": limit,
            "total": len(jobs),
        }
    except Exception as e:
        logger.error("List jobs error: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/multimodal/process")
async def process_multimodal(
    request: dict[str, Any],
    client_id: Annotated[str, Depends(get_client_id)],
) -> dict[str, Any]:
    """Process multimodal AI requests (text, image, audio, video)"""
    return {
        "task_id": "multimodal_123",
        "modality": request.get("modality", "text"),
        "status": "processing",
        "result": "multimodal processing initiated",
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.post("/multimodal/benchmark")
async def benchmark_multimodal(
    request: dict[str, Any],
    client_id: Annotated[str, Depends(get_client_id)],
) -> dict[str, Any]:
    """Benchmark multimodal AI performance"""
    return {
        "benchmark_id": "bench_456",
        "modality": request.get("modality", "text"),
        "performance_score": 95.5,
        "latency_ms": 150,
        "throughput": "high",
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.get("/multimodal/agents")
async def list_multimodal_agents(client_id: Annotated[str, Depends(get_client_id)]) -> dict[str, Any]:
    """List available multimodal AI agents"""
    return {
        "agents": [
            {"id": "agent_1", "name": "Text-Image Agent", "capabilities": ["text", "image"]},
            {"id": "agent_2", "name": "Audio-Video Agent", "capabilities": ["audio", "video"]},
        ],
        "total": 2,
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.get("/multimodal/health")
async def multimodal_health(client_id: Annotated[str, Depends(get_client_id)]) -> dict[str, Any]:
    """Multi-Modal Agent Service Health"""
    return {
        "status": "healthy",
        "service": "multimodal-agent",
        "timestamp": datetime.now(UTC).isoformat(),
        "capabilities": {
            "text_processing": True,
            "image_processing": True,
            "audio_processing": True,
            "video_processing": True,
            "tabular_processing": True,
            "graph_processing": True,
        },
        "performance": {
            "text_processing_time": "0.02s",
            "image_processing_time": "0.15s",
            "audio_processing_time": "0.22s",
            "video_processing_time": "0.35s",
            "tabular_processing_time": "0.05s",
            "graph_processing_time": "0.08s",
            "average_accuracy": "94%",
        },
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.get("/multimodal/health/deep")
async def multimodal_deep_health(client_id: Annotated[str, Depends(get_client_id)]) -> dict[str, Any]:
    """Deep Multi-Modal Service Health with modality tests"""
    return {
        "status": "healthy",
        "service": "multimodal-agent",
        "timestamp": datetime.now(UTC).isoformat(),
        "modality_tests": {
            "text": {"status": "pass", "processing_time": "0.02s", "accuracy": "92%"},
            "image": {"status": "pass", "processing_time": "0.15s", "accuracy": "87%"},
            "audio": {"status": "pass", "processing_time": "0.22s", "accuracy": "89%"},
            "video": {"status": "pass", "processing_time": "0.35s", "accuracy": "85%"},
        },
        "overall_health": "pass",
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.post("/optimization/tune")
async def tune_optimization(
    request: dict[str, Any],
    client_id: Annotated[str, Depends(get_client_id)],
) -> dict[str, Any]:
    """Tune AI model optimization parameters"""
    return {
        "tuning_id": "tune_789",
        "model": request.get("model", "default"),
        "parameters": {"learning_rate": 0.001, "batch_size": 32},
        "status": "tuned",
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.post("/optimization/predict")
async def predict_optimization(
    request: dict[str, Any],
    client_id: Annotated[str, Depends(get_client_id)],
) -> dict[str, Any]:
    """Predict optimal model performance"""
    return {
        "prediction_id": "pred_101",
        "model": request.get("model", "default"),
        "expected_performance": "high",
        "estimated_accuracy": 95.5,
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.get("/optimization/agents")
async def list_optimization_agents(client_id: Annotated[str, Depends(get_client_id)]) -> dict[str, Any]:
    """List available optimization agents"""
    return {
        "agents": [
            {"id": "opt_1", "name": "Gradient Descent Optimizer", "type": "gradient"},
            {"id": "opt_2", "name": "Genetic Algorithm", "type": "evolutionary"},
        ],
        "total": 2,
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


@app.get("/optimization/health")
async def optimization_health(client_id: Annotated[str, Depends(get_client_id)]) -> dict[str, Any]:
    """Optimization Service Health"""
    return {
        "status": "healthy",
        "service": "modality-optimization",
        "timestamp": datetime.now(UTC).isoformat(),
        "capabilities": {
            "text_optimization": True,
            "image_optimization": True,
            "audio_optimization": True,
            "video_optimization": True,
        },
        "performance": {
            "optimization_speedup": "150x average",
            "memory_reduction": "60% average",
            "accuracy_retention": "95% average",
        },
        "simulated": True,
        "notice": _SIMULATION_NOTICE,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("BIND_HOST", "127.0.0.1"), port=8106)
