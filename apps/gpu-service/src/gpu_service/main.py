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


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Get database session dependency"""
    async with get_session() as session:
        yield session

async def get_edge_service(session: AsyncSession = Depends(get_session_dep)) -> EdgeGPUService:
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


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict, session: AsyncSession = Depends(get_session_dep)):
    """Submit GPU marketplace transaction"""
    from .domain.gpu_marketplace import GPURegistry
    
    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')
    
    if transaction_type != 'gpu_marketplace':
        return {"error": "Invalid transaction type for GPU service"}, 400
    
    try:
        if action == 'offer':
            # Map offer data to GPURegistry
            gpu_data = {
                "id": transaction_data.get('offer_id', f"gpu_{transaction_data.get('provider_node_id', 'unknown')}"),
                "miner_id": transaction_data.get('provider_node_id', 'default_miner'),
                "model": transaction_data.get('specs', {}).get('model', 'Unknown'),
                "memory_gb": transaction_data.get('specs', {}).get('memory_gb', 0),
                "price_per_hour": transaction_data.get('price_per_gpu', 0.0),
                "status": transaction_data.get('status', 'available'),
                "region": transaction_data.get('specs', {}).get('region', ''),
                "capabilities": transaction_data.get('specs', {}).get('capabilities', []),
            }
            gpu = GPURegistry(**gpu_data)
            session.add(gpu)
        else:
            return {"error": f"Invalid action: {action}. Only 'offer' is currently supported"}, 400
        
        await session.commit()
        return {"status": "success", "transaction_id": transaction_data.get('offer_id')}
    except Exception as e:
        await session.rollback()
        logger.error(f"Transaction submission error: {e}")
        return {"error": str(e)}, 500


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None = None,
    action: str | None = None,
    status: str | None = None,
    island_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Query GPU marketplace transactions"""
    from .domain.gpu_marketplace import GPURegistry
    from sqlalchemy import select
    
    try:
        transactions = []
        
        # Query GPU registry for offers
        result = await session.execute(select(GPURegistry))
        gpus = result.scalars().all()
        
        # Map to transaction format
        for gpu in gpus:
            transactions.append({
                "id": gpu.id,
                "action": "offer",
                "model": gpu.model,
                "memory_gb": gpu.memory_gb,
                "price_per_hour": gpu.price_per_hour,
                "status": gpu.status,
                "region": gpu.region,
                "miner_id": gpu.miner_id,
                "created_at": gpu.created_at.isoformat() if gpu.created_at else None
            })
        
        # Apply filters
        if status:
            transactions = [t for t in transactions if t.get('status') == status]
        if island_id:
            transactions = [t for t in transactions if t.get('miner_id') == island_id]
        
        return transactions
    except Exception as e:
        logger.error(f"Transaction query error: {e}")
        return {"error": str(e)}, 500


