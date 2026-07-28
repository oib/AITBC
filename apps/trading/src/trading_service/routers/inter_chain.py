"""Inter-chain trading endpoints: chain discovery, trade lifecycle, matching."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..dependencies import get_chain_discovery, get_inter_chain_service, get_matching_engine
from ..services.chain_discovery import ChainDiscoveryService
from ..services.inter_chain_service import InterChainTradeService
from ..services.matching_engine import MatchingEngine

router = APIRouter(tags=["inter-chain"])


@router.get("/v1/trading/chains")
async def list_chains(
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
    status: str | None = None,
):
    """List registered chains for inter-chain trading."""
    return await svc.list_chains(status=status)


@router.post("/v1/trading/chains/register")
async def register_chain(
    chain_id: str,
    endpoint: str,
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
):
    """Register a new chain in the island registry."""
    return await svc.register_chain(chain_id=chain_id, endpoint=endpoint)


@router.get("/v1/trading/chains/{chain_id}/health")
async def get_chain_health(
    chain_id: str,
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
):
    """Get health metrics for a specific chain."""
    return await svc.get_chain_health(chain_id)


@router.post("/v1/trading/inter-chain/create")
async def create_inter_chain_trade(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    source_chain: str,
    dest_chain: str,
    sender: str,
    recipient: str,
    amount: int,
    offer_id: str | None = None,
    price: Decimal = Decimal("0"),
    quantity: int = 0,
):
    """Create a new inter-chain trade."""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    return await svc.create_trade(
        source_chain=source_chain,
        dest_chain=dest_chain,
        sender=sender,
        recipient=recipient,
        amount=amount,
        offer_id=offer_id,
        price=price,
        quantity=quantity,
    )


@router.get("/v1/trading/inter-chain")
async def list_inter_chain_trades(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    status: str | None = None,
    source_chain: str | None = None,
    dest_chain: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List inter-chain trades with optional filters."""
    return await svc.list_trades(
        status=status,
        source_chain=source_chain,
        dest_chain=dest_chain,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/trading/inter-chain/history")
async def get_inter_chain_trade_history(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    source_chain: str | None = None,
    dest_chain: str | None = None,
    limit: int = 50,
):
    """Get inter-chain trade history."""
    return await svc.get_trade_history(
        source_chain=source_chain,
        dest_chain=dest_chain,
        limit=limit,
    )


@router.post("/v1/trading/inter-chain/match-all")
async def match_all_pending_trades(
    svc: Annotated[MatchingEngine, Depends(get_matching_engine)],
):
    """Attempt to match all pending inter-chain trades."""
    return await svc.match_all_pending()


@router.get("/v1/trading/inter-chain/{trade_id}")
async def get_inter_chain_trade(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
):
    """Get inter-chain trade details."""
    trade = await svc.get_trade(trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return trade


@router.get("/v1/trading/inter-chain/{trade_id}/status")
async def get_inter_chain_trade_status(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
):
    """Get inter-chain trade status."""
    status = await svc.get_trade_status(trade_id)
    if not status:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return status


@router.post("/v1/trading/inter-chain/{trade_id}/match")
async def match_inter_chain_trade(
    trade_id: str,
    svc: Annotated[MatchingEngine, Depends(get_matching_engine)],
):
    """Attempt to match an inter-chain trade with a counterparty."""
    result = await svc.match_trade(trade_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return result
