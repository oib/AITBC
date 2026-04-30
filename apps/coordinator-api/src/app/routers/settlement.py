"""
Settlement router for cross-chain settlements
"""

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_api_key
from .settlement.manager import BridgeManager

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
async def initiate_cross_chain_settlement(
    request: CrossChainSettlementRequest, background_tasks: BackgroundTasks, api_key: str = Depends(get_api_key)
) -> CrossChainSettlementResponse:
    """Initiate a cross-chain settlement"""
    try:
        # Initialize settlement manager
        manager = BridgeManager()

        # Create settlement
        settlement_id = await manager.create_settlement(
            source_chain_id=request.source_chain_id,
            target_chain_id=request.target_chain_id,
            amount=request.amount,
            asset_type=request.asset_type,
            recipient_address=request.recipient_address,
            gas_limit=request.gas_limit,
            gas_price=request.gas_price,
        )

        # Add background task to process settlement
        background_tasks.add_task(manager.process_settlement, settlement_id, api_key)

        return CrossChainSettlementResponse(
            settlement_id=settlement_id,
            status="pending",
            estimated_completion="~5 minutes",
            created_at=asyncio.get_event_loop().time(),
        )

    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Settlement failed: {str(e)}")


@router.get("/cross-chain/{settlement_id}")
async def get_settlement_status(settlement_id: str, api_key: str = Depends(get_api_key)) -> dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=f"Failed to get settlement: {str(e)}")


@router.get("/cross-chain")
async def list_settlements(api_key: str = Depends(get_api_key), limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List settlements with pagination"""
    try:
        manager = BridgeManager()
        settlements = await manager.list_settlements(api_key=api_key, limit=limit, offset=offset)

        return {"settlements": settlements, "total": len(settlements), "limit": limit, "offset": offset}

    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to list settlements: {str(e)}")


@router.delete("/cross-chain/{settlement_id}")
async def cancel_settlement(settlement_id: str, api_key: str = Depends(get_api_key)) -> dict[str, str]:
    """Cancel a pending settlement"""
    try:
        manager = BridgeManager()
        success = await manager.cancel_settlement(settlement_id, api_key)

        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel settlement")

        return {"message": "Settlement cancelled successfully"}

    except HTTPException:
        raise
    except (ValueError, KeyError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel settlement: {str(e)}")
