from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class MarketplaceOffer(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    sla: str = Field(default="")
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    attributes: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class MarketplaceBid(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str = Field(index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    notes: Optional[str] = Field(default=None)
    status: str = Field(default="pending", nullable=False)
    submitted_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
