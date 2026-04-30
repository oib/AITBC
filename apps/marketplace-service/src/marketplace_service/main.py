"""
Marketplace Service main application
Manages GPU marketplace operations
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
from .services.marketplace_service import MarketplaceService

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Marketplace Service."""
    logger.info("Starting Marketplace Service")
    # Initialize database
    await init_db()
    yield
    logger.info("Shutting down Marketplace Service")


app = FastAPI(
    title="AITBC Marketplace Service",
    description="Manages GPU marketplace operations",
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
    return HealthResponse(status="healthy", service="marketplace-service")


@app.get("/marketplace/status")
async def marketplace_status() -> dict[str, str]:
    """Get marketplace status"""
    return {
        "status": "operational",
        "service": "marketplace-service",
        "message": "Marketplace service is running",
    }


async def get_marketplace_service(session: AsyncSession = Depends(get_session)) -> MarketplaceService:
    """Get marketplace service instance"""
    return MarketplaceService(session)


@app.get("/v1/marketplace/offers")
async def get_offers(
    status: str | None = None,
    region: str | None = None,
    gpu_model: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace offers"""
    return svc.list_offers(status=status, region=region, gpu_model=gpu_model)


@app.get("/v1/marketplace/offers/{offer_id}")
async def get_offer(
    offer_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get a specific marketplace offer"""
    return svc.get_offer(offer_id)


@app.post("/v1/marketplace/offers")
async def create_offer(
    offer_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new marketplace offer"""
    return svc.create_offer(offer_data)


@app.get("/v1/marketplace/bids")
async def get_bids(
    status: str | None = None,
    provider: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace bids"""
    return svc.list_bids(status=status, provider=provider)


@app.post("/v1/marketplace/bids")
async def create_bid(
    bid_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new marketplace bid"""
    return svc.create_bid(bid_data)


@app.get("/v1/marketplace/analytics")
async def get_analytics(
    period_type: str = "daily",
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace analytics"""
    return await svc.get_analytics(period_type=period_type)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8102)
