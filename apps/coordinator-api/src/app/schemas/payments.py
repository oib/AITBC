"""Payment-related schemas for job payments"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class JobPaymentCreate(BaseModel):
    """Request to create a payment for a job"""
    job_id: str
    amount: float
    currency: str = "AITBC"  # Jobs paid with AITBC tokens
    payment_method: str = "aitbc_token"  # Primary method for job payments
    escrow_timeout_seconds: int = 3600  # 1 hour default


class JobPaymentView(BaseModel):
    """Payment information for a job"""
    job_id: str
    payment_id: str
    amount: float
    currency: str
    status: str
    payment_method: str
    escrow_address: Optional[str] = None
    refund_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    released_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    transaction_hash: Optional[str] = None
    refund_transaction_hash: Optional[str] = None


class PaymentRequest(BaseModel):
    """Request to pay for a job"""
    job_id: str
    amount: float
    currency: str = "BTC"
    refund_address: Optional[str] = None


class PaymentReceipt(BaseModel):
    """Receipt for a payment"""
    payment_id: str
    job_id: str
    amount: float
    currency: str
    status: str
    transaction_hash: Optional[str] = None
    created_at: datetime
    verified_at: Optional[datetime] = None


class EscrowRelease(BaseModel):
    """Request to release escrow payment"""
    job_id: str
    payment_id: str
    reason: Optional[str] = None


class RefundRequest(BaseModel):
    """Request to refund a payment"""
    job_id: str
    payment_id: str
    reason: str
