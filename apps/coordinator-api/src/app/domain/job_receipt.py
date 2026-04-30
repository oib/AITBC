from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class JobReceipt(SQLModel, table=True):
    __tablename__ = "jobreceipt"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    job_id: str = Field(index=True, foreign_key="job.id")
    receipt_id: str = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC), index=True)
