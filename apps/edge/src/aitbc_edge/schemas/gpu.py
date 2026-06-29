"""GPU-related schemas for Edge API Service"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class GPUListing(SQLModel, table=True):
    """GPU listing on island"""

    __tablename__ = "gpu_listings"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"gpu_listing_{uuid4().hex[:8]}", primary_key=True)
    # v0.6.6: gpu_id and model are the primary identifiers used by service code.
    gpu_id: str = Field(default="", index=True)
    model: str = Field(default="Unknown", index=True)
    # Legacy fields — kept for backward compatibility, now optional.
    listing_id: str = Field(default="", index=True)
    island_id: str = Field(default="", index=True)
    miner_id: str = Field(default="", index=True)
    gpu_type: str = Field(default="", index=True)
    price_per_hour: float = Field(default=0.0)
    status: str = Field(default="active", index=True)  # active, inactive, booked
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # GPU specifications
    memory_gb: int | None = Field(default=None)
    cuda_version: str = Field(default="")
    region: str = Field(default="")

    # Capabilities
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=True))

    # Listing metadata
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
