"""
GPU Service main application
Manages GPU resource operations
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
    configure_logging,
    get_logger,
)

from .services.edge_gpu_service import EdgeGPUService
from .storage import get_session, init_db

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


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness check - verifies database connectivity"""
    try:
        async with get_session() as session:
            # Test database connection
            await session.execute("SELECT 1")
        return {"status": "ready", "service": "gpu-service"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "gpu-service", "error": str(e)},
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "gpu-service"}


@app.get("/v1/gpu/status")
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
    return await svc.list_profiles(architecture=arch, edge_optimized=edge_optimized, min_memory_gb=min_memory_gb)


@app.get("/v1/marketplace/edge-gpu/metrics/{gpu_id}")
async def get_edge_gpu_metrics(
    gpu_id: str,
    limit: int = 100,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Get edge GPU metrics"""
    return await svc.list_metrics(gpu_id=gpu_id, limit=limit)


@app.post("/v1/marketplace/edge-gpu/scan/{miner_id}")
async def scan_edge_gpus(
    miner_id: str,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Scan and register edge GPUs for a miner"""
    return await svc.discover_and_register_edge_gpus(miner_id)


from pydantic import BaseModel


class OptimizeInferenceRequest(BaseModel):
    model_name: str
    request_data: dict


@app.post("/v1/marketplace/edge-gpu/optimize/inference/{gpu_id}")
async def optimize_inference(
    gpu_id: str,
    request: OptimizeInferenceRequest,
    svc: EdgeGPUService = Depends(get_edge_service),
):
    """Optimize ML inference request for edge GPU"""
    return await svc.optimize_inference_for_edge(gpu_id, request.model_name, request.request_data)


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict, session: AsyncSession = Depends(get_session_dep)):
    """Submit GPU marketplace transaction to blockchain"""
    from aitbc import AITBCHTTPClient

    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')

    logger.info(f"=== Transaction Submission ===")
    logger.info(f"Transaction type: {transaction_type}")
    logger.info(f"Action: {action}")

    if transaction_type != 'gpu_marketplace':
        return {"error": "Invalid transaction type for GPU service"}, 400

    try:
        if action == 'offer':
            # Create blockchain GPU registration transaction
            gpu_specs = transaction_data.get('specs', {})
            provider_address = transaction_data.get('provider_address', '')
            
            logger.info(f"=== GPU Registration ===")
            logger.info(f"Provider address: '{provider_address}'")
            logger.info(f"GPU specs: {gpu_specs}")
            
            # Submit GPU_REGISTER transaction to blockchain
            blockchain_tx = {
                "from": provider_address,
                "to": "0x0000000000000000000000000000000000000000",
                "amount": 0,
                "fee": 10,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "payload": {
                    "amount": 0,
                    "compute_capability": gpu_specs.get('compute_capability', ''),
                    "cuda_cores": gpu_specs.get('cuda_cores', 0),
                    "description": gpu_specs.get('description', ''),
                    "gpu_model": gpu_specs.get('model', 'Unknown'),
                    "memory_gb": gpu_specs.get('memory_gb', 0),
                    "miner_id": transaction_data.get('provider_node_id', 'default_miner'),
                    "price_per_hour": transaction_data.get('price_per_gpu', 0.0),
                    "provider_address": provider_address
                },
                "signature": transaction_data.get('signature', '')
            }
            
            logger.info(f"Blockchain transaction prepared: type={blockchain_tx['type']}")

            # Submit to blockchain (optional - if wallet address provided)
            blockchain_tx_hash = None
            if provider_address:
                try:
                    logger.info("Attempting blockchain transaction submission...")
                    # Use hub blockchain endpoint from environment
                    hub_url = os.getenv("HUB_BLOCKCHAIN_URL", "https://hub.aitbc.bubuit.net")
                    
                    # Fetch correct nonce from hub blockchain
                    http_client = AITBCHTTPClient(base_url=hub_url, timeout=30)
                    account_info = http_client.get(f"/rpc/account/{provider_address}")
                    correct_nonce = account_info.get("nonce", 0) if isinstance(account_info, dict) else 0
                    blockchain_tx["nonce"] = correct_nonce
                    
                    logger.info(f"Using nonce: {correct_nonce} for address {provider_address}")
                    logger.info(f"Submitting transaction: {blockchain_tx}")
                    result = http_client.post("/rpc/transaction", json=blockchain_tx)
                    logger.info(f"Blockchain response: {result}")
                    blockchain_tx_hash = result.get("transaction_hash")
                    if blockchain_tx_hash:
                        logger.info(f"Blockchain transaction submitted: {blockchain_tx_hash}")
                except Exception as blockchain_error:
                    logger.warning(f"Blockchain submission failed, falling back to local storage: {blockchain_error}")
                    logger.warning(f"Error type: {type(blockchain_error)}")
                    if hasattr(blockchain_error, 'args'):
                        logger.warning(f"Error args: {blockchain_error.args}")
                    if hasattr(blockchain_error, 'response'):
                        logger.warning(f"Response: {blockchain_error.response}")
                        if hasattr(blockchain_error.response, 'text'):
                            logger.warning(f"Response text: {blockchain_error.response.text}")
                    if hasattr(blockchain_error, '__str__'):
                        logger.warning(f"Error string: {str(blockchain_error)}")
            else:
                logger.info("No provider address provided, skipping blockchain registration")
            
            # Store in local database for quick access (always)
            gpu_data = {
                "id": transaction_data.get('offer_id', f"gpu_{transaction_data.get('provider_node_id', 'unknown')}"),
                "miner_id": transaction_data.get('provider_node_id', 'default_miner'),
                "model": gpu_specs.get('model', 'Unknown'),
                "memory_gb": gpu_specs.get('memory_gb', 0),
                "price_per_hour": transaction_data.get('price_per_gpu', 0.0),
                "status": transaction_data.get('status', 'available'),
                "region": gpu_specs.get('region', ''),
                "capabilities": gpu_specs.get('capabilities', []),
                "blockchain_tx_hash": blockchain_tx_hash
            }
            from .domain.gpu_marketplace import GPURegistry
            gpu = GPURegistry(**gpu_data)
            session.add(gpu)
            await session.commit()
            
            response_data = {
                "status": "success", 
                "transaction_id": transaction_data.get('offer_id'),
                "blockchain_registered": blockchain_tx_hash is not None
            }
            if blockchain_tx_hash:
                response_data["blockchain_tx_hash"] = blockchain_tx_hash
            
            return response_data
        else:
            return {"error": f"Invalid action: {action}. Only 'offer' is currently supported"}, 400

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
    from sqlalchemy import select

    from .domain.gpu_marketplace import GPURegistry

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


