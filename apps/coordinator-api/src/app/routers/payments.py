"""
Payments Router - Payment processing API endpoints

Provides:
- Payment intent creation
- Payment confirmation
- Escrow management
- Refund processing
- Payment history
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from aitbc.rate_limiting import rate_limit

from ..contexts.payments.services.payments_service import get_payments_service

router = APIRouter(prefix="/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    """Request to create payment intent"""

    payer: str
    payee: str
    amount: int = Field(..., gt=0)
    currency: str = "AITBC"
    method: str = "native_token"
    description: str = ""
    escrow: bool = False
    expires_in_hours: int = 24
    metadata: dict[str, Any] | None = None


class ConfirmPaymentRequest(BaseModel):
    """Request to confirm payment"""

    payment_id: str
    tx_hash: str
    confirmations: int = 1


class ReleaseEscrowRequest(BaseModel):
    """Request to release escrow"""

    payment_id: str
    releaser: str


class RefundRequest(BaseModel):
    """Request to refund payment"""

    payment_id: str
    reason: str = ""


@router.post("/create", summary="Create payment intent")
@rate_limit(rate=30, per=60)
async def create_payment(request: Request, req: CreatePaymentRequest) -> dict[str, Any]:
    """Create a new payment intent"""
    try:
        service = get_payments_service()

        payment = service.create_payment_intent(
            payer=req.payer,
            payee=req.payee,
            amount=req.amount,
            currency=req.currency,
            method=req.method,
            description=req.description,
            metadata=req.metadata,
            escrow=req.escrow,
            expires_in_hours=req.expires_in_hours,
        )

        return {"success": True, "payment": payment.to_dict()}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create payment: {str(e)}"
        ) from e


@router.post("/confirm", summary="Confirm payment")
@rate_limit(rate=50, per=60)
async def confirm_payment(request: Request, req: ConfirmPaymentRequest) -> dict[str, Any]:
    """Confirm payment with transaction hash"""
    try:
        service = get_payments_service()

        payment = service.confirm_payment(payment_id=req.payment_id, tx_hash=req.tx_hash, confirmations=req.confirmations)

        return {"success": True, "payment": payment.to_dict()}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to confirm payment: {str(e)}"
        ) from e


@router.post("/escrow/release", summary="Release escrow")
@rate_limit(rate=20, per=60)
async def release_escrow(request: Request, req: ReleaseEscrowRequest) -> dict[str, Any]:
    """Release escrowed payment to payee"""
    try:
        service = get_payments_service()

        payment = service.release_escrow(payment_id=req.payment_id, releaser=req.releaser)

        return {"success": True, "payment": payment.to_dict(), "message": "Escrow released successfully"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to release escrow: {str(e)}"
        ) from e


@router.post("/refund", summary="Refund payment")
@rate_limit(rate=10, per=60)
async def refund_payment(request: Request, req: RefundRequest) -> dict[str, Any]:
    """Refund a payment to payer"""
    try:
        service = get_payments_service()

        payment = service.refund_payment(payment_id=req.payment_id, reason=req.reason)

        return {"success": True, "payment": payment.to_dict(), "message": "Payment refunded successfully"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to refund payment: {str(e)}"
        ) from e


@router.get("/{payment_id}", summary="Get payment details")
@rate_limit(rate=100, per=60)
async def get_payment(request: Request, payment_id: str) -> dict[str, Any]:
    """Get payment details by ID"""
    try:
        service = get_payments_service()

        payment = service.get_payment(payment_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payment {payment_id} not found")

        return payment.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get payment: {str(e)}"
        ) from e


@router.get("/", summary="List payments")
@rate_limit(rate=50, per=60)
async def list_payments(
    request: Request, payer: str | None = None, payee: str | None = None, status: str | None = None
) -> dict[str, Any]:
    """List payments with optional filters"""
    try:
        service = get_payments_service()

        payments = service.list_payments(payer=payer, payee=payee, status=status)

        return {
            "payments": [p.to_dict() for p in payments],
            "count": len(payments),
            "filters": {"payer": payer, "payee": payee, "status": status},
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # type: ignore[union-attr]
            detail=f"Failed to list payments: {str(e)}",
        ) from e


@router.get("/escrow/{escrow_id}", summary="Get escrow details")
@rate_limit(rate=100, per=60)
async def get_escrow(request: Request, escrow_id: str) -> dict[str, Any]:
    """Get escrow details by ID"""
    try:
        service = get_payments_service()

        escrow = service.get_escrow(escrow_id)
        if not escrow:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Escrow {escrow_id} not found")

        return escrow

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get escrow: {str(e)}") from e


@router.get("/stats/summary", summary="Payment statistics")
@rate_limit(rate=30, per=60)
async def get_stats(request: Request) -> dict[str, Any]:
    """Get payment platform statistics"""
    try:
        service = get_payments_service()

        return service.get_payment_stats()

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get stats: {str(e)}") from e


@router.get("/health", summary="Payments health check")
async def health_check(request: Request) -> dict[str, Any]:
    """Check payments service health"""
    try:
        service = get_payments_service()
        stats = service.get_payment_stats()

        return {"status": "healthy", "total_payments": stats["total_payments"], "total_volume": stats["total_volume"]}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
