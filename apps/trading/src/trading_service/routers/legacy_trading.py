"""Legacy P2P trading endpoints for requests, matches, agreements, and analytics."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ..dependencies import get_trading_service
from ..services.trading_service import TradingService

router = APIRouter(tags=["trading"])


@router.get("/v1/trading/requests")
async def get_requests(
    svc: Annotated[TradingService, Depends(get_trading_service)],
    status: str | None = None,
    buyer_agent_id: str | None = None,
    trade_type: str | None = None,
):
    """Get trade requests."""
    return await svc.list_requests(status=status, buyer_agent_id=buyer_agent_id, trade_type=trade_type)


@router.get("/v1/trading/requests/{request_id}")
async def get_request(request_id: str, svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Get a specific trade request."""
    return await svc.get_request(request_id)


@router.post("/v1/trading/requests")
async def create_request(request_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade request."""
    return await svc.create_request(request_data)


@router.get("/v1/trading/matches")
async def get_matches(
    svc: Annotated[TradingService, Depends(get_trading_service)],
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
):
    """Get trade matches."""
    return await svc.list_matches(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@router.post("/v1/trading/matches")
async def create_match(match_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade match."""
    return await svc.create_match(match_data)


@router.get("/v1/trading/agreements")
async def get_agreements(
    svc: Annotated[TradingService, Depends(get_trading_service)],
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
):
    """Get trade agreements."""
    return await svc.list_agreements(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@router.post("/v1/trading/agreements")
async def create_agreement(agreement_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade agreement."""
    return await svc.create_agreement(agreement_data)


@router.get("/v1/trading/analytics")
async def get_analytics(
    svc: Annotated[TradingService, Depends(get_trading_service)],
    period_type: str | None = None,
):
    """Get trading analytics."""
    return await svc.get_analytics(period_type=period_type)  # type: ignore[arg-type]
