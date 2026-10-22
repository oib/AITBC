"""GPU resource RPC endpoints for AITBC blockchain."""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..chain_id import resolve_chain_id
from ..metrics import metrics_registry
from .escrow_routes import verify_rpc_api_key
from .router import router


class GPURegistrationRequest(BaseModel):
    """Signed GPU_REGISTER envelope — kept for API shape compatibility.

    The route no longer writes ``gpu_registration`` rows itself (FORK-OOB-1,
    issue #382): a direct insert committed state on exactly the node that
    served the call, diverging that node's side-table fingerprint at the next
    block. Send a signed ``GPU_REGISTER`` transaction in ``tx`` instead; the
    row appears on every node when it seals.
    """

    tx: dict[str, Any] | None = Field(default=None, description="Signed GPU_REGISTER transaction envelope")


class GPUAllocationRequest(BaseModel):
    """Signed GPU_ALLOCATE envelope — see :class:`GPURegistrationRequest`.

    ``allocation_id`` must be carried in the transaction payload by the
    caller (e.g. ``alloc_<uuid>``); the route no longer generates it. It is
    readable from the sealed transaction/row after the block commits.
    """

    tx: dict[str, Any] | None = Field(default=None, description="Signed GPU_ALLOCATE transaction envelope")


def _require_signed_gpu_tx(body: dict[str, Any], tx_type: str) -> dict[str, Any]:
    """Return the signed ``tx`` envelope or refuse with a 4xx.

    The unsigned legacy shape (bare registration/allocation fields) is not
    accepted: nothing unsigned may write a committed table outside a block.
    """
    tx = body.get("tx")
    if not isinstance(tx, dict):
        raise HTTPException(
            status_code=400,
            detail=(
                f"send {{'tx': <signed {tx_type} envelope>}} — this route submits "
                "transactions; the state row lands when the block seals "
                "(unsigned field bodies are refused, FORK-OOB-1/#382)"
            ),
        )
    if tx.get("type") != tx_type:
        raise HTTPException(status_code=400, detail=f"tx.type must be {tx_type}")
    if not tx.get("signature"):
        raise HTTPException(status_code=400, detail=f"tx.signature is required for {tx_type}")
    if not tx.get("from"):
        raise HTTPException(status_code=400, detail=f"tx.from is required for {tx_type}")
    return tx


async def _submit_gpu_tx(tx: dict[str, Any], tx_type: str) -> str:
    """Submit a signed GPU_* transaction via market admission; return its hash."""
    from aitbc.network import SharedHttpClient

    from .escrow_routes import _HUB_RPC_URL

    resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/market", json=tx, timeout=10.0)
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"{tx_type} submission failed: {resp.status_code} {resp.text[:200]}")
    result = resp.json()
    tx_hash = result.get("transaction_hash")
    if not tx_hash:
        raise HTTPException(status_code=400, detail=f"{tx_type} accepted but no transaction_hash returned")
    return str(tx_hash)


