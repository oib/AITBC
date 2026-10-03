"""GPU resource state models for blockchain tracking."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Session, select

from ..metadata import ChainBase

GPU_STATUS_DEACTIVATED = "deactivated"


class GPURegistration(ChainBase, table=True):
    """On-chain GPU registration record with immutable specs."""

    __tablename__ = "gpu_registration"
    __table_args__ = (UniqueConstraint("chain_id", "gpu_id", name="uix_gpu_registration_chain_gpu"),)

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
    price_per_hour: Decimal = Field(default=Decimal("0"), max_digits=20, decimal_places=8)
    registered_by: str = Field(index=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    status: str = Field(default="active")  # active, deactivated
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GPUAllocation(ChainBase, table=True):
    """On-chain GPU allocation/booking record."""

    __tablename__ = "gpu_allocation"
    __table_args__ = (UniqueConstraint("chain_id", "allocation_id", name="uix_gpu_allocation_chain_id"),)

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    allocation_id: str = Field(index=True)
    gpu_id: str = Field(index=True)
    client_id: str = Field(index=True)
    duration_hours: float = Field(default=0.0)
    total_cost: Decimal = Field(default=Decimal("0"), max_digits=20, decimal_places=8)
    status: str = Field(default="active", index=True)  # active, completed, cancelled
    allocated_by: str = Field(index=True)
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EdgeNodeRegistration(ChainBase, table=True):
    """On-chain edge node registration record (v0.6.6)."""

    __tablename__ = "edge_node_registration"
    __table_args__ = (UniqueConstraint("chain_id", "node_id", name="uix_edge_node_chain_node"),)

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


GPU_ID_BEARING_TYPES = frozenset({"GPU_REGISTER", "GPU_ALLOCATE"})


def retired_gpu_error(tx_type: str, payload: Any, retired_ids: frozenset[str]) -> str | None:
    """Why a GPU_REGISTER or GPU_ALLOCATE may not name its ``gpu_id`` (it is retired), or None.

    Refused unconditionally at admission (``GPU_RETIRED_IDS``) and, from ``block_version`` 10
    on, at consensus validation too — below v10 a block carrying one still replays as before.
    Any other type, a payload that is not an object, or a missing ``gpu_id`` is left to the
    validation that already handles it. Ids compare exactly, as consensus compares them.
    """
    if not retired_ids or tx_type not in GPU_ID_BEARING_TYPES or not isinstance(payload, dict):
        return None
    gpu_id = payload.get("gpu_id")
    if isinstance(gpu_id, str) and gpu_id in retired_ids:
        return f"{tx_type} for GPU {gpu_id} is refused: that id is retired on this chain"
    return None


def gpu_deregister_error(session: Session, chain_id: str, payload: Any, sender_addr: str) -> str | None:
    """Why ``sender_addr`` may not deregister the GPU named in ``payload`` (v10 rules), or None when it may.

    The single definition of the rule: ``StateTransition.validate_transaction`` applies it at block time and
    mempool admission applies it at the door, so a transaction the proposer would drop is refused up front.
    """
    if not isinstance(payload, dict):
        return "GPU_DEREGISTER payload must be an object"
    gpu_id = payload.get("gpu_id")
    if not isinstance(gpu_id, str) or not gpu_id:
        return "GPU_DEREGISTER payload must include gpu_id"
    row = session.exec(
        select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == gpu_id)
    ).first()
    if row is None:
        return f"GPU not found: {gpu_id}"
    if not row.registered_by:
        return f"GPU {gpu_id} has no registrant on record; removal is not permitted"
    if canonical_address(row.registered_by) != canonical_address(sender_addr):
        return f"GPU_DEREGISTER for {gpu_id} must come from its registrant {row.registered_by}, got {sender_addr}"
    if row.status == GPU_STATUS_DEACTIVATED:
        return f"GPU {gpu_id} is already deactivated"
    return None


def gpu_allocate_deactivated_error(session: Session, chain_id: str, payload: Any) -> str | None:
    """Why a ``GPU_ALLOCATE`` may not name its ``gpu_id`` (the row is deactivated), or None.

    The single definition of the v10 rule: ``StateTransition.validate_transaction`` applies it at block
    time and mempool admission applies it at the door, so a transaction the proposer would drop is
    refused up front. Every other ``GPU_ALLOCATE`` payload problem stays with the check that already
    owns it, so a non-dict payload or a missing ``gpu_id`` is left alone here; an unknown row and an
    active one are both fine.
    """
    if not isinstance(payload, dict):
        return None
    gpu_id = payload.get("gpu_id")
    if gpu_id is None:
        return None
    target = session.exec(
        select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == str(gpu_id))
    ).first()
    if target is not None and target.status == GPU_STATUS_DEACTIVATED:
        return f"GPU {gpu_id} is deactivated; it takes no new allocations"
    return None
