"""Edge serve-related schemas for Edge API Service"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class ComputeRequest(SQLModel, table=True):
    """Compute request in edge serve queue"""
    
    __tablename__ = "compute_requests"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"compute_req_{uuid4().hex[:8]}", primary_key=True)
    request_id: str = Field(index=True)
    island_id: str = Field(index=True)
    gpu_type: str
    status: str = Field(default="pending", index=True)  # pending, processing, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Request parameters
    model_name: str
    input_data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
    
    # Processing info
    assigned_gpu_id: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    
    # Result
    result: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: str | None = Field(default=None)


class ComputeResult(SQLModel, table=True):
    """Compute result cache"""
    
    __tablename__ = "compute_results"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"compute_res_{uuid4().hex[:8]}", primary_key=True)
    result_id: str = Field(index=True)
    request_id: str = Field(index=True)
    island_id: str = Field(index=True)
    gpu_id: str
    result: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    cache_ttl: int = Field(default=3600)  # 1 hour default
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
