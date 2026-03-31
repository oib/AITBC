from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    client_id: str = Field(index=True)

    state: str = Field(default="QUEUED", max_length=20)
    payload: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    constraints: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    ttl_seconds: int = Field(default=900)
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=datetime.utcnow)

    assigned_miner_id: str | None = Field(default=None, index=True)

    result: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt_id: str | None = Field(default=None, index=True)
    error: str | None = None

    # Payment tracking
    payment_id: str | None = Field(default=None, sa_column=Column(String, ForeignKey("job_payments.id"), index=True))
    payment_status: str | None = Field(default=None, max_length=20)  # pending, escrowed, released, refunded

    # Relationships
    # payment: Mapped[Optional["JobPayment"]] = relationship(back_populates="jobs")
