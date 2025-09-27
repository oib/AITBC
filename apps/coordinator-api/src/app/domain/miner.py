from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Miner(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    region: Optional[str] = Field(default=None, index=True)
    capabilities: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    concurrency: int = Field(default=1)
    status: str = Field(default="ONLINE", index=True)
    inflight: int = Field(default=0)
    extra_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow, index=True)
    session_token: Optional[str] = None
    last_job_at: Optional[datetime] = Field(default=None, index=True)
    jobs_completed: int = Field(default=0)
    jobs_failed: int = Field(default=0)
    total_job_duration_ms: int = Field(default=0)
    average_job_duration_ms: float = Field(default=0.0)
    last_receipt_id: Optional[str] = Field(default=None, index=True)
