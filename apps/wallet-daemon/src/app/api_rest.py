from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .deps import get_receipt_service
from .models import (
    ReceiptVerificationListResponse,
    ReceiptVerificationModel,
    ReceiptVerifyResponse,
    SignatureValidationModel,
    from_validation_result,
)
from .receipts.service import ReceiptValidationResult, ReceiptVerifierService

router = APIRouter(prefix="/v1", tags=["receipts"])


def _result_to_response(result: ReceiptValidationResult) -> ReceiptVerifyResponse:
    payload = from_validation_result(result)
    return ReceiptVerifyResponse(result=payload)


@router.get(
    "/receipts/{job_id}",
    response_model=ReceiptVerifyResponse,
    summary="Verify latest receipt for a job",
)
def verify_latest_receipt(
    job_id: str,
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> ReceiptVerifyResponse:
    result = service.verify_latest(job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="receipt not found")
    return _result_to_response(result)


@router.get(
    "/receipts/{job_id}/history",
    response_model=ReceiptVerificationListResponse,
    summary="Verify all historical receipts for a job",
)
def verify_receipt_history(
    job_id: str,
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> ReceiptVerificationListResponse:
    results = service.verify_history(job_id)
    items = [from_validation_result(result) for result in results]
    return ReceiptVerificationListResponse(items=items)
