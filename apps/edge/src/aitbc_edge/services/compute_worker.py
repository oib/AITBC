"""Background compute worker for the Edge API Service.

The worker polls the ``compute_requests`` queue, executes queued requests,
creates ``ComputeResult`` records, and updates request status.  By default it
uses a lightweight stub executor so the end-to-end ``submit -> queue -> result``
flow works without an external inference backend.  A real Ollama executor can
be enabled with ``EDGE_WORKER_EXECUTOR=ollama``.
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlmodel import select

from aitbc.aitbc_logging import get_logger

from ..config import settings
from ..schemas.serve import ComputeRequest, ComputeResult
from ..storage import get_session

logger = get_logger(__name__)

# Default result cache TTL; mirrors ComputeResult.cache_ttl default.
DEFAULT_CACHE_TTL_SECONDS = 3600


def _island_id() -> str:
    """Return a stable island ID for this edge node."""
    return settings.island_id or "default"


def _extract_prompt(input_data: dict[str, Any]) -> str:
    """Extract a text prompt from request input data."""
    if not input_data:
        return ""
    for key in ("prompt", "text", "input", "query"):
        if key in input_data and isinstance(input_data[key], str):
            return input_data[key]
    return json.dumps(input_data)


def _execute_stub(request: ComputeRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    """Simulate a compute execution and return deterministic output."""
    output_data = {
        "result": "ok",
        "model": request.model_name,
        "gpu_id": request.gpu_id,
        "input_data": request.input_data,
        "message": f"Simulated execution of {request.model_name} on {request.gpu_id}",
    }
    metrics = {
        "gpu_utilization": 0,
        "memory_used_mb": 0,
        "simulated": True,
    }
    return output_data, metrics


async def _execute_ollama(request: ComputeRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute a request against a local Ollama instance."""
    prompt = _extract_prompt(request.input_data)
    payload = {
        "model": request.model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 128},
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()

    output_data = {
        "response": data.get("response", ""),
        "model": request.model_name,
        "done": data.get("done", False),
    }
    metrics = {
        "prompt_eval_count": data.get("prompt_eval_count", 0),
        "eval_count": data.get("eval_count", 0),
        "total_duration_ns": data.get("total_duration", 0),
    }
    return output_data, metrics


async def _execute_request(
    request: ComputeRequest,
) -> tuple[dict[str, Any], dict[str, Any], float, bool, str | None]:
    """Run a single compute request and return output/metrics/status."""
    start = time.time()
    try:
        executor = settings.edge_worker_executor.lower()
        if executor == "ollama":
            output_data, metrics = await _execute_ollama(request)
        else:
            if executor != "stub":
                logger.warning("Unknown edge worker executor %r, using stub", executor)
            output_data, metrics = _execute_stub(request)

        execution_time = time.time() - start
        metrics["execution_time_seconds"] = round(execution_time, 4)
        return output_data, metrics, execution_time, True, None
    except Exception as exc:
        execution_time = time.time() - start
        error = str(exc)
        output_data = {"error": error}
        metrics = {"execution_time_seconds": round(execution_time, 4)}
        logger.exception("Compute request %s execution failed", request.request_id)
        return output_data, metrics, execution_time, False, error


async def _mark_request_status(
    request_id: str, status: str, started_at: datetime | None = None, error: str | None = None
) -> None:
    """Load and update the status of a compute request."""
    async with get_session() as session:
        result = await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))
        request = result.scalar_one_or_none()
        if request is None:
            logger.warning("Request %s not found while updating status", request_id)
            return

        request.status = status
        request.updated_at = datetime.now(UTC)
        if started_at is not None:
            request.started_at = started_at
        if error is not None:
            request.error = error
        await session.commit()


async def _execute_and_store(request_id: str) -> None:
    """Execute a queued request and persist the result."""
    async with get_session() as session:
        result = await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))
        request = result.scalar_one_or_none()
        if request is None:
            logger.warning("Request %s not found", request_id)
            return
        if request.status != "queued":
            return

        request.status = "running"
        request.started_at = datetime.now(UTC)
        request.updated_at = datetime.now(UTC)
        await session.commit()
        # Keep the ORM object attached while we execute so attribute access works.
        await session.refresh(request)

        output_data, metrics, _execution_time, success, error = await _execute_request(request)

        request.completed_at = datetime.now(UTC)
        request.updated_at = datetime.now(UTC)
        if success:
            request.status = "completed"
            request.error = None
        else:
            request.status = "failed"
            request.error = error

        result_status = "completed" if success else "failed"
        now = datetime.now(UTC)
        compute_result = ComputeResult(
            result_id=f"res_{uuid4().hex[:8]}",
            request_id=request_id,
            island_id=_island_id(),
            gpu_id=request.gpu_id,
            result={"output": output_data, "status": result_status},
            output_data=output_data,
            metrics=metrics,
            status=result_status,
            extra_data={"executor": settings.edge_worker_executor},
            created_at=now,
            expires_at=now + timedelta(seconds=DEFAULT_CACHE_TTL_SECONDS),
        )
        session.add(compute_result)
        await session.commit()

    logger.info(
        "Compute request %s finished with status %s (executor=%s)",
        request_id,
        result_status,
        settings.edge_worker_executor,
    )


async def process_queued_requests() -> int:
    """Poll the queue and process all queued requests."""
    async with get_session() as session:
        result = await session.execute(
            select(ComputeRequest).where(ComputeRequest.status == "queued").order_by(ComputeRequest.created_at)
        )
        queued = list(result.scalars().all())

    if not queued:
        return 0

    count = 0
    for request in queued:
        request_id = request.request_id
        try:
            await _execute_and_store(request_id)
            count += 1
        except Exception as exc:
            logger.exception("Failed to process queued request %s: %s", request_id, exc)
            try:
                await _mark_request_status(request_id, "failed", error=str(exc))
            except Exception as mark_exc:
                logger.exception("Could not mark request %s as failed: %s", request_id, mark_exc)
    return count


async def run_compute_worker() -> None:
    """Main worker loop."""
    if not settings.edge_worker_enabled:
        logger.info("Edge compute worker is disabled")
        return

    logger.info(
        "Starting edge compute worker (executor=%s, poll_interval=%s)",
        settings.edge_worker_executor,
        settings.edge_worker_poll_interval,
    )
    while True:
        try:
            processed = await process_queued_requests()
            if processed:
                logger.info("Edge compute worker processed %d request(s)", processed)
        except Exception:
            logger.exception("Edge compute worker iteration failed")
        await asyncio.sleep(settings.edge_worker_poll_interval)
