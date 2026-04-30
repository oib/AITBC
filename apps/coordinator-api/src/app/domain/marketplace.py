from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class MarketplaceOffer(SQLModel, table=True):
    __tablename__ = "marketplaceoffer"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    sla: str = Field(default="")
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC), nullable=False, index=True)
    attributes: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # GPU-specific fields
    gpu_model: str | None = Field(default=None, index=True)
    gpu_memory_gb: int | None = Field(default=None)
    gpu_count: int | None = Field(default=1)
    cuda_version: str | None = Field(default=None)
    price_per_hour: float | None = Field(default=None)
    region: str | None = Field(default=None, index=True)


class MarketplaceBid(SQLModel, table=True):
    __tablename__ = "marketplacebid"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    notes: str | None = Field(default=None)
    status: str = Field(default="pending", nullable=False)
    submitted_at: datetime = Field(default_factory=datetime.now(datetime.UTC), nullable=False, index=True)
