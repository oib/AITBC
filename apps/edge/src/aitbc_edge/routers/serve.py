"""Edge serve operations router for Edge API Service"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..services.serve_service import ServeService

router = APIRouter()


class SubmitComputeRequest(BaseModel):
    """Request model for submitting compute request"""

    gpu_id: str
    model_name: str
    input_data: dict[str, Any]
    priority: str = Field(default="normal")
    # v0.6.6: optional escrow ID for payment verification
    escrow_id: str | None = None


def get_serve_service() -> ServeService:
    """Dependency injection for serve service"""
    return ServeService()


@router.post("/requests")
async def submit_compute_request(
    request: SubmitComputeRequest, svc: Annotated[ServeService, Depends(get_serve_service)]
) -> Any:
    """Submit compute request (v0.6.6: optional payment verification)"""
    # v0.6.6: verify payment before serving (feature-flagged)
    if settings.require_payment_verification:
        if not request.escrow_id:
            raise HTTPException(status_code=402, detail="Payment required: escrow_id is required")
        from aitbc.marketplace import BlockchainRPCClient

        rpc_url = f"http://{settings.blockchain_rpc_host}:{settings.blockchain_rpc_port}"
        rpc_client = BlockchainRPCClient(rpc_url=rpc_url)
        escrow = await rpc_client.verify_escrow(request.escrow_id)
        if not escrow or escrow.get("status") != "locked":
            raise HTTPException(status_code=402, detail="Payment required: escrow not locked")
    result = await svc.submit_compute_request(request.gpu_id, request.model_name, request.input_data, request.priority)
    return result


@router.get("/requests")
async def list_compute_requests(
    gpu_id: str | None, status: str | None, svc: Annotated[ServeService, Depends(get_serve_service)]
) -> dict[str, Any]:
    """List compute requests, optionally filtered"""
    requests = await svc.list_compute_requests(gpu_id, status)
    return {"requests": requests, "total": len(requests)}


@router.get("/requests/{request_id}")
async def get_compute_request(request_id: str, svc: Annotated[ServeService, Depends(get_serve_service)]) -> Any:
    """Get compute request details"""
    req = await svc.get_compute_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return req


@router.post("/requests/{request_id}/cancel")
async def cancel_compute_request(request_id: str, svc: Annotated[ServeService, Depends(get_serve_service)]) -> dict[str, str]:
    """Cancel compute request"""
    success = await svc.cancel_compute_request(request_id)
    if success:
        return {"message": f"Request {request_id} cancelled"}
    else:
        raise HTTPException(status_code=400, detail=f"Request {request_id} cannot be cancelled")


@router.get("/requests/{request_id}/result")
async def get_compute_result(request_id: str, svc: Annotated[ServeService, Depends(get_serve_service)]) -> Any:
    """Get compute result"""
    result = await svc.get_compute_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for request {request_id} not found")
    return result
