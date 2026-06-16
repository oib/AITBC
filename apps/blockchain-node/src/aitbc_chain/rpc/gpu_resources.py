"""GPU resource RPC endpoints for AITBC blockchain."""

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..metrics import metrics_registry
from .router import router


class GPURegistrationRequest(BaseModel):
    """Request to register GPU on-chain."""

    gpu_id: str = Field(..., description="GPU unique identifier")
    miner_id: str = Field(..., description="Miner/provider ID")
    model: str = Field(..., description="GPU model (e.g., RTX 4090)")
    memory_gb: int = Field(..., ge=0, description="GPU memory in GB")
    cuda_version: str = Field(default="", description="CUDA version")
    region: str = Field(default="", description="Geographic region")
    capabilities: list[Any] = Field(default_factory=list, description="GPU capabilities")
    price_per_hour: float = Field(..., ge=0, description="Price per hour in AIT")
    registered_by: str = Field(..., description="Wallet address of registrant")


class GPUAllocationRequest(BaseModel):
    """Request to allocate GPU on-chain."""

    gpu_id: str = Field(..., description="GPU ID to allocate")
    client_id: str = Field(..., description="Client wallet address")
    duration_hours: float = Field(..., ge=0, description="Allocation duration in hours")
    total_cost: float = Field(..., ge=0, description="Total cost in AIT")
    allocated_by: str = Field(..., description="Wallet address of allocator")


