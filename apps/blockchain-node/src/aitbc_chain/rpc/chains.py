"""RPC handlers for multi-chain management (v0.6.4).

Provides endpoints to start/stop secondary chains and list all chain
instances managed by the MultiChainManager.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from ..logger import get_logger
from ..network.multi_chain_manager import get_multi_chain_manager

_logger = get_logger(__name__)


class ChainActionRequest(BaseModel):
    """Request model for chain start/stop actions."""

    chain_id: str
    chain_type: str = "micro"  # "bilateral" or "micro"


class ChainActionResponse(BaseModel):
    """Response model for chain start/stop actions."""

    success: bool
    chain_id: str
    message: str = ""


async def start_chain(request: ChainActionRequest) -> ChainActionResponse:
    """Start a secondary chain instance."""
    mgr = get_multi_chain_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Multi-chain manager not available")
    from ..network.multi_chain_manager import ChainType

    try:
        chain_type = ChainType(request.chain_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid chain_type: {request.chain_type}") from None
    success = await mgr.start_chain(request.chain_id, chain_type=chain_type)
    if success:
        return ChainActionResponse(success=True, chain_id=request.chain_id, message="Chain started successfully")
    chain = mgr.get_chain_status(request.chain_id)
    msg = chain.error_message if chain else "Unknown error"
    return ChainActionResponse(success=False, chain_id=request.chain_id, message=msg)


async def stop_chain(request: ChainActionRequest) -> ChainActionResponse:
    """Stop a secondary chain instance."""
    mgr = get_multi_chain_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Multi-chain manager not available")
    success = await mgr.stop_chain(request.chain_id)
    if success:
        return ChainActionResponse(success=True, chain_id=request.chain_id, message="Chain stopped successfully")
    chain = mgr.get_chain_status(request.chain_id)
    msg = chain.error_message if chain else "Unknown error"
    return ChainActionResponse(success=False, chain_id=request.chain_id, message=msg)


async def list_chains() -> dict[str, Any]:
    """List all chain instances managed by the MultiChainManager."""
    mgr = get_multi_chain_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Multi-chain manager not available")
    chains = []
    for chain in mgr.get_all_chains():
        chains.append(
            {
                "chain_id": chain.chain_id,
                "chain_type": chain.chain_type.value,
                "status": chain.status.value,
                "rpc_port": chain.rpc_port,
                "p2p_port": chain.p2p_port,
                "started_at": chain.started_at,
                "error_message": chain.error_message,
            }
        )
    return {"chains": chains, "total": len(chains)}
