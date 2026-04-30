"""
Trading Service main application
Manages trading operations
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

from .storage import init_db, get_session
from .services.trading_service import TradingService

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Trading Service."""
    logger.info("Starting Trading Service")
    # Initialize database
    await init_db()
    yield
    logger.info("Shutting down Trading Service")


app = FastAPI(
    title="AITBC Trading Service",
    description="Manages trading operations",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
app.add_middleware(ErrorHandlerMiddleware)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="trading-service")


@app.get("/trading/status")
async def trading_status() -> dict[str, str]:
    """Get trading status"""
    return {
        "status": "operational",
        "service": "trading-service",
        "message": "Trading service is running",
    }


async def get_trading_service(session: AsyncSession = Depends(get_session)) -> TradingService:
    """Get trading service instance"""
    return TradingService(session)


@app.get("/v1/trading/requests")
async def get_requests(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    trade_type: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade requests"""
    return svc.list_requests(status=status, buyer_agent_id=buyer_agent_id, trade_type=trade_type)


@app.get("/v1/trading/requests/{request_id}")
async def get_request(
    request_id: str,
    svc: TradingService = Depends(get_trading_service),
):
    """Get a specific trade request"""
    return svc.get_request(request_id)


@app.post("/v1/trading/requests")
async def create_request(
    request_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade request"""
    return svc.create_request(request_data)


@app.get("/v1/trading/matches")
async def get_matches(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade matches"""
    return svc.list_matches(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/matches")
async def create_match(
    match_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade match"""
    return svc.create_match(match_data)


@app.get("/v1/trading/agreements")
async def get_agreements(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade agreements"""
    return svc.list_agreements(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/agreements")
async def create_agreement(
    agreement_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade agreement"""
    return svc.create_agreement(agreement_data)


@app.get("/v1/trading/analytics")
async def get_analytics(
    period_type: str = "daily",
    svc: TradingService = Depends(get_trading_service),
):
    """Get trading analytics"""
    return await svc.get_analytics(period_type=period_type)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8104)
