"""Payment domain model"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, JSON
from sqlalchemy.orm import Mapped, relationship
from sqlmodel import Field, SQLModel


class JobPayment(SQLModel, table=True):
    """Payment record for a job"""
    
    __tablename__ = "job_payments"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    job_id: str = Field(index=True)
    
    # Payment details
    amount: float = Field(sa_column=Column(Numeric(20, 8), nullable=False))
    currency: str = Field(default="AITBC", max_length=10)
    status: str = Field(default="pending", max_length=20)
    payment_method: str = Field(default="aitbc_token", max_length=20)
    
    # Addresses
    escrow_address: Optional[str] = Field(default=None, max_length=100)
    refund_address: Optional[str] = Field(default=None, max_length=100)
    
    # Transaction hashes
    transaction_hash: Optional[str] = Field(default=None, max_length=100)
    refund_transaction_hash: Optional[str] = Field(default=None, max_length=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    escrowed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Additional metadata
    meta_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Relationships
    # jobs: Mapped[List["Job"]] = relationship(back_populates="payment")


class PaymentEscrow(SQLModel, table=True):
    """Escrow record for holding payments"""
    
    __tablename__ = "payment_escrows"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    payment_id: str = Field(index=True)
    
    # Escrow details
    amount: float = Field(sa_column=Column(Numeric(20, 8), nullable=False))
    currency: str = Field(default="AITBC", max_length=10)
    address: str = Field(max_length=100)
    
    # Status
    is_active: bool = Field(default=True)
    is_released: bool = Field(default=False)
    is_refunded: bool = Field(default=False)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    released_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
