"""
GPU Service main application
Manages GPU resource operations
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
from .services.edge_gpu_service import EdgeGPUService

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the GPU Service."""
    logger.info("Starting GPU Service")
    # Initialize database
    await init_db()
    yield
    logger.info("Shutting down GPU Service")


app = FastAPI(
    title="AITBC GPU Service",
    description="Manages GPU resource operations",
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
    return HealthResponse(status="healthy", service="gpu-service")


@app.get("/gpu/status")
async def gpu_status() -> dict[str, str]:
    """Get GPU status"""
    return {
        "status": "operational",
        "service": "gpu-service",
        "message": "GPU service is running",
    }


async def get_edge_service(session: AsyncSession = Depends(get_session)) -> EdgeGPUService:
    """Get edge GPU service instance"""
    return EdgeGPUService(session)


@app.get("/v1/marketplace/edge-gpu/profiles")
async def get_consumer_gpu_profiles(
    architecture: str | None = None,
    edge_optimized: bool | None = None,
    min_memory_gb: int | None = None,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Get consumer GPU profiles"""
    from .domain.gpu_marketplace import GPUArchitecture
    
    arch = GPUArchitecture(architecture) if architecture else None
    return svc.list_profiles(architecture=arch, edge_optimized=edge_optimized, min_memory_gb=min_memory_gb)


@app.get("/v1/marketplace/edge-gpu/metrics/{gpu_id}")
async def get_edge_gpu_metrics(
    gpu_id: str,
    limit: int = 100,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Get edge GPU metrics"""
    return svc.list_metrics(gpu_id=gpu_id, limit=limit)


@app.post("/v1/marketplace/edge-gpu/scan/{miner_id}")
async def scan_edge_gpus(
    miner_id: str,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Scan and register edge GPUs for a miner"""
    return await svc.discover_and_register_edge_gpus(miner_id)


@app.post("/v1/marketplace/edge-gpu/optimize/inference/{gpu_id}")
async def optimize_inference(
    gpu_id: str,
    model_name: str,
    request_data: dict,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Optimize ML inference request for edge GPU"""
    return await svc.optimize_inference_for_edge(gpu_id, model_name, request_data)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)