@app.post("/v1/gpu/register")
async def register_gpu(
    gpu_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Register a GPU with the service and record on blockchain"""
    from uuid import uuid4

    from sqlalchemy import select

    from .domain.gpu_marketplace import GPURegistry

    try:
        gpu_id = gpu_data.get("gpu_id", f"gpu_{uuid4().hex[:8]}")
        miner_id = gpu_data.get("miner_id", "default_miner")
        specs = gpu_data.get("specs", {})
        pricing = gpu_data.get("pricing", {})
        registered_by = gpu_data.get("registered_by", "0x0000000000000000000000000000000000000000")

        # Check if GPU already exists
        result = await session.execute(
            select(GPURegistry).where(GPURegistry.id == gpu_id)
        )
        existing_gpu = result.scalar_one_or_none()

        if existing_gpu:
            # Update existing GPU
            if specs:
                existing_gpu.model = specs.get("model", existing_gpu.model)
                existing_gpu.memory_gb = specs.get("memory_gb", existing_gpu.memory_gb)
                existing_gpu.cuda_version = specs.get("cuda_version", existing_gpu.cuda_version)
                existing_gpu.region = specs.get("region", existing_gpu.region)
                existing_gpu.capabilities = specs.get("capabilities", existing_gpu.capabilities)
            if pricing:
                existing_gpu.price_per_hour = pricing.get("price_per_hour", existing_gpu.price_per_hour)
            existing_gpu.status = "available"
            await session.commit()
        else:
            # Create new GPU
            new_gpu = GPURegistry(
                id=gpu_id,
                miner_id=miner_id,
                model=specs.get("model", "Unknown"),
                memory_gb=specs.get("memory_gb", 0),
                cuda_version=specs.get("cuda_version", ""),
                region=specs.get("region", ""),
                price_per_hour=pricing.get("price_per_hour", 0.0) if pricing else 0.0,
                status="available",
                capabilities=specs.get("capabilities", [])
            )
            session.add(new_gpu)
            await session.commit()

        # Record GPU registration on blockchain (async, non-blocking)
        try:
            import httpx
            import os
            
            blockchain_rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
            
            # Submit GPU_REGISTER transaction to blockchain
            transaction_payload = {
                "from": registered_by,
                "to": "0x0000000000000000000000000000000000000000",
                "amount": 0,
                "fee": 10,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "payload": {
                    "gpu_id": gpu_id,
                    "miner_id": miner_id,
                    "gpu_model": specs.get("model", "Unknown"),
                    "memory_gb": specs.get("memory_gb", 0),
                    "cuda_cores": specs.get("cuda_cores", 0),
                    "compute_capability": specs.get("compute_capability", ""),
                    "price_per_hour": pricing.get("price_per_hour", 0.0) if pricing else 0.0,
                    "description": specs.get("description", ""),
                    "provider_address": registered_by
                },
                "signature": ""
            }
            
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.post(
                    f"{blockchain_rpc_url}/rpc/transaction",
                    json=transaction_payload
                )
                response.raise_for_status()
            logger.info(f"GPU {gpu_id} registered on blockchain")
        except Exception as blockchain_error:
            logger.warning(f"Failed to register GPU on blockchain (non-blocking): {blockchain_error}")

        return {
            "status": "created" if not existing_gpu else "updated",
            "gpu_id": gpu_id,
            "miner_id": miner_id,
            "message": "GPU registered successfully"
        }
    except Exception as e:
        await session.rollback()
        logger.error(f"GPU registration error: {e}")
        return {"error": str(e)}, 500


@app.post("/v1/miners/register")
async def register_miner(
    miner_data: dict,
    session: AsyncSession = Depends(get_session_dep),
):
    """Register or update a miner"""
    from uuid import uuid4

    from sqlalchemy import select

    from .domain.gpu_marketplace import GPURegistry

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
    from sqlalchemy import update

    from .domain.gpu_marketplace import GPURegistry

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
    from sqlalchemy import select

    from .domain.gpu_marketplace import GPURegistry

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
    from sqlalchemy import update

    from .domain.gpu_marketplace import GPURegistry

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
    uvicorn.run(app, host="127.0.0.1", port=8101)
