"""Edge serve operations router for Edge API Service"""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from aitbc.auth import AuthDep
from pydantic import BaseModel, Field

from ..config import settings
from ..services.serve_service import EscrowAlreadyUsedError, ServeService

router = APIRouter()


class SubmitComputeRequest(BaseModel):
    """Request model for submitting compute request"""

    gpu_id: str
    model_name: str
    input_data: dict[str, Any]
    priority: str = Field(default="normal")
    # v0.6.6: optional escrow ID for payment verification
    escrow_id: str | None = None
    # v0.10.1: job_id is the preferred parameter (matches blockchain escrow endpoint).
    # escrow_id is kept for backward compatibility.
    job_id: str | None = None
    # EDGE-PAY-1 (#1668): declared cost ceiling in AIT. When payment
    # verification is on, the locked escrow amount must cover it.
    expected_amount: str | None = None


def get_serve_service() -> ServeService:
    """Dependency injection for serve service"""
    return ServeService()


def _owner_scope(user: dict[str, Any]) -> str | None:
    """Owner filter for serve-object access.

    ``None`` means unrestricted (admin role, matching the #1188 ownership
    model's admin bypass); otherwise the caller's JWT ``sub`` scopes every
    list/read/cancel to requests they submitted (#1205).
    """
    if user.get("role") == "admin":
        return None
    return str(user.get("sub") or "")


def _escrow_amount_ait(escrow: dict[str, Any]) -> Decimal | None:
    """Locked AIT amount from a ``GET /rpc/escrow/{job_id}`` reply.

    The endpoint reports ``amount`` as an AIT decimal string
    (``units_to_ait``); anything unparseable means the amount check cannot
    run, so the caller treats it as "no usable amount".
    """
    raw = escrow.get("amount")
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _parse_expected_amount(raw: str) -> Decimal | None:
    """Parse the caller-declared cost ceiling; None when malformed."""
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return value


@router.post("/requests")
async def submit_compute_request(
    request: SubmitComputeRequest,
    user: AuthDep,
    svc: Annotated[ServeService, Depends(get_serve_service)],
) -> Any:
    """Submit compute request (v0.6.6: optional payment verification)"""
    # v0.6.6: verify payment before serving (feature-flagged). EDGE-PAY-1
    # (#1668): the verified escrow is no longer discarded — its key and
    # locked amount are bound to the ComputeRequest, single-use enforced by
    # a unique constraint in the service layer.
    escrow_key: str | None = None
    escrow_amount: Decimal | None = None
    if settings.require_payment_verification:
        # v0.10.1: prefer job_id (matches blockchain escrow endpoint), fall back to escrow_id
        escrow_key = request.job_id or request.escrow_id
        if not escrow_key:
            raise HTTPException(status_code=402, detail="Payment required: job_id (or escrow_id) is required")
        from aitbc.market import BlockchainRPCClient

        rpc_url = f"http://{settings.blockchain_rpc_host}:{settings.blockchain_rpc_port}"
        rpc_client = BlockchainRPCClient(
            rpc_url=rpc_url,
            api_key=settings.blockchain_rpc_api_key,
        )
        escrow = await rpc_client.verify_escrow(escrow_key)
        if not escrow or escrow.get("status") != "locked":
            raise HTTPException(status_code=402, detail="Payment required: escrow not locked")
        escrow_amount = _escrow_amount_ait(escrow)
        if request.expected_amount is not None:
            expected = _parse_expected_amount(request.expected_amount)
            if expected is None:
                raise HTTPException(status_code=422, detail="expected_amount must be a non-negative AIT decimal")
            if escrow_amount is None or escrow_amount < expected:
                raise HTTPException(status_code=402, detail="Payment required: escrow amount does not cover expected_amount")
    try:
        result = await svc.submit_compute_request(
            request.gpu_id,
            request.model_name,
            request.input_data,
            request.priority,
            owner_id=str(user.get("sub") or ""),
            escrow_id=escrow_key,
            escrow_amount=escrow_amount,
        )
    except EscrowAlreadyUsedError:
        raise HTTPException(status_code=409, detail="Escrow already bound to a compute request") from None
    return result


@router.get("/requests")
async def list_compute_requests(
    user: AuthDep,
    svc: Annotated[ServeService, Depends(get_serve_service)],
    gpu_id: str | None = None,
    status: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """List compute requests, optionally filtered — own requests only unless admin."""
    requests = await svc.list_compute_requests(gpu_id, status, owner_id=_owner_scope(user), limit=limit)
    return {"requests": requests, "total": len(requests)}


@router.get("/requests/{request_id}")
async def get_compute_request(request_id: str, user: AuthDep, svc: Annotated[ServeService, Depends(get_serve_service)]) -> Any:
    """Get compute request details — own requests only unless admin."""
    req = await svc.get_compute_request(request_id, owner_id=_owner_scope(user))
    if req is None:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return req


@router.post("/requests/{request_id}/cancel")
async def cancel_compute_request(
    request_id: str, user: AuthDep, svc: Annotated[ServeService, Depends(get_serve_service)]
) -> dict[str, str]:
    """Cancel compute request — own requests only unless admin."""
    success = await svc.cancel_compute_request(request_id, owner_id=_owner_scope(user))
    if success:
        return {"message": f"Request {request_id} cancelled"}
    else:
        raise HTTPException(status_code=400, detail=f"Request {request_id} cannot be cancelled")


@router.get("/requests/{request_id}/result")
async def get_compute_result(request_id: str, user: AuthDep, svc: Annotated[ServeService, Depends(get_serve_service)]) -> Any:
    """Get compute result — own requests only unless admin."""
    result = await svc.get_compute_result(request_id, owner_id=_owner_scope(user))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for request {request_id} not found")
    return result
