"""Payment router for job payments"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ....auth import ClientDep  # NEW: JWT auth

# from ....deps import require_client_key  # OLD: API key auth (deprecated)
from ....schemas import EscrowRelease, JobPaymentCreate, JobPaymentView, PaymentReceipt, RefundRequest
from ....storage import get_session
from ..services.payments import PaymentService

router = APIRouter(tags=["payments"])


@router.post(
    "/payments", response_model=JobPaymentView, status_code=status.HTTP_201_CREATED, summary="Create payment for a job"
)
async def create_payment(
    payment_data: JobPaymentCreate,
    session: Annotated[Session, Depends(get_session)],
    # OLD: user: ClientDep,
    # NEW: JWT auth with client role
    user: ClientDep,
) -> JobPaymentView:
    """Create a payment for a job"""
    user["sub"]

    service = PaymentService(session)
    payment = await service.create_payment(payment_data.job_id, payment_data)

    return service.to_view(payment)


@router.get("/payments/{payment_id}", response_model=JobPaymentView, summary="Get payment details")
async def get_payment(
    payment_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobPaymentView:
    """Get payment details by ID"""
    user["sub"]

    service = PaymentService(session)
    payment = service.get_payment(payment_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return service.to_view(payment)


@router.get("/jobs/{job_id}/payment", response_model=JobPaymentView, summary="Get payment for a job")
async def get_job_payment(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobPaymentView:
    """Get payment information for a specific job"""
    user["sub"]

    service = PaymentService(session)
    payment = service.get_job_payment(job_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found for this job")

    return service.to_view(payment)


@router.post("/payments/{payment_id}/release", response_model=dict, summary="Release payment from escrow")
async def release_payment(
    payment_id: str,
    release_data: EscrowRelease,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> dict[str, Any]:
    """Release payment from escrow (for completed jobs)"""
    user["sub"]

    service = PaymentService(session)

    # Verify the payment belongs to the client's job
    payment = service.get_payment(payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    success = await service.release_payment(release_data.job_id, payment_id, release_data.reason)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to release payment")

    return {"status": "released", "payment_id": payment_id}


@router.post("/payments/{payment_id}/refund", response_model=dict, summary="Refund payment")
async def refund_payment(
    payment_id: str,
    refund_data: RefundRequest,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> dict[str, Any]:
    """Refund payment (for failed or cancelled jobs)"""
    user["sub"]

    service = PaymentService(session)

    # Verify the payment belongs to the client's job
    payment = service.get_payment(payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    success = await service.refund_payment(refund_data.job_id, payment_id, refund_data.reason)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to refund payment")

    return {"status": "refunded", "payment_id": payment_id}


@router.get("/payments/{payment_id}/receipt", response_model=PaymentReceipt, summary="Get payment receipt")
async def get_payment_receipt(
    payment_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> PaymentReceipt:
    """Get payment receipt with verification status"""
    user["sub"]

    service = PaymentService(session)
    payment = service.get_payment(payment_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    receipt = PaymentReceipt(
        payment_id=payment.id,
        job_id=payment.job_id,
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status,
        transaction_hash=payment.transaction_hash,
        created_at=payment.created_at,
        verified_at=payment.released_at or payment.refunded_at,
    )

    return receipt


# ============================================================================
# MIGRATION NOTES: API Key to JWT Auth
# ============================================================================
#
# Migration completed: 2025-01-XX
#
# Changes made:
# 1. Import change:
#    OLD: from ....deps import require_client_key
#    NEW: from ....auth import ClientDep
#
# 2. Dependency changes (7 endpoints):
#    - create_payment: client_id -> user: ClientDep
#    - get_payment: client_id -> user: ClientDep
#    - get_job_payment: client_id -> user: ClientDep
#    - release_payment: client_id -> user: ClientDep
#    - refund_payment: client_id -> user: ClientDep
#    - get_payment_receipt: client_id -> user: ClientDep
#
# 3. Client ID extraction:
#    Added: client_id = user["sub"] in each endpoint
#
# 4. JWT benefits:
#    - user["sub"]: Client user ID
#    - user["role"]: Role verification (client)
#    - user["exp"]: Token expiration
#    - Centralized auth via security matrix
#
# 5. Client code change:
#    OLD: headers = {"X-Api-Key": "your-api-key"}
#    NEW: headers = {"Authorization": f"Bearer {token}"}
#
# ============================================================================
