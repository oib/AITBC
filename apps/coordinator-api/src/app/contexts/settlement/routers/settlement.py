"""
Settlement router for cross-chain settlements
"""

import asyncio
from typing import Any

from app.settlement.manager import BridgeManager  # type: ignore
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep  # NEW: JWT auth (miners handle settlements)

# from ....auth import get_api_key  # OLD: API key auth (deprecated)

router = APIRouter(prefix="/settlement", tags=["settlement"])


class CrossChainSettlementRequest(BaseModel):
    """Request model for cross-chain settlement"""

    source_chain_id: str = Field(..., description="Source blockchain ID")
    target_chain_id: str = Field(..., description="Target blockchain ID")
    amount: float = Field(..., gt=0, description="Amount to settle")
    asset_type: str = Field(..., description="Asset type (e.g., 'AITBC', 'ETH')")
    recipient_address: str = Field(..., description="Recipient address on target chain")
    gas_limit: int | None = Field(None, description="Gas limit for transaction")
    gas_price: float | None = Field(None, description="Gas price in Gwei")


class CrossChainSettlementResponse(BaseModel):
    """Response model for cross-chain settlement"""

    settlement_id: str = Field(..., description="Unique settlement identifier")
    status: str = Field(..., description="Settlement status")
    transaction_hash: str | None = Field(None, description="Transaction hash on target chain")
    estimated_completion: str | None = Field(None, description="Estimated completion time")
    created_at: str = Field(..., description="Creation timestamp")


@router.post("/cross-chain", response_model=CrossChainSettlementResponse)
@rate_limit(rate=20, per=60)
async def initiate_cross_chain_settlement(
    request: Request,
    settlement_request: CrossChainSettlementRequest,
    background_tasks: BackgroundTasks,
    user: MinerDep,
) -> CrossChainSettlementResponse:
    """Initiate a cross-chain settlement"""
    try:
        # Initialize settlement manager
        manager = BridgeManager()

        # Create settlement
        settlement_id = await manager.create_settlement(
            source_chain_id=request.source_chain_id,  # type: ignore[attr-defined]
            target_chain_id=request.target_chain_id,  # type: ignore[attr-defined]
            amount=request.amount,  # type: ignore[attr-defined]
            asset_type=request.asset_type,  # type: ignore[attr-defined]
            recipient_address=request.recipient_address,  # type: ignore[attr-defined]
            gas_limit=request.gas_limit,  # type: ignore[attr-defined]
            gas_price=request.gas_price,  # type: ignore[attr-defined]
        )

        # Add background task to process settlement
        background_tasks.add_task(manager.process_settlement, settlement_id, user["sub"])

        return CrossChainSettlementResponse(
            settlement_id=settlement_id,
            status="pending",
            estimated_completion="~5 minutes",
            created_at=asyncio.get_event_loop().time(),
        )

    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Settlement failed: {str(e)}") from e


@router.get("/cross-chain/{settlement_id}")
@rate_limit(rate=200, per=60)
async def get_settlement_status(
    request: Request,
    settlement_id: str,
    user: MinerDep,
) -> dict[str, Any]:
    """Get settlement status"""
    try:
        manager = BridgeManager()
        settlement = await manager.get_settlement(settlement_id)

        if not settlement:
            raise HTTPException(status_code=404, detail="Settlement not found")

        return {
            "settlement_id": settlement.id,
            "status": settlement.status,
            "transaction_hash": settlement.tx_hash,
            "created_at": settlement.created_at,
            "completed_at": settlement.completed_at,
            "error_message": settlement.error_message,
        }

    except HTTPException:
        raise
    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settlement: {str(e)}") from e


@router.get("/cross-chain")
@rate_limit(rate=200, per=60)
async def list_settlements(
    request: Request,
    user: MinerDep,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List settlements with pagination"""
    try:
        manager = BridgeManager()
        settlements = await manager.list_settlements(api_key=user["sub"], limit=limit, offset=offset)

        return {"settlements": settlements, "total": len(settlements), "limit": limit, "offset": offset}

    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to list settlements: {str(e)}") from e


@router.delete("/cross-chain/{settlement_id}")
@rate_limit(rate=20, per=60)
async def cancel_settlement(
    request: Request,
    settlement_id: str,
    user: MinerDep,
) -> dict[str, str]:
    """Cancel a pending settlement"""
    try:
        manager = BridgeManager()
        success = await manager.cancel_settlement(settlement_id, user["sub"])

        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel settlement")

        return {"message": "Settlement cancelled successfully"}

    except HTTPException:
        raise
    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel settlement: {str(e)}") from e


# ============================================================================
# MIGRATION NOTES: API Key to JWT Auth
# ============================================================================
#
# Migration completed: 2025-01-XX
#
# Changes made:
# 1. Import change:
#    OLD: from ....auth import get_api_key
#    NEW: from ....auth import MinerDep
#
# 2. Dependency changes (4 endpoints):
#    - initiate_cross_chain_settlement: api_key -> user: MinerDep
#    - get_settlement_status: api_key -> user: MinerDep
#    - list_settlements: api_key -> user: MinerDep
#    - cancel_settlement: api_key -> user: MinerDep
#
# 3. API key references updated:
#    - background_tasks.add_task(..., user["sub"])
#    - manager.list_settlements(api_key=user["sub"], ...)
#    - manager.cancel_settlement(..., user["sub"])
#
# 4. JWT benefits:
#    - user["sub"]: Miner user ID
#    - user["role"]: Role verification (miner)
#    - user["exp"]: Token expiration
#    - Centralized auth via security matrix
#
# 5. Client code change:
#    OLD: headers = {"X-Api-Key": "your-api-key"}
#    NEW: headers = {"Authorization": f"Bearer {token}"}
#
# ============================================================================
