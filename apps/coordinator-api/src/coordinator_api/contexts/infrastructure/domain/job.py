from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    client_id: str = Field(index=True)

    state: str = Field(default="QUEUED", max_length=20, index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    constraints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    ttl_seconds: int = Field(default=900)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    assigned_miner_id: str | None = Field(default=None, index=True)

    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt_id: str | None = Field(default=None, index=True)
    error: str | None = None

    # Payment tracking
    payment_id: str | None = Field(default=None, index=True)
    payment_status: str | None = Field(default=None, max_length=20)  # pending, escrowed, released, refunded

    # Cross-chain settlement fields
    cross_chain_payment_id: str | None = Field(default=None, index=True)
    target_chain: int | None = Field(default=None, index=True)
    requires_cross_chain_settlement: bool = Field(default=False)
    payment_chain: int | None = Field(default=None)
    preferred_bridge: str | None = Field(default=None)
    settlement_priority: str | None = Field(default=None, max_length=20)
    payment_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(36, 18)))
    payment_token: str | None = Field(default=None, max_length=42)
    settlement_gas_limit: int | None = Field(default=None)
    cross_chain_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(36, 18)))
    cross_chain_target_address: str | None = Field(default=None)

    # Settlement tracking (set during/after settlement)
    cross_chain_settlement_id: str | None = Field(default=None, index=True)
    cross_chain_bridge: str | None = Field(default=None)
    cross_chain_settlement_status: str | None = Field(default=None, max_length=20, index=True)
    cross_chain_settlement_error: str | None = Field(default=None)
    cross_chain_refund_id: str | None = Field(default=None)
    cross_chain_refund_status: str | None = Field(default=None, max_length=20)

    # G1: the quoted offer that priced and routed this job. Keeping these on the
    # job makes dispatch matching independent of payment state, so a job quoted
    # against one provider's offer cannot be executed by another just because it
    # happens to match the customer's capability constraints.
    offer_id: str | None = Field(default=None, index=True)
    provider_address: str | None = Field(default=None, index=True)

    # Completion tracking
    completed_at: datetime | None = Field(default=None)

    @property
    def completed(self) -> bool:
        """Check if job is completed"""
        return self.state == "COMPLETED"

    # Relationships
    # payment: Mapped[Optional["JobPayment"]] = relationship(back_populates="jobs")


__all__ = ["Job"]
