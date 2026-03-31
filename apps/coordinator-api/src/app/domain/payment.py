"""Payment domain model"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel


class JobPayment(SQLModel, table=True):
    """Payment record for a job"""

    __tablename__ = "job_payments"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    job_id: str = Field(index=True)

    # Payment details
    amount: float = Field(sa_column=Column(Numeric(20, 8), nullable=False))
    currency: str = Field(default="AITBC", max_length=10)
    status: str = Field(default="pending", max_length=20)
    payment_method: str = Field(default="aitbc_token", max_length=20)

    # Addresses
    escrow_address: str | None = Field(default=None, max_length=100)
    refund_address: str | None = Field(default=None, max_length=100)

    # Transaction hashes
    transaction_hash: str | None = Field(default=None, max_length=100)
    refund_transaction_hash: str | None = Field(default=None, max_length=100)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    escrowed_at: datetime | None = None
    released_at: datetime | None = None
    refunded_at: datetime | None = None
    expires_at: datetime | None = None

    # Additional metadata
    meta_data: dict | None = Field(default=None, sa_column=Column(JSON))

    # Relationships
    # jobs: Mapped[List["Job"]] = relationship(back_populates="payment")


class PaymentEscrow(SQLModel, table=True):
    """Escrow record for holding payments"""

    __tablename__ = "payment_escrows"
    __table_args__ = {"extend_existing": True}

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
    released_at: datetime | None = None
    refunded_at: datetime | None = None
    expires_at: datetime | None = None