@router.get("/gpus", summary="List all registered GPUs", tags=["gpu_resources"])
async def list_gpus(chain_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List all GPUs registered on blockchain."""
    if chain_id is None:
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    try:
        metrics_registry.increment("rpc_gpu_list_total")

        from ..database import session_scope
        from ..state.gpu_resources import GPURegistration

        with session_scope() as session:
            from sqlalchemy import select

            query = select(GPURegistration).where(GPURegistration.chain_id == chain_id)  # type: ignore[arg-type]

            if status:
                query = query.where(GPURegistration.status == status)  # type: ignore[arg-type]

            result = session.execute(query)
            gpus = result.scalars().all()

            return {
                "gpus": [
                    {
                        "gpu_id": g.gpu_id,
                        "miner_id": g.miner_id,
                        "model": g.model,
                        "memory_gb": g.memory_gb,
                        "region": g.region,
                        "price_per_hour": g.price_per_hour,
                        "status": g.status,
                        "registered_at": g.registered_at.isoformat() if g.registered_at else None,
                    }
                    for g in gpus
                ],
                "total": len(gpus),
            }

    except Exception as e:
        metrics_registry.increment("rpc_gpu_list_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/gpu/allocations/{gpu_id}", summary="Query GPU allocations", tags=["gpu_resources"])
async def get_gpu_allocations(gpu_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Query GPU allocations from blockchain."""
    if chain_id is None:
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    try:
        metrics_registry.increment("rpc_gpu_allocations_get_total")

        from ..database import session_scope
        from ..state.gpu_resources import GPUAllocation

        with session_scope() as session:
            from sqlalchemy import and_, select

            result = session.execute(
                select(GPUAllocation).where(
                    and_(
                        GPUAllocation.chain_id == chain_id,  # type: ignore[arg-type]
                        GPUAllocation.gpu_id == gpu_id,  # type: ignore[arg-type]
                    )
                )
            )
            allocations = result.scalars().all()

            return {
                "gpu_id": gpu_id,
                "allocations": [
                    {
                        "allocation_id": a.allocation_id,
                        "client_id": a.client_id,
                        "duration_hours": a.duration_hours,
                        "total_cost": a.total_cost,
                        "status": a.status,
                        "allocated_by": a.allocated_by,
                        "allocated_at": a.allocated_at.isoformat() if a.allocated_at else None,
                        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                    }
                    for a in allocations
                ],
                "total": len(allocations),
            }

    except Exception as e:
        metrics_registry.increment("rpc_gpu_allocations_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/gpu/register", summary="Register GPU on-chain", tags=["gpu_resources"])
async def register_gpu(request: GPURegistrationRequest, chain_id: str | None = None) -> dict[str, Any]:
    """Register GPU with immutable specs on blockchain."""
    # Use env var or provided chain_id
    if chain_id is None:
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    try:
        metrics_registry.increment("rpc_gpu_register_total")

        from ..database import session_scope
        from ..state.gpu_resources import GPURegistration

        with session_scope() as session:
            # Check if GPU already registered
            from sqlalchemy import and_, select

            result = session.execute(
                select(GPURegistration).where(
                    and_(
                        GPURegistration.chain_id == chain_id,  # type: ignore[arg-type]
                        GPURegistration.gpu_id == request.gpu_id,  # type: ignore[arg-type]
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing registration
                existing.model = request.model
                existing.memory_gb = request.memory_gb
                existing.cuda_version = request.cuda_version
                existing.region = request.region
                existing.capabilities = request.capabilities
                existing.price_per_hour = request.price_per_hour
                existing.status = "active"
                existing.updated_at = datetime.now(UTC)
                session.commit()
                return {"gpu_id": request.gpu_id, "status": "updated", "message": "GPU registration updated on-chain"}

            # Create new registration
            registration = GPURegistration(
                chain_id=chain_id,
                gpu_id=request.gpu_id,
                miner_id=request.miner_id,
                model=request.model,
                memory_gb=request.memory_gb,
                cuda_version=request.cuda_version,
                region=request.region,
                capabilities=request.capabilities,
                price_per_hour=request.price_per_hour,
                registered_by=request.registered_by,
                registered_at=datetime.now(UTC),
                status="active",
            )
            session.add(registration)
            session.commit()

            return {"gpu_id": request.gpu_id, "status": "registered", "message": "GPU registered on-chain successfully"}

    except Exception as e:
        metrics_registry.increment("rpc_gpu_register_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/gpu/info/{gpu_id}", summary="Query GPU registration", tags=["gpu_resources"])
async def get_gpu(gpu_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Query GPU registration from blockchain."""
    # Use env var or provided chain_id
    if chain_id is None:
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    try:
        metrics_registry.increment("rpc_gpu_get_total")

        from ..database import session_scope
        from ..state.gpu_resources import GPURegistration

        with session_scope() as session:
            from sqlalchemy import and_, select

            result = session.execute(
                select(GPURegistration).where(
                    and_(
                        GPURegistration.chain_id == chain_id,  # type: ignore[arg-type]
                        GPURegistration.gpu_id == gpu_id,  # type: ignore[arg-type]
                    )
                )
            )
            gpu = result.scalar_one_or_none()

            if not gpu:
                raise HTTPException(status_code=404, detail="GPU not found on-chain")

            return {
                "gpu_id": gpu.gpu_id,
                "miner_id": gpu.miner_id,
                "model": gpu.model,
                "memory_gb": gpu.memory_gb,
                "cuda_version": gpu.cuda_version,
                "region": gpu.region,
                "capabilities": gpu.capabilities,
                "price_per_hour": gpu.price_per_hour,
                "registered_by": gpu.registered_by,
                "registered_at": gpu.registered_at.isoformat() if gpu.registered_at else None,
                "status": gpu.status,
            }

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_gpu_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/gpu/allocate", summary="Allocate GPU on-chain", tags=["gpu_resources"])
async def allocate_gpu(request: GPUAllocationRequest, chain_id: str | None = None) -> dict[str, Any]:
    """Record GPU allocation on blockchain."""
    # Use env var or provided chain_id
    if chain_id is None:
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    try:
        metrics_registry.increment("rpc_gpu_allocate_total")

        from ..database import session_scope
        from ..state.gpu_resources import GPUAllocation

        with session_scope() as session:
            # Generate allocation ID
            allocation_id = f"alloc_{uuid4().hex[:12]}"

            # Create allocation record
            allocation = GPUAllocation(
                chain_id=chain_id,
                allocation_id=allocation_id,
                gpu_id=request.gpu_id,
                client_id=request.client_id,
                duration_hours=request.duration_hours,
                total_cost=request.total_cost,
                status="active",
                allocated_by=request.allocated_by,
                allocated_at=datetime.now(UTC),
            )
            session.add(allocation)
            session.commit()

            return {
                "allocation_id": allocation_id,
                "gpu_id": request.gpu_id,
                "status": "allocated",
                "message": "GPU allocation recorded on-chain",
            }

    except Exception as e:
        metrics_registry.increment("rpc_gpu_allocate_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e
