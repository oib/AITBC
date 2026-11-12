"""
Portfolio Management API Endpoints
REST API for unified portfolio management across AITBC services
"""

from collections.abc import Awaitable, Callable
from datetime import UTC
from decimal import InvalidOperation
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..services.portfolio_aggregation_service import PortfolioAggregationService

logger = get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])
portfolio_service = PortfolioAggregationService()

# Expected failure surface for the 500-translate handlers and per-dependency
# health probes below: outbound HTTP from the aggregation service (httpx),
# response decode/Decimal conversion, pydantic validation (ValueError), and
# data-shape/runtime errors. HTTPException is not in the tuple, so it
# propagates to the client untouched.
_OPS_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    InvalidOperation,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    httpx.HTTPError,
)


class PortfolioSummaryResponse(BaseModel):
    """Response model for unified portfolio summary"""

    timestamp: str
    agent_address: str | None
    wallet: dict[str, Any]
    exchange: dict[str, Any]
    market: dict[str, Any]
    trading: dict[str, Any]
    ai_signals: dict[str, Any]
    summary: dict[str, Any]


class PortfolioHealthResponse(BaseModel):
    """Response model for portfolio health check"""

    status: str
    services: dict[str, str]
    timestamp: str


async def _probe_portfolio_dependency(fetch: Callable[[], Awaitable[dict[str, Any]]]) -> tuple[str, bool]:
    """Run one dependency probe; returns (service status, overall degraded flag)."""
    try:
        data = await fetch()
    except _OPS_ERRORS:
        return "unhealthy", True
    if data.get("error"):
        return "degraded", True
    return "healthy", False


@router.get("/unified", response_model=PortfolioSummaryResponse)
@rate_limit(rate=100, per=60)
async def get_unified_portfolio(
    request: Request, agent_address: str | None = Query(default=None, description="Filter by agent address")
) -> PortfolioSummaryResponse:
    """
    Get unified portfolio view aggregating data from all AITBC services

    Aggregates data from:
    - Wallet service (8108): Wallet balances
    - Exchange service (8106): Exchange rates
    - Market service (8102): Market stats
    - Trading service (8104): Trading analytics
    - AI service (8005): AI trade signals (simulation-labelled)
    """
    try:
        portfolio_data = await portfolio_service.get_unified_portfolio(agent_address)
        return PortfolioSummaryResponse(**portfolio_data)
    except _OPS_ERRORS as e:
        logger.error("Error getting unified portfolio: %s", str(e))
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health", response_model=PortfolioHealthResponse)
@rate_limit(rate=200, per=60)
async def get_portfolio_health(request: Request) -> PortfolioHealthResponse:
    """Health check for portfolio aggregation service and dependencies"""
    services_status = {}
    overall_status = "healthy"
    probes: tuple[tuple[str, Callable[[], Awaitable[dict[str, Any]]]], ...] = (
        ("wallet", portfolio_service._get_wallet_balances),
        ("exchange", portfolio_service._get_exchange_rates),
        ("market", portfolio_service._get_market_stats),
        ("trading", portfolio_service._get_trading_analytics),
        ("ai", portfolio_service._get_ai_trade_signals),
    )
    for name, fetch in probes:
        dep_status, degraded = await _probe_portfolio_dependency(fetch)
        services_status[name] = dep_status
        if degraded:
            overall_status = "degraded"
    from datetime import datetime

    return PortfolioHealthResponse(status=overall_status, services=services_status, timestamp=datetime.now(UTC).isoformat())


@router.get("/summary")
@rate_limit(rate=200, per=60)
async def get_portfolio_summary_only(
    request: Request, agent_address: str | None = Query(default=None, description="Filter by agent address")
) -> dict[str, Any]:
    """Get only the portfolio summary metrics without full details"""
    try:
        portfolio_data = await portfolio_service.get_unified_portfolio(agent_address)
        return {"timestamp": portfolio_data["timestamp"], "agent_address": agent_address, "summary": portfolio_data["summary"]}
    except _OPS_ERRORS as e:
        logger.error("Error getting portfolio summary: %s", str(e))
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
