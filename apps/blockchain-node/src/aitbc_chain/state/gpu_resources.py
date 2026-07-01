"""GPU resource state models for blockchain tracking."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class GPURegistration(SQLModel, table=True):
    """On-chain GPU registration record with immutable specs."""

    __tablename__ = "gpu_registration"
    __table_args__ = (UniqueConstraint("chain_id", "gpu_id", name="uix_gpu_registration_chain_gpu"), {"extend_existing": True})

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    gpu_id: str = Field(index=True)
    miner_id: str = Field(index=True)
    model: str = Field(index=True)
    memory_gb: int = Field(default=0)
    cuda_version: str = Field(default="")
    region: str = Field(default="", index=True)
    capabilities: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    price_per_hour: float = Field(default=0.0)
    registered_by: str = Field(index=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    status: str = Field(default="active")  # active, deactivated
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GPUAllocation(SQLModel, table=True):
    """On-chain GPU allocation/booking record."""

    __tablename__ = "gpu_allocation"
    __table_args__ = (
        UniqueConstraint("chain_id", "allocation_id", name="uix_gpu_allocation_chain_id"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    allocation_id: str = Field(index=True)
    gpu_id: str = Field(index=True)
    client_id: str = Field(index=True)
    duration_hours: float = Field(default=0.0)
    total_cost: float = Field(default=0.0)
    status: str = Field(default="active", index=True)  # active, completed, cancelled
    allocated_by: str = Field(index=True)
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EdgeNodeRegistration(SQLModel, table=True):
    """On-chain edge node registration record (v0.6.6)."""

    __tablename__ = "edge_node_registration"
    __table_args__ = (
        UniqueConstraint("chain_id", "node_id", name="uix_edge_node_chain_node"),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    node_id: str = Field(index=True)
    endpoint: str = Field(default="")
    region: str = Field(default="", index=True)
    gpu_count: int = Field(default=0)
    total_vram: int = Field(default=0)
    capabilities: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    registered_by: str = Field(index=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    status: str = Field(default="active", index=True)  # active, deactivated
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
