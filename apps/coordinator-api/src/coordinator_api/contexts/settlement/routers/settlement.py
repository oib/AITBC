"""
Settlement router for cross-chain settlements

ponytail: All settlement endpoints are disabled and return 501 until a real
bridge initialization, signature verification, provider configuration, and
persistence layer are implemented.
"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep

router = APIRouter(prefix="/settlement", tags=["settlement"])


class CrossChainSettlementRequest(BaseModel):
    """Request model for cross-chain settlement"""

    source_chain_id: str = Field(..., description="Source blockchain ID")
    target_chain_id: str = Field(..., description="Target blockchain ID")
    amount: Decimal = Field(..., gt=Decimal("0"), description="Amount to settle")
    asset_type: str = Field(..., description="Asset type (e.g., 'AITBC', 'ETH')")
    recipient_address: str = Field(..., description="Recipient address on target chain")
    gas_limit: int | None = Field(None, description="Gas limit for transaction")
    gas_price: Decimal | None = Field(None, gt=Decimal("0"), description="Gas price in Gwei")


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
    user: MinerDep,
) -> CrossChainSettlementResponse:
    """Initiate a cross-chain settlement"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Settlement is not implemented",
    )


@router.get("/cross-chain/{settlement_id}")
@rate_limit(rate=200, per=60)
async def get_settlement_status(
    request: Request,
    settlement_id: str,
    user: MinerDep,
) -> dict[str, Any]:
    """Get settlement status"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Settlement is not implemented",
    )


@router.get("/cross-chain")
@rate_limit(rate=200, per=60)
async def list_settlements(
    request: Request,
    user: MinerDep,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List settlements with pagination"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Settlement is not implemented",
    )


@router.delete("/cross-chain/{settlement_id}")
@rate_limit(rate=20, per=60)
async def cancel_settlement(
    request: Request,
    settlement_id: str,
    user: MinerDep,
) -> dict[str, str]:
    """Cancel a pending settlement"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Settlement is not implemented",
    )
