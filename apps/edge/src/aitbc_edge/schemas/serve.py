"""Edge serve-related schemas for Edge API Service"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class ComputeRequest(SQLModel, table=True):
    """Compute request in edge serve queue"""

    __tablename__ = "compute_requests"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"compute_req_{uuid4().hex[:8]}", primary_key=True)
    request_id: str = Field(index=True)
    gpu_id: str = Field(index=True)
    model_name: str
    input_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
    priority: str = Field(default="normal")
    status: str = Field(default="queued", index=True)  # queued, running, completed, failed, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    error: str | None = Field(default=None)
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))


class ComputeResult(SQLModel, table=True):
    """Compute result cache"""

    __tablename__ = "compute_results"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"compute_res_{uuid4().hex[:8]}", primary_key=True)
    result_id: str = Field(index=True)
    request_id: str = Field(index=True)
    island_id: str = Field(index=True)
    gpu_id: str
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    cache_ttl: int = Field(default=3600)  # 1 hour default
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=datetime.utcnow)