@router.get("/gpus", summary="List all registered GPUs", tags=["gpu_resources"])
async def list_gpus(chain_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List all GPUs registered on blockchain."""
    if chain_id is None:
        chain_id = resolve_chain_id()

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
                        "registered_by": g.registered_by,
                        "model": g.model,
                        "memory_gb": g.memory_gb,
                        "region": g.region,
                        "price_per_hour": str(g.price_per_hour),
                        "status": g.status,
                        "registered_at": g.registered_at.isoformat() if g.registered_at else None,
                    }
                    for g in gpus
                ],
                "total": len(gpus),
            }

    except Exception as e:
        metrics_registry.increment("rpc_gpu_list_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/gpu/allocations/{gpu_id}", summary="Query GPU allocations", tags=["gpu_resources"])
async def get_gpu_allocations(gpu_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Query GPU allocations from blockchain."""
    if chain_id is None:
        chain_id = resolve_chain_id()

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
                        "total_cost": str(a.total_cost),
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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/gpu/register",
    summary="Register GPU on-chain",
    tags=["gpu_resources"],
    dependencies=[Depends(verify_rpc_api_key)],
)
async def register_gpu(request: GPURegistrationRequest, chain_id: str | None = None) -> dict[str, Any]:
    """Submit a signed GPU_REGISTER transaction.

    FORK-OOB-1/#382: this route no longer writes the ``gpu_registration``
    row itself — a direct insert committed state on exactly the node that
    served the call, diverging that node's committed fingerprint at the
    next block (the escrow-phantom shape). The row lands fleet-wide when
    the signed transaction seals.
    """
    if chain_id is None:
        chain_id = resolve_chain_id()

    try:
        metrics_registry.increment("rpc_gpu_register_total")
        tx = _require_signed_gpu_tx(request.model_dump(), "GPU_REGISTER")
        if tx.get("chain_id") not in (None, chain_id):
            raise HTTPException(status_code=400, detail=f"tx.chain_id {tx['chain_id']!r} does not match {chain_id!r}")
        tx_hash = await _submit_gpu_tx(tx, "GPU_REGISTER")
        return {
            "gpu_id": (tx.get("payload") or {}).get("gpu_id"),
            "status": "submitted",
            "tx_hash": tx_hash,
            "message": "GPU_REGISTER accepted to mempool; the registration row lands when the block seals",
        }
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_gpu_register_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/gpu/info/{gpu_id}", summary="Query GPU registration", tags=["gpu_resources"])
async def get_gpu(gpu_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Query GPU registration from blockchain."""
    # Use env var or provided chain_id
    if chain_id is None:
        chain_id = resolve_chain_id()

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
                "price_per_hour": str(gpu.price_per_hour),
                "registered_by": gpu.registered_by,
                "registered_at": gpu.registered_at.isoformat() if gpu.registered_at else None,
                "status": gpu.status,
            }

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_gpu_get_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post(
    "/gpu/allocate",
    summary="Allocate GPU on-chain",
    tags=["gpu_resources"],
    dependencies=[Depends(verify_rpc_api_key)],
)
async def allocate_gpu(request: GPUAllocationRequest, chain_id: str | None = None) -> dict[str, Any]:
    """Submit a signed GPU_ALLOCATE transaction.

    Same committed-table rule as ``register_gpu`` (FORK-OOB-1/#382): the
    ``gpu_allocation`` row lands fleet-wide when the signed transaction
    seals. ``payload.allocation_id`` is required — the caller picks it
    (``alloc_<uuid>`` is the existing convention) and reads it back from
    the sealed transaction.
    """
    if chain_id is None:
        chain_id = resolve_chain_id()

    try:
        metrics_registry.increment("rpc_gpu_allocate_total")
        tx = _require_signed_gpu_tx(request.model_dump(), "GPU_ALLOCATE")
        if tx.get("chain_id") not in (None, chain_id):
            raise HTTPException(status_code=400, detail=f"tx.chain_id {tx['chain_id']!r} does not match {chain_id!r}")
        allocation_id = (tx.get("payload") or {}).get("allocation_id")
        if not allocation_id:
            raise HTTPException(
                status_code=400,
                detail="GPU_ALLOCATE tx.payload must carry allocation_id (caller-generated, e.g. alloc_<uuid>)",
            )
        tx_hash = await _submit_gpu_tx(tx, "GPU_ALLOCATE")
        return {
            "allocation_id": allocation_id,
            "gpu_id": (tx.get("payload") or {}).get("gpu_id"),
            "status": "submitted",
            "tx_hash": tx_hash,
            "message": "GPU_ALLOCATE accepted to mempool; the allocation row lands when the block seals",
        }
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_gpu_allocate_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# ============================================================================
# v0.6.6: Edge node registration endpoints
# ============================================================================


class EdgeNodeRegistrationRequest(BaseModel):
    """Request to register an edge node on-chain (v0.6.6)."""

    node_id: str = Field(..., description="Edge node unique identifier")
    endpoint: str = Field(default="", description="Edge service endpoint URL")
    region: str = Field(default="", description="Geographic region")
    gpu_count: int = Field(default=0, ge=0, description="Number of GPUs")
    total_vram: int = Field(default=0, ge=0, description="Total VRAM in GB")
    capabilities: list[Any] = Field(default_factory=list, description="Node capabilities")
    registered_by: str = Field(..., description="Wallet address of registrant")


@router.post(
    "/edge/register",
    summary="Register edge node on-chain",
    tags=["gpu_resources"],
    dependencies=[Depends(verify_rpc_api_key)],
)
async def register_edge_node(request: EdgeNodeRegistrationRequest, chain_id: str | None = None) -> dict[str, Any]:
    """Register an edge node on the blockchain (v0.6.6)."""
    if chain_id is None:
        chain_id = resolve_chain_id()

    try:
        metrics_registry.increment("rpc_edge_register_total")

        from ..database import session_scope
        from ..state.gpu_resources import EdgeNodeRegistration

        with session_scope() as session:
            from sqlalchemy import and_, select

            result = session.execute(
                select(EdgeNodeRegistration).where(
                    and_(
                        EdgeNodeRegistration.chain_id == chain_id,  # type: ignore[arg-type]
                        EdgeNodeRegistration.node_id == request.node_id,  # type: ignore[arg-type]
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.endpoint = request.endpoint
                existing.region = request.region
                existing.gpu_count = request.gpu_count
                existing.total_vram = request.total_vram
                existing.capabilities = request.capabilities
                existing.status = "active"
                existing.updated_at = datetime.now(UTC)
                session.commit()
                return {"node_id": request.node_id, "status": "updated", "message": "Edge node registration updated on-chain"}

            registration = EdgeNodeRegistration(
                chain_id=chain_id,
                node_id=request.node_id,
                endpoint=request.endpoint,
                region=request.region,
                gpu_count=request.gpu_count,
                total_vram=request.total_vram,
                capabilities=request.capabilities,
                registered_by=request.registered_by,
                registered_at=datetime.now(UTC),
                status="active",
            )
            session.add(registration)
            session.commit()

            return {
                "node_id": request.node_id,
                "status": "registered",
                "message": "Edge node registered on-chain successfully",
            }

    except Exception as e:
        metrics_registry.increment("rpc_edge_register_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/edge/info/{node_id}", summary="Query edge node registration", tags=["gpu_resources"])
async def get_edge_node(node_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Query edge node registration from blockchain (v0.6.6)."""
    if chain_id is None:
        chain_id = resolve_chain_id()

    try:
        metrics_registry.increment("rpc_edge_get_total")

        from ..database import session_scope
        from ..state.gpu_resources import EdgeNodeRegistration

        with session_scope() as session:
            from sqlalchemy import and_, select

            result = session.execute(
                select(EdgeNodeRegistration).where(
                    and_(
                        EdgeNodeRegistration.chain_id == chain_id,  # type: ignore[arg-type]
                        EdgeNodeRegistration.node_id == node_id,  # type: ignore[arg-type]
                    )
                )
            )
            node = result.scalar_one_or_none()

            if not node:
                raise HTTPException(status_code=404, detail=f"Edge node {node_id} not found")

            return {
                "node_id": node.node_id,
                "endpoint": node.endpoint,
                "region": node.region,
                "gpu_count": node.gpu_count,
                "total_vram": node.total_vram,
                "capabilities": node.capabilities,
                "registered_by": node.registered_by,
                "status": node.status,
                "registered_at": node.registered_at.isoformat() if node.registered_at else None,
            }

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_edge_get_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
