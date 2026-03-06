"""Payment router for job payments"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from ..deps import require_client_key
from ..schemas import (
    JobPaymentCreate,
    JobPaymentView,
    PaymentRequest,
    PaymentReceipt,
    EscrowRelease,
    RefundRequest
)
from ..services.payments import PaymentService
from ..storage import SessionDep

router = APIRouter(tags=["payments"])


@router.post("/payments", response_model=JobPaymentView, status_code=status.HTTP_201_CREATED, summary="Create payment for a job")
async def create_payment(
    payment_data: JobPaymentCreate,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> JobPaymentView:
    """Create a payment for a job"""
    
    service = PaymentService(session)
    payment = await service.create_payment(payment_data.job_id, payment_data)
    
    return service.to_view(payment)


@router.get("/payments/{payment_id}", response_model=JobPaymentView, summary="Get payment details")
async def get_payment(
    payment_id: str,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> JobPaymentView:
    """Get payment details by ID"""
    
    service = PaymentService(session)
    payment = service.get_payment(payment_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    return service.to_view(payment)


@router.get("/jobs/{job_id}/payment", response_model=JobPaymentView, summary="Get payment for a job")
async def get_job_payment(
    job_id: str,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> JobPaymentView:
    """Get payment information for a specific job"""
    
    service = PaymentService(session)
    payment = service.get_job_payment(job_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found for this job"
        )
    
    return service.to_view(payment)


@router.post("/payments/{payment_id}/release", response_model=dict, summary="Release payment from escrow")
async def release_payment(
    payment_id: str,
    release_data: EscrowRelease,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> dict:
    """Release payment from escrow (for completed jobs)"""
    
    service = PaymentService(session)
    
    # Verify the payment belongs to the client's job
    payment = service.get_payment(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    success = await service.release_payment(
        release_data.job_id,
        payment_id,
        release_data.reason
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to release payment"
        )
    
    return {"status": "released", "payment_id": payment_id}


@router.post("/payments/{payment_id}/refund", response_model=dict, summary="Refund payment")
async def refund_payment(
    payment_id: str,
    refund_data: RefundRequest,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> dict:
    """Refund payment (for failed or cancelled jobs)"""
    
    service = PaymentService(session)
    
    # Verify the payment belongs to the client's job
    payment = service.get_payment(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    success = await service.refund_payment(
        refund_data.job_id,
        payment_id,
        refund_data.reason
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refund payment"
        )
    
    return {"status": "refunded", "payment_id": payment_id}


@router.get("/payments/{payment_id}/receipt", response_model=PaymentReceipt, summary="Get payment receipt")
async def get_payment_receipt(
    payment_id: str,
    session: SessionDep,
    client_id: str = Depends(require_client_key()),
) -> PaymentReceipt:
    """Get payment receipt with verification status"""
    
    service = PaymentService(session)
    payment = service.get_payment(payment_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    receipt = PaymentReceipt(
        payment_id=payment.id,
        job_id=payment.job_id,
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status,
        transaction_hash=payment.transaction_hash,
        created_at=payment.created_at,
        verified_at=payment.released_at or payment.refunded_at
    )
    
    return receipt
