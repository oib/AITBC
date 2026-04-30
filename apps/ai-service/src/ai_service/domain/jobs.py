"""Domain models for AI job operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class JobState(StrEnum):
    """Job execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    EXPIRED = "expired"


class Job(SQLModel, table=True):
    """AI job model."""

    __tablename__ = "jobs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"job_{uuid4().hex[:12]}", primary_key=True)
    client_id: str = Field(index=True)
    task_type: str = Field(index=True)
    task_data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    state: JobState = Field(default=JobState.PENDING, index=True)
    result: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: str | None = Field(default=None)
    
    # Payment information
    payment_id: str | None = Field(default=None, index=True)
    payment_amount: float = Field(default=0.0)
    payment_status: str = Field(default="none", index=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    requested_at: datetime | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    
    # Metadata
    priority: int = Field(default=0)
    assigned_miner_id: str | None = Field(default=None, index=True)
    receipt: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt_id: str | None = Field(default=None)


class JobReceipt(SQLModel, table=True):
    """Job receipts for verification."""

    __tablename__ = "job_receipts"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"rcpt_{uuid4().hex[:12]}", primary_key=True)
    job_id: str = Field(index=True)
    miner_id: str = Field(index=True)
    result: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    metrics: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    signature: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
