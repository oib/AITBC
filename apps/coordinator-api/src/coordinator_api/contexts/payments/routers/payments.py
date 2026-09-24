"""Payment router for job payments"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from ....auth import AdminOrClientDep  # NEW: JWT auth

# from ....deps import require_client_key  # OLD: API key auth (deprecated)
from ....schemas import EscrowRelease, JobPaymentCreate, JobPaymentView, PaymentReceipt, RefundRequest
from ....storage import get_session
from ..operations import begin_operation, complete_operation, fail_operation, record_rejection
from ..services.payments import PaymentService

router = APIRouter(tags=["payments"])


@router.post(
    "/payments", response_model=JobPaymentView, status_code=status.HTTP_201_CREATED, summary="Create payment for a job"
)
async def create_payment(
    payment_data: JobPaymentCreate,
    session: Annotated[Session, Depends(get_session)],
    # OLD: user: AdminOrClientDep,
    # NEW: JWT auth with client role
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Create a payment for a job"""
    client_id = user["sub"]

    key, attempt, early = await begin_operation(
        request,
        "create_payment",
        {"client_id": client_id, "body": payment_data.model_dump(mode="python")},
    )
    if early is not None:
        return early

    service = PaymentService(session)
    try:
        payment = await service.create_payment(client_id, payment_data.job_id, payment_data)
        result = service.to_view(payment)
        # Record exactly what response_model=JobPaymentView would emit so a
        # replay is byte-identical (Decimal fields, defaulted optionals).
        await complete_operation(
            key, attempt, JobPaymentView.model_validate(result).model_dump(mode="json"), response_status=201
        )
        return result
    except HTTPException as e:
        await record_rejection(key, attempt, e.status_code, {"detail": e.detail})
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise


@router.get("/payments/{payment_id}", response_model=JobPaymentView, summary="Get payment details")
async def get_payment(
    payment_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
) -> JobPaymentView:
    """Get payment details by ID"""
    client_id = user["sub"]

    service = PaymentService(session)
    payment = service.get_payment(client_id, payment_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return service.to_view(payment)


@router.get("/jobs/{job_id}/payment", response_model=JobPaymentView, summary="Get payment for a job")
async def get_job_payment(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
) -> JobPaymentView:
    """Get payment information for a specific job"""
    client_id = user["sub"]

    service = PaymentService(session)
    payment = service.get_job_payment(client_id, job_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found for this job")

    return service.to_view(payment)


@router.post("/payments/{payment_id}/release", response_model=dict, summary="Release payment from escrow")
async def release_payment(
    payment_id: str,
    release_data: EscrowRelease,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Release payment from escrow (for completed jobs)"""
    client_id = user["sub"]

    key, attempt, early = await begin_operation(
        request,
        "release_payment",
        {"client_id": client_id, "payment_id": payment_id, "body": release_data.model_dump(mode="python")},
    )
    if early is not None:
        return early

    service = PaymentService(session)
    try:
        # Verify the payment belongs to the client's job
        payment = service.get_payment(client_id, payment_id)
        if not payment:
            await record_rejection(key, attempt, status.HTTP_404_NOT_FOUND, {"detail": "Payment not found"})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        success = await service.release_payment(client_id, release_data.job_id, payment_id, release_data.reason)

        if not success:
            await record_rejection(key, attempt, status.HTTP_400_BAD_REQUEST, {"detail": "Failed to release payment"})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to release payment")

        result = {"status": "released", "payment_id": payment_id}
        await complete_operation(key, attempt, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise


@router.post("/payments/{payment_id}/refund", response_model=dict, summary="Refund payment")
async def refund_payment(
    payment_id: str,
    refund_data: RefundRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
    request: Request,
) -> Any:
    """Refund payment (for failed or cancelled jobs)"""
    client_id = user["sub"]

    key, attempt, early = await begin_operation(
        request,
        "refund_payment",
        {"client_id": client_id, "payment_id": payment_id, "body": refund_data.model_dump(mode="python")},
    )
    if early is not None:
        return early

    service = PaymentService(session)
    try:
        # Verify the payment belongs to the client's job
        payment = service.get_payment(client_id, payment_id)
        if not payment:
            await record_rejection(key, attempt, status.HTTP_404_NOT_FOUND, {"detail": "Payment not found"})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        success = await service.refund_payment(client_id, refund_data.job_id, payment_id, refund_data.reason)

        if not success:
            await record_rejection(key, attempt, status.HTTP_400_BAD_REQUEST, {"detail": "Failed to refund payment"})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to refund payment")

        result = {"status": "refunded", "payment_id": payment_id}
        await complete_operation(key, attempt, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        await fail_operation(key, attempt, type(e).__name__)
        raise


@router.get("/payments/{payment_id}/receipt", response_model=PaymentReceipt, summary="Get payment receipt")
async def get_payment_receipt(
    payment_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
) -> PaymentReceipt:
    """Get payment receipt with verification status"""
    client_id = user["sub"]

    service = PaymentService(session)
    payment = service.get_payment(client_id, payment_id)

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    receipt = PaymentReceipt(
        payment_id=payment.id,
        job_id=payment.job_id,
        amount=payment.amount,
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
#    NEW: from ....auth import AdminOrClientDep
#
# 2. Dependency changes (7 endpoints):
#    - create_payment: client_id -> user: AdminOrClientDep
#    - get_payment: client_id -> user: AdminOrClientDep
#    - get_job_payment: client_id -> user: AdminOrClientDep
#    - release_payment: client_id -> user: AdminOrClientDep
#    - refund_payment: client_id -> user: AdminOrClientDep
#    - get_payment_receipt: client_id -> user: AdminOrClientDep
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
