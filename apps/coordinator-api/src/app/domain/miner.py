from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Miner(SQLModel, table=True):
    __tablename__ = "miner"
    __table_args__ = {"extend_existing": True}

    id: str = Field(primary_key=True, index=True)
    region: str | None = Field(default=None, index=True)
    capabilities: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    concurrency: int = Field(default=1)
    status: str = Field(default="ONLINE", index=True)
    inflight: int = Field(default=0)
    extra_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    session_token: str | None = None
    last_job_at: datetime | None = Field(default=None, index=True)
    jobs_completed: int = Field(default=0)
    jobs_failed: int = Field(default=0)
    total_job_duration_ms: int = Field(default=0)
    average_job_duration_ms: float = Field(default=0.0)
    last_receipt_id: str | None = Field(default=None, index=True)
