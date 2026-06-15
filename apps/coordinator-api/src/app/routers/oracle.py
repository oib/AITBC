"""
Oracle Router - Price feed API endpoints

Provides:
- Price queries
- Price history
- Admin price setting
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..services.oracle_service import get_oracle_service

router = APIRouter(prefix="/oracle", tags=["oracle"])


class SetPriceRequest(BaseModel):
    """Request to set a price"""

    pair: str
    price: float
    confidence: float = 1.0
    source: str = "manual"


class PriceResponse(BaseModel):
    """Price response"""

    pair: str
    price: float
    source: str
    timestamp: str
    confidence: float


@router.get("/price/{pair}", response_model=PriceResponse, summary="Get price for pair")
async def get_price(request: Request, pair: str) -> dict[str, Any]:
    """Get current price for a trading pair (e.g., BTC/USD)"""
    try:
        oracle = get_oracle_service()
        price = await oracle.get_price(pair)

        if not price:
            # Try to get from manual cache
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Price not available for {pair}")

        return price

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get price: {str(e)}")


@router.get("/prices", summary="Get all prices")
async def get_all_prices(request: Request) -> dict[str, Any]:
    """Get all available trading pair prices"""
    try:
        oracle = get_oracle_service()
        prices = await oracle.get_all_prices()

        return {
            "prices": prices,
            "count": len(prices),
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get prices: {str(e)}")


@router.post("/price", summary="Set price (admin)")
async def set_price(request: Request, req: SetPriceRequest) -> dict[str, Any]:
    """
    Set price for a trading pair (admin function).

    This overrides automated price feeds.
    """
    try:
        # In production, verify admin API key
        # For now, allow any authenticated request

        oracle = get_oracle_service()
        result = oracle.set_price(pair=req.pair, price=req.price, confidence=req.confidence, source=req.source)

        return {"success": True, **result}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to set price: {str(e)}")


@router.get("/health", summary="Health check")
async def oracle_health(request: Request) -> dict[str, Any]:
    """Check oracle service health"""
    return {"status": "healthy", "service": "oracle"}


@router.get("/oracle/health", summary="Oracle health check")
async def health_check(request: Request) -> dict[str, Any]:
    """Check oracle service health"""
    try:
        oracle = get_oracle_service()
        prices = await oracle.get_all_prices()

        return {"status": "healthy", "available_pairs": len(prices), "pairs": list(prices.keys())}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
