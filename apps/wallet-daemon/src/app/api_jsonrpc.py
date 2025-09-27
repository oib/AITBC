from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from .deps import get_receipt_service
from .models import ReceiptVerificationModel, from_validation_result
from .receipts.service import ReceiptVerifierService

router = APIRouter(tags=["jsonrpc"])


def _response(result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None, *, request_id: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


@router.post("/rpc", summary="JSON-RPC endpoint")
def handle_jsonrpc(
    request: Dict[str, Any],
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> Dict[str, Any]:
    method = request.get("method")
    params = request.get("params") or {}
    request_id = request.get("id")

    if method == "receipts.verify_latest":
        job_id = params.get("job_id")
        if not job_id:
            return _response(error={"code": -32602, "message": "job_id required"}, request_id=request_id)
        result = service.verify_latest(str(job_id))
        if result is None:
            return _response(error={"code": -32004, "message": "receipt not found"}, request_id=request_id)
        model = from_validation_result(result)
        return _response(result=model.model_dump(), request_id=request_id)

    if method == "receipts.verify_history":
        job_id = params.get("job_id")
        if not job_id:
            return _response(error={"code": -32602, "message": "job_id required"}, request_id=request_id)
        results = [from_validation_result(item).model_dump() for item in service.verify_history(str(job_id))]
        return _response(result={"items": results}, request_id=request_id)

    return _response(error={"code": -32601, "message": "Method not found"}, request_id=request_id)
