"""
Multi-modal RL Router
Handles multi-modal reinforcement learning endpoints by proxying to AI service
"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError, NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.rate_limiting import rate_limit

from ....auth import AuthDep
from ....config import settings

logger = get_logger(__name__)
router = APIRouter(prefix="/multi-modal-rl", tags=["multi-modal-rl"])

_OPS_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    AITBCError,
)


class JobCreate(BaseModel):
    """Job creation model"""

    task_type: str
    task_data: dict = {}
    payment_amount: Decimal = Decimal("0.0")
    payment_currency: str = "aitbc_token"
    priority: int = 0


def get_ai_service_url() -> str:
    """Configured AI engine upstream (AI_SERVICE_URL, default :8005)."""
    return settings.ai_service_url.rstrip("/")


def _effective_client_id(user: dict[str, Any], client_id: str | None) -> str:
    """Bind client_id to the caller — a foreign id is a 403, admins may pass one."""
    if user.get("role") == "admin":
        return client_id or str(user.get("sub") or "admin")
    sub = str(user.get("sub") or "")
    if client_id is not None and client_id != sub:
        raise HTTPException(status_code=403, detail="cannot act for another client_id")
    return sub


@router.post("/jobs")
@rate_limit(rate=20, per=60)
def submit_job(request: Request, req: JobCreate, user: AuthDep, client_id: str | None = None) -> dict[str, Any]:
    """Submit a job for execution (proxies to AI service)"""
    effective_client_id = _effective_client_id(user, client_id)
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        job_data = req.model_dump()
        job_data["client_id"] = effective_client_id
        # payment_amount is Decimal — the wire payload needs JSON-native
        # types or httpx's encoder raises before the upstream is even tried
        # (#3084). jsonable_encoder is the repo's Decimal boundary (#1635).
        return client.post(f"{ai_url}/jobs", json=jsonable_encoder(job_data))
    except NetworkError as e:
        logger.error("AI service connection failed: %s", e)
        raise HTTPException(status_code=502, detail="AI service unreachable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to submit job: %s", e)
        raise HTTPException(status_code=500, detail="Failed to submit job") from e


@router.get("/jobs/{job_id}")
@rate_limit(rate=200, per=60)
def get_job(request: Request, job_id: str, user: AuthDep, client_id: str | None = None) -> dict[str, Any]:
    """Get job status (proxies to AI service)"""
    effective_client_id = _effective_client_id(user, client_id)
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        return client.get(f"{ai_url}/jobs/{job_id}", params={"client_id": effective_client_id})
    except NetworkError as e:
        logger.error("AI service connection failed: %s", e)
        raise HTTPException(status_code=502, detail="AI service unreachable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to get job: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get job") from e


@router.get("/jobs/{job_id}/result")
@rate_limit(rate=200, per=60)
def get_job_result(request: Request, job_id: str, user: AuthDep, client_id: str | None = None) -> dict[str, Any]:
    """Get job result (proxies to AI service)"""
    effective_client_id = _effective_client_id(user, client_id)
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        return client.get(f"{ai_url}/jobs/{job_id}/result", params={"client_id": effective_client_id})
    except NetworkError as e:
        logger.error("AI service connection failed: %s", e)
        raise HTTPException(status_code=502, detail="AI service unreachable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to get job result: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get job result") from e


@router.post("/jobs/{job_id}/cancel")
@rate_limit(rate=20, per=60)
def cancel_job(request: Request, job_id: str, user: AuthDep, client_id: str | None = None) -> dict[str, Any]:
    """Cancel a job (proxies to AI service)"""
    effective_client_id = _effective_client_id(user, client_id)
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        return client.post(f"{ai_url}/jobs/{job_id}/cancel", data={"client_id": effective_client_id})
    except NetworkError as e:
        logger.error("AI service connection failed: %s", e)
        raise HTTPException(status_code=502, detail="AI service unreachable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to cancel job: %s", e)
        raise HTTPException(status_code=500, detail="Failed to cancel job") from e


@router.get("/jobs")
@rate_limit(rate=200, per=60)
def list_jobs(
    request: Request, user: AuthDep, client_id: str | None = None, limit: int = 10, state: str | None = None
) -> dict[str, Any]:
    """List jobs with filtering (proxies to AI service)"""
    effective_client_id = _effective_client_id(user, client_id)
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        params = {"client_id": effective_client_id, "limit": limit}
        if state:
            params["state"] = state
        return client.get(f"{ai_url}/jobs", params=params)
    except NetworkError as e:
        logger.error("AI service connection failed: %s", e)
        raise HTTPException(status_code=502, detail="AI service unreachable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to list jobs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list jobs") from e


@router.get("/health")
@rate_limit(rate=1000, per=60)
def health(request: Request) -> dict[str, Any]:
    """Health check for multi-modal RL router"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{ai_url}/health")
        return {"status": "healthy", "router": "multi-modal-rl", "ai_service": response}
    except NetworkError:
        return {
            "status": "degraded",
            "router": "multi-modal-rl",
            "ai_service": "unreachable",
            "note": "AI service not available on this node",
        }
    except _OPS_ERRORS as e:
        logger.error("AI service check failed: %s", e)
        return {"status": "degraded", "router": "multi-modal-rl", "ai_service": "error", "note": "AI service check failed"}
