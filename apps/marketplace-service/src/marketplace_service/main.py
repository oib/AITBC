"""
Marketplace Service main application
Manages GPU marketplace operations
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from pydantic import BaseModel

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Marketplace Service."""
    logger.info("Starting Marketplace Service")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8102)
