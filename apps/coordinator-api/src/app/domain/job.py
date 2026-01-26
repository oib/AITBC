from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel, Relationship

from ..types import JobState


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    client_id: str = Field(index=True)

    state: JobState = Field(default=JobState.queued, sa_column_kwargs={"nullable": False})
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    constraints: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    ttl_seconds: int = Field(default=900)
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=datetime.utcnow)

    assigned_miner_id: Optional[str] = Field(default=None, index=True)

    result: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt_id: Optional[str] = Field(default=None, index=True)
    error: Optional[str] = None
    
    # Payment tracking
    payment_id: Optional[str] = Field(default=None, foreign_key="job_payments.id", index=True)
    payment_status: Optional[str] = Field(default=None, max_length=20)  # pending, escrowed, released, refunded
    
    # Relationships
    payment: Optional["JobPayment"] = Relationship(back_populates="jobs")