@app.post("/v1/miners/register")
async def register_miner(
    miner_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Register or update a miner"""
    from .domain.gpu_marketplace import GPURegistry
    from uuid import uuid4
    from sqlalchemy import select
    
    try:
        miner_id = miner_data.get('miner_id', f"miner_{uuid4().hex[:8]}")
        session_token = f"token_{uuid4().hex[:16]}"
        
        # Check if miner already has GPUs registered
        result = await session.execute(
            select(GPURegistry).where(GPURegistry.miner_id == miner_id)
        )
        existing_gpus = result.scalars().all()
        
        if existing_gpus:
            # Update existing GPUs
            for gpu in existing_gpus:
                gpu.status = "online"
        
        return {
            "status": "ok",
            "miner_id": miner_id,
            "session_token": session_token,
            "gpu_count": len(existing_gpus)
        }
    except Exception as e:
        logger.error(f"Miner registration error: {e}")
        return {"error": str(e)}, 500


@app.post("/v1/miners/heartbeat")
async def miner_heartbeat(
    heartbeat_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Send miner heartbeat"""
    from .domain.gpu_marketplace import GPURegistry
    from sqlalchemy import select, update
    
    try:
        miner_id = heartbeat_data.get('miner_id')
        
        # Update miner's GPUs to online status
        stmt = (
            update(GPURegistry)
            .where(GPURegistry.miner_id == miner_id)
            .values(status="online")
        )
        await session.execute(stmt)
        await session.commit()
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return {"error": str(e)}, 500


@app.get("/v1/miners/{miner_id}/gpus")
async def get_miner_gpus(
    miner_id: str,
    session: AsyncSession = Depends(get_session_dep),
):
    """Get GPUs registered by a miner"""
    from .domain.gpu_marketplace import GPURegistry
    from sqlalchemy import select
    
    try:
        result = await session.execute(
            select(GPURegistry).where(GPURegistry.miner_id == miner_id)
        )
        gpus = result.scalars().all()
        
        return [
            {
                "id": gpu.id,
                "model": gpu.model,
                "memory_gb": gpu.memory_gb,
                "status": gpu.status,
                "price_per_hour": gpu.price_per_hour,
                "region": gpu.region,
                "created_at": gpu.created_at.isoformat() if gpu.created_at else None
            }
            for gpu in gpus
        ]
    except Exception as e:
        logger.error(f"Get miner GPUs error: {e}")
        return {"error": str(e)}, 500


@app.post("/v1/miners/poll")
async def poll_jobs(
    poll_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Poll for next job"""
    miner_id = poll_data.get('miner_id')
    max_wait = poll_data.get('max_wait_seconds', 5)
    
    # Placeholder implementation - job scheduling would be added here
    # For now, return no jobs available
    return None


@app.post("/v1/miners/{job_id}/result")
async def submit_job_result(
    job_id: str,
    result_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Submit job result"""
    miner_id = result_data.get('miner_id')
    result = result_data.get('result')
    metrics = result_data.get('metrics', {})
    
    # Placeholder implementation - job result processing would be added here
    return {
        "status": "ok",
        "job_id": job_id,
        "result": "accepted"
    }


@app.post("/v1/miners/{job_id}/fail")
async def submit_job_failure(
    job_id: str,
    fail_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Submit job failure"""
    miner_id = fail_data.get('miner_id')
    error = fail_data.get('error')
    
    # Placeholder implementation - job failure processing would be added here
    return {
        "status": "ok",
        "job_id": job_id,
        "error": "recorded"
    }


@app.post("/v1/miners/{miner_id}/earnings")
async def get_miner_earnings(
    miner_id: str,
    session: AsyncSession = Depends(get_session_dep),
):
    """Get miner earnings"""
    # Placeholder implementation - earnings tracking would be added here
    return {
        "miner_id": miner_id,
        "total_earnings": 0.0,
        "pending_earnings": 0.0,
        "currency": "AITBC"
    }


@app.put("/v1/miners/{miner_id}/capabilities")
async def update_miner_capabilities(
    miner_id: str,
    capabilities_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Update miner capabilities"""
    capabilities = capabilities_data.get('capabilities', {})
    
    # Placeholder implementation - capability update would be added here
    return {
        "status": "ok",
        "miner_id": miner_id,
        "capabilities": capabilities
    }


@app.delete("/v1/miners/{miner_id}")
async def deregister_miner(
    miner_id: str,
    session: AsyncSession = Depends(get_session_dep),
):
    """Deregister miner"""
    from .domain.gpu_marketplace import GPURegistry
    from sqlalchemy import select, update
    
    try:
        # Set miner's GPUs to offline status
        stmt = (
            update(GPURegistry)
            .where(GPURegistry.miner_id == miner_id)
            .values(status="offline")
        )
        await session.execute(stmt)
        await session.commit()
        
        return {
            "status": "ok",
            "miner_id": miner_id,
            "message": "Miner deregistered"
        }
    except Exception as e:
        logger.error(f"Deregister miner error: {e}")
        return {"error": str(e)}, 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8101)
