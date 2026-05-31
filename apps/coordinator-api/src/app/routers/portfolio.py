"""
Portfolio Router - Portfolio aggregation API endpoints

Provides:
- Cross-wallet portfolio view
- Wallet breakdowns
- Historical portfolio value
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..services.portfolio_service import get_portfolio_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PortfolioRequest(BaseModel):
    """Request for portfolio data"""
    wallet_addresses: list[str] | None = None


@router.get("/", summary="Get full portfolio")
async def get_portfolio(
    request: Request,
    user_id: str | None = None
) -> dict[str, Any]:
    """
    Get complete portfolio aggregation.
    
    Returns:
    - Total value in USD
    - Holdings by chain
    - Individual positions
    - Wallet breakdowns
    """
    try:
        service = get_portfolio_service()

        # Get user ID from request if not provided
        if not user_id:
            user_id = request.headers.get("X-User-ID", "anonymous")

        portfolio = await service.get_portfolio(user_id=user_id)

        if "error" in portfolio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=portfolio["error"]
            )

        return portfolio

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get portfolio: {str(e)}"
        )


@router.post("/", summary="Get portfolio for specific wallets")
async def get_portfolio_for_wallets(
    request: Request,
    req: PortfolioRequest
) -> dict[str, Any]:
    """Get portfolio for specific wallet addresses"""
    try:
        service = get_portfolio_service()

        if not req.wallet_addresses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="wallet_addresses required"
            )

        portfolio = await service.get_portfolio(
            wallet_addresses=req.wallet_addresses
        )

        if "error" in portfolio:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=portfolio["error"]
            )

        return portfolio

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get portfolio: {str(e)}"
        )


@router.get("/wallet/{address}", summary="Get wallet breakdown")
async def get_wallet_breakdown(
    request: Request,
    address: str,
    chain_id: str | None = None
) -> dict[str, Any]:
    """
    Get detailed breakdown for a single wallet.
    
    Shows:
    - Available balance
    - Staked amount
    - Bridge-locked amount
    - USD value
    """
    try:
        service = get_portfolio_service()

        chain_id = chain_id or "ait-mainnet"

        breakdown = await service.get_wallet_breakdown(address, chain_id)

        if "error" in breakdown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=breakdown["error"]
            )

        return breakdown

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get wallet breakdown: {str(e)}"
        )


@router.get("/chains", summary="Get supported chains")
async def get_supported_chains(request: Request) -> dict[str, Any]:
    """Get list of supported blockchain networks"""
    return {
        "chains": [
            {
                "chain_id": "ait-mainnet",
                "name": "AITBC Mainnet",
                "native_token": "AITBC"
            },
            {
                "chain_id": "ait-testnet",
                "name": "AITBC Testnet",
                "native_token": "tAITBC"
            }
        ]
    }


@router.get("/health", summary="Health check")
async def portfolio_health(request: Request) -> dict[str, Any]:
    """Check portfolio service health"""
    return {
        "status": "healthy",
        "service": "portfolio"
    }
