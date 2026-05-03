"""
Multi-modal RL Router
Handles multi-modal reinforcement learning endpoints by proxying to AI service
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aitbc import AITBCHTTPClient, NetworkError

router = APIRouter(prefix="/multi-modal-rl", tags=["multi-modal-rl"])


class JobCreate(BaseModel):
    """Job creation model"""
    task_type: str
    task_data: dict = {}
    payment_amount: float = 0.0
    payment_currency: str = "aitbc_token"
    priority: int = 0


def get_ai_service_url() -> str:
    """Get AI service URL from settings"""
    try:
        from ..config import settings
        return settings.ai_service_url.rstrip("/")
    except Exception:
        return "http://localhost:8106"


@router.post("/jobs")
async def submit_job(req: JobCreate, client_id: str = "default_client") -> dict[str, Any]:
    """Submit a job for execution (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        
        # Add client_id to request data
        job_data = req.model_dump()
        job_data["client_id"] = client_id
        
        response = client.post(f"{ai_url}/jobs", json=job_data)
        return response
    except NetworkError as e:
        return {"error": f"AI service connection failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to submit job: {e}"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, client_id: str = "default_client") -> dict[str, Any]:
    """Get job status (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.get(f"{ai_url}/jobs/{job_id}", params={"client_id": client_id})
        return response
    except NetworkError as e:
        return {"error": f"AI service connection failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to get job: {e}"}


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, client_id: str = "default_client") -> dict[str, Any]:
    """Get job result (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.get(f"{ai_url}/jobs/{job_id}/result", params={"client_id": client_id})
        return response
    except NetworkError as e:
        return {"error": f"AI service connection failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to get job result: {e}"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, client_id: str = "default_client") -> dict[str, Any]:
    """Cancel a job (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        response = client.post(f"{ai_url}/jobs/{job_id}/cancel", params={"client_id": client_id})
        return response
    except NetworkError as e:
        return {"error": f"AI service connection failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to cancel job: {e}"}


@router.get("/jobs")
async def list_jobs(client_id: str = "default_client", limit: int = 10, state: str | None = None) -> dict[str, Any]:
    """List jobs with filtering (proxies to AI service)"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=10.0)
        params = {"client_id": client_id, "limit": limit}
        if state:
            params["state"] = state
        response = client.get(f"{ai_url}/jobs", params=params)
        return response
    except NetworkError as e:
        return {"error": f"AI service connection failed: {e}"}
    except Exception as e:
        return {"error": f"Failed to list jobs: {e}"}


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check for multi-modal RL router"""
    try:
        ai_url = get_ai_service_url()
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{ai_url}/health")
        return {
            "status": "healthy",
            "router": "multi-modal-rl",
            "ai_service": response
        }
    except NetworkError:
        return {
            "status": "degraded",
            "router": "multi-modal-rl",
            "ai_service": "unreachable",
            "note": "AI service not available on this node"
        }
    except Exception:
        return {
            "status": "degraded",
            "router": "multi-modal-rl",
            "ai_service": "error",
            "note": "AI service check failed"
        }
