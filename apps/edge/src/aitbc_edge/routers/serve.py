"""Edge serve operations router for Edge API Service"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.serve_service import ServeService

router = APIRouter()


class SubmitComputeRequest(BaseModel):
    """Request model for submitting compute request"""
    gpu_id: str
    model_name: str
    input_data: dict
    priority: str = Field(default="normal")


def get_serve_service() -> ServeService:
    """Dependency injection for serve service"""
    return ServeService()


@router.post("/requests")
async def submit_compute_request(request: SubmitComputeRequest, svc: ServeService = Depends(get_serve_service)) -> Any:
    """Submit compute request"""
    result = await svc.submit_compute_request(request.gpu_id, request.model_name, request.input_data, request.priority)
    return result


@router.get("/requests")
async def list_compute_requests(gpu_id: str = Query(None), status: str = Query(None), svc: ServeService = Depends(get_serve_service)) -> dict[str, Any]:
    """List compute requests, optionally filtered"""
    requests = await svc.list_compute_requests(gpu_id, status)
    return {"requests": requests, "total": len(requests)}


@router.get("/requests/{request_id}")
async def get_compute_request(request_id: str, svc: ServeService = Depends(get_serve_service)) -> Any:
    """Get compute request details"""
    req = await svc.get_compute_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return req


@router.post("/requests/{request_id}/cancel")
async def cancel_compute_request(request_id: str, svc: ServeService = Depends(get_serve_service)) -> dict[str, str]:
    """Cancel compute request"""
    success = await svc.cancel_compute_request(request_id)
    if success:
        return {"message": f"Request {request_id} cancelled"}
    else:
        raise HTTPException(status_code=400, detail=f"Request {request_id} cannot be cancelled")


@router.get("/requests/{request_id}/result")
async def get_compute_result(request_id: str, svc: ServeService = Depends(get_serve_service)) -> Any:
    """Get compute result"""
    result = await svc.get_compute_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for request {request_id} not found")
    return result
