"""
Marketplace Service main application
Manages hardware+software bundle marketplace operations
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import os

from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")

from aitbc import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
    configure_logging,
    get_logger,
)

from .services.marketplace_service import MarketplaceService
from .services.matching_service import MatchingService
from .storage import get_session, init_db

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
    description="Manages hardware+software bundle marketplace operations",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Add specific allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
app.add_middleware(ErrorHandlerMiddleware)


# Use get_session() directly as dependency - FastAPI handles async generators
get_session_dep = get_session


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="marketplace-service")


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness check - verifies database connectivity"""
    try:
        from .storage import get_session_context
        async with get_session_context() as session:
            # Test database connection
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "service": "marketplace-service"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "marketplace-service", "error": str(e)},
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "marketplace-service"}


@app.get("/v1/marketplace/status")
async def marketplace_status() -> dict[str, str]:
    """Get marketplace status"""
    return {
        "status": "operational",
        "service": "marketplace-service",
        "message": "Marketplace service is running",
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def get_marketplace_service(session: AsyncSession = Depends(get_session)) -> MarketplaceService:
    """Get marketplace service instance"""
    return MarketplaceService(session)


async def get_matching_service(session: AsyncSession = Depends(get_session)) -> MatchingService:
    """Get matching service instance"""
    return MatchingService(session)


@app.get("/v1/marketplace/offers")
async def get_offers(
    status: str | None = None,
    region: str | None = None,
    gpu_model: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace offers"""
    try:
        logger.info(f"GET /v1/marketplace/offers called with filters: status={status}, region={region}, gpu_model={gpu_model}")
        result = await svc.list_offers(status=status, region=region, gpu_model=gpu_model)
        logger.info(f"GET /v1/marketplace/offers returned {len(result)} offers")
        return result
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/offers: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/marketplace/offers/{offer_id}")
async def get_offer(
    offer_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get a specific marketplace offer"""
    try:
        logger.info(f"GET /v1/marketplace/offers/{offer_id} called")
        result = await svc.get_offer(offer_id)
        logger.info(f"GET /v1/marketplace/offers/{offer_id} returned: {result is not None}")
        return result
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/offers/{offer_id}: {type(e).__name__}: {str(e)}")
        raise


async def _create_escrow_bg(job_id: str, buyer: str, provider: str, amount: float) -> None:
    """Fire-and-forget escrow creation — runs outside the SQLAlchemy session."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{BLOCKCHAIN_RPC_URL}/rpc/escrow/create",
                json={"job_id": job_id, "buyer": buyer, "provider": provider, "amount": amount},
            )
            if resp.status_code == 200:
                logger.info(f"Escrow created for job {job_id}: {resp.json().get('contract_id')}")
            else:
                logger.warning(f"Escrow creation returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Escrow creation skipped (non-fatal): {e}")


@app.post("/v1/marketplace/offers/{offer_id}/book")
async def book_offer(
    offer_id: str,
    booking_data: dict,
    background_tasks: BackgroundTasks,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Book/purchase a marketplace offer"""
    try:
        logger.info(f"POST /v1/marketplace/offers/{offer_id}/book called with data keys: {booking_data.keys()}")
        result = await svc.book_offer(offer_id, booking_data)
        logger.info(f"POST /v1/marketplace/offers/{offer_id}/book completed")

        # Schedule escrow creation as a background task (outside SQLAlchemy session)
        buyer = booking_data.get("wallet") or booking_data.get("buyer")
        provider = result.get("provider") or booking_data.get("provider")
        amount = float(booking_data.get("amount") or booking_data.get("price") or 0)
        bid_id = result.get("bid_id")
        if bid_id and buyer and provider and amount:
            background_tasks.add_task(_create_escrow_bg, bid_id, buyer, provider, amount)
            result["escrow_contract_id"] = "(pending — created in background)"

        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/offers/{offer_id}/book: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/marketplace/offers")
async def create_offer(
    offer_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new marketplace offer"""
    try:
        logger.info(f"POST /v1/marketplace/offers called with data keys: {offer_data.keys()}")
        # Set provider from wallet or use a default
        if 'provider' not in offer_data:
            if 'wallet' in offer_data:
                offer_data['provider'] = offer_data['wallet']
            elif 'metadata' in offer_data and 'provider' in offer_data.get('metadata', {}):
                offer_data['provider'] = offer_data['metadata']['provider']
            else:
                offer_data['provider'] = 'default-provider'
        result = await svc.create_offer(offer_data)
        logger.info(f"POST /v1/marketplace/offers created offer with id: {result.id}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/offers: {type(e).__name__}: {str(e)}")
        raise




@app.get("/v1/marketplace/analytics")
async def get_analytics(
    period_type: str = "daily",
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace analytics"""
    return await svc.get_analytics(period_type=period_type)


# ===== Advanced Marketplace Features (Migrated from Coordinator API) =====

@app.get("/v1/marketplace")
async def get_marketplace_overview(
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get hardware+software bundle marketplace overview"""
    logger.info("GET /v1/marketplace called - marketplace overview")
    
    # Get marketplace statistics
    offers = await svc.list_offers()
    
    active_offers = [o for o in offers if o.get("status") == "active"]
    
    # Calculate average price
    avg_price = 0
    if active_offers:
        total_price = sum(o.get("price_per_hour", 0) for o in active_offers)
        avg_price = total_price / len(active_offers)
    
    return {
        "status": "operational",
        "total_offers": len(offers),
        "active_offers": len(active_offers),
        "average_price_per_hour": avg_price,
        "regions": list(set(o.get("region", "unknown") for o in active_offers)),
        "service_types": list(set(o.get("service_type", "unknown") for o in active_offers)),
        "timestamp": svc.get_current_timestamp()
    }




@app.get("/v1/marketplace/offers/{offer_id}/history")
async def get_offer_history(
    offer_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get offer history (migrated from Coordinator API)"""
    logger.info(f"GET /v1/marketplace/offers/{offer_id}/history called")
    
    # Get offer details
    offer = await svc.get_offer(offer_id)
    if not offer:
        return {"error": "Offer not found"}, 404
    
    # Placeholder for offer history - would query database for price changes, bookings, etc.
    history = {
        "offer_id": offer_id,
        "created_at": offer.get("created_at"),
        "price_history": [
            {
                "price": offer.get("price_per_hour"),
                "timestamp": offer.get("created_at"),
                "reason": "initial_listing"
            }
        ],
        "booking_count": 0,
        "total_revenue": 0,
        "last_booked": None
    }
    
    return history


@app.post("/v1/marketplace/offers/{offer_id}/cancel")
async def cancel_offer(
    offer_id: str,
    reason: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Cancel offer (migrated from Coordinator API)"""
    logger.info(f"POST /v1/marketplace/offers/{offer_id}/cancel called")
    
    # Get offer
    offer = await svc.get_offer(offer_id)
    if not offer:
        return {"error": "Offer not found"}, 404
    
    if offer.status == "cancelled":
        return {"error": "Offer already cancelled"}, 400
    
    # Update offer status to cancelled
    await svc.update_offer_status(offer_id, "cancelled")
    
    cancelled_offer = {
        "offer_id": offer_id,
        "status": "cancelled",
        "cancelled_at": svc.get_current_timestamp(),
        "reason": reason or "user_requested"
    }
    
    logger.info(f"Cancelled offer {offer_id}")
    return cancelled_offer


@app.get("/v1/marketplace/performance")
async def get_marketplace_performance(
    period: str = "daily",
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace performance metrics (migrated from Coordinator API)"""
    logger.info(f"GET /v1/marketplace/performance called with period={period}")
    
    # Get analytics data
    analytics = await svc.get_analytics(period_type=period)
    
    # Add performance-specific metrics
    performance = {
        "period": period,
        "total_volume": analytics.get("total_volume", 0),
        "total_trades": analytics.get("total_trades", 0),
        "average_price": analytics.get("average_price", 0),
        "price_volatility": analytics.get("price_volatility", 0),
        "liquidity_score": analytics.get("liquidity_score", 0),
        "active_providers": analytics.get("active_providers", 0),
        "utilization_rate": analytics.get("utilization_rate", 0),
        "fill_rate": analytics.get("fill_rate", 0)
    }
    
    return performance


@app.post("/v1/marketplace/dynamic-pricing")
async def calculate_dynamic_pricing(
    offer_id: str,
    current_demand: int,
    current_supply: int,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Calculate dynamic pricing based on supply/demand (migrated from Coordinator API)"""
    logger.info(f"POST /v1/marketplace/dynamic-pricing called for offer {offer_id}")
    
    # Get offer
    offer = await svc.get_offer(offer_id)
    if not offer:
        return {"error": "Offer not found"}, 404
    
    base_price = offer.get("price_per_hour", 0)
    
    # Calculate dynamic price based on supply/demand
    supply_demand_ratio = current_demand / max(current_supply, 1)
    
    # Price adjustment formula
    if supply_demand_ratio > 1.5:
        # High demand - increase price
        price_multiplier = 1.2
    elif supply_demand_ratio > 1.0:
        # Moderate demand - slight increase
        price_multiplier = 1.1
    elif supply_demand_ratio < 0.5:
        # Low demand - decrease price
        price_multiplier = 0.9
    else:
        # Balanced - no change
        price_multiplier = 1.0
    
    suggested_price = base_price * price_multiplier
    
    return {
        "offer_id": offer_id,
        "base_price": base_price,
        "suggested_price": suggested_price,
        "price_multiplier": price_multiplier,
        "supply_demand_ratio": supply_demand_ratio,
        "current_demand": current_demand,
        "current_supply": current_supply,
        "reason": "dynamic_pricing_calculation"
    }










@app.get("/v1/marketplace/plugins")
async def get_plugins(
    type: str | None = None,
    status: str = "approved",
):
    """Get marketplace plugins"""
    # Return fallback data directly without database dependency
    logger.info(f"GET /v1/marketplace/plugins called with type={type}, status={status}")
    return {
        "plugins": [
            {
                "id": "ollama-integration",
                "name": "Ollama Integration",
                "version": "1.0.0",
                "description": "Integrate Ollama for local LLM inference",
                "author": "AITBC Team",
                "status": "active",
                "downloads": 1250
            },
            {
                "id": "ipfs-storage",
                "name": "IPFS Storage",
                "version": "1.2.0",
                "description": "Decentralized storage using IPFS",
                "author": "AITBC Team",
                "status": "active",
                "downloads": 890
            },
            {
                "id": "gpu-optimizer",
                "name": "GPU Optimizer",
                "version": "0.9.0",
                "description": "Optimize GPU utilization for ML workloads",
                "author": "Community",
                "status": "beta",
                "downloads": 450
            }
        ],
        "total": 3
    }


@app.post("/v1/marketplace/plugins")
async def register_plugin(
    plugin_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Register a new plugin"""
    try:
        logger.info(f"POST /v1/marketplace/plugins called with data keys: {plugin_data.keys()}")
        result = await svc.register_plugin(plugin_data)
        logger.info(f"POST /v1/marketplace/plugins registered plugin with id: {result['id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/plugins: {type(e).__name__}: {str(e)}")
        raise


# ===== Software Service Registry (migrated from plugin service) =====

@app.get("/v1/marketplace/offer")
async def get_offers(
    service_type: str | None = None,
    status: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """List marketplace offers (hardware+software bundles)"""
    try:
        logger.info(f"GET /v1/marketplace/offer called with filters: service_type={service_type}, status={status}")
        result = await svc.list_software_services(service_type=service_type, status=status)
        logger.info(f"GET /v1/marketplace/offer returned {len(result)} offers")
        return {"offers": result, "total": len(result)}
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/offer: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/marketplace/offer/{plugin_id}")
async def get_offer(
    plugin_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get a specific marketplace offer"""
    try:
        logger.info(f"GET /v1/marketplace/offer/{plugin_id} called")
        result = await svc.get_software_service(plugin_id)
        if not result:
            return {"error": "Offer not found"}, 404
        logger.info(f"GET /v1/marketplace/offer/{plugin_id} returned offer")
        return result
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/offer/{plugin_id}: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/marketplace/offer")
async def register_offer(
    service_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Register or update a marketplace offer"""
    try:
        logger.info(f"POST /v1/marketplace/offer called with data keys: {service_data.keys()}")
        result = await svc.register_software_service(service_data)
        logger.info(f"POST /v1/marketplace/offer registered offer: {result['plugin_id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/offer: {type(e).__name__}: {str(e)}")
        raise


@app.delete("/v1/marketplace/offer/{plugin_id}")
async def unregister_offer(
    plugin_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Unregister a marketplace offer"""
    try:
        logger.info(f"DELETE /v1/marketplace/offer/{plugin_id} called")
        result = await svc.unregister_software_service(plugin_id)
        logger.info(f"DELETE /v1/marketplace/offer/{plugin_id} completed")
        return result
    except Exception as e:
        logger.error(f"Error in DELETE /v1/marketplace/offer/{plugin_id}: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/knowledge-graph")
async def create_graph(
    graph_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new knowledge graph"""
    try:
        logger.info(f"POST /v1/knowledge-graph called with data keys: {graph_data.keys()}")
        result = await svc.create_graph(graph_data)
        logger.info(f"POST /v1/knowledge-graph created graph with id: {result['id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/knowledge-graph: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/knowledge-graph/{graph_id}/nodes")
async def add_node(
    graph_id: str,
    node_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Add a node to a knowledge graph"""
    try:
        node_data["graph_id"] = graph_id
        logger.info(f"POST /v1/knowledge-graph/{graph_id}/nodes called")
        result = await svc.add_node(node_data)
        logger.info(f"Added node with id: {result['id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/knowledge-graph/{graph_id}/nodes: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/knowledge-graph/{graph_id}/edges")
async def add_edge(
    graph_id: str,
    edge_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Add an edge to a knowledge graph"""
    try:
        edge_data["graph_id"] = graph_id
        logger.info(f"POST /v1/knowledge-graph/{graph_id}/edges called")
        result = await svc.add_edge(edge_data)
        logger.info(f"Added edge with id: {result['id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/knowledge-graph/{graph_id}/edges: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/knowledge-graph/{graph_id}")
async def query_graph(
    graph_id: str,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Query a knowledge graph"""
    try:
        logger.info(f"GET /v1/knowledge-graph/{graph_id} called")
        result = await svc.query_graph(graph_id)
        return result
    except Exception as e:
        logger.error(f"Error in GET /v1/knowledge-graph/{graph_id}: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict, session: AsyncSession = Depends(get_session_dep)):
    """Submit marketplace transaction"""
    from .domain.marketplace import MarketplaceOffer

    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')

    if transaction_type != 'marketplace':
        return {"error": "Invalid transaction type for marketplace service"}, 400

    try:
        if action == 'offer':
            offer = MarketplaceOffer(**transaction_data)
            session.add(offer)
        else:
            return {"error": f"Invalid action: {action}. Only 'offer' is currently supported"}, 400

        await session.commit()
        return {"status": "success"}
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
    """Query marketplace transactions"""
    from sqlalchemy import select

    from .domain.marketplace import MarketplaceOffer

    try:
        transactions = []

        # Query offers
        if action == 'offer' or not action:
            result = await session.execute(select(MarketplaceOffer))
            offers = result.scalars().all()
            transactions.extend([{
                "id": o.id,
                "action": "offer",
                "provider": o.provider,
                "capacity": o.capacity,
                "price": o.price,
                "status": o.status,
                "gpu_model": o.gpu_model,
                "gpu_memory_gb": o.gpu_memory_gb,
                "gpu_count": o.gpu_count,
                "price_per_hour": o.price_per_hour,
                "region": o.region,
                "created_at": o.created_at.isoformat() if o.created_at else None
            } for o in offers])

        # Apply filters
        if status:
            transactions = [t for t in transactions if t.get('status') == status]
        if island_id:
            transactions = [t for t in transactions if t.get('provider') == island_id]

        return transactions
    except Exception as e:
        logger.error(f"Transaction query error: {e}")
        return {"error": str(e)}, 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8102)
