"""
Marketplace Service main application
Manages GPU marketplace operations
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
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

from marketplace_service.services.marketplace_service import MarketplaceService
from marketplace_service.services.matching_service import MatchingService
from marketplace_service.storage import get_session, init_db

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


@app.post("/v1/marketplace/offers/{offer_id}/book")
async def book_offer(
    offer_id: str,
    booking_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Book/purchase a marketplace offer"""
    try:
        logger.info(f"POST /v1/marketplace/offers/{offer_id}/book called with data keys: {booking_data.keys()}")
        result = await svc.book_offer(offer_id, booking_data)
        logger.info(f"POST /v1/marketplace/offers/{offer_id}/book completed")
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


@app.get("/v1/marketplace/bids")
async def get_bids(
    status: str | None = None,
    provider: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace bids"""
    try:
        logger.info(f"GET /v1/marketplace/bids called with filters: status={status}, provider={provider}")
        result = await svc.list_bids(status=status, provider=provider)
        logger.info(f"GET /v1/marketplace/bids returned {len(result)} bids")
        return result
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/bids: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/marketplace/bids")
async def create_bid(
    bid_data: dict,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new marketplace bid"""
    try:
        logger.info(f"POST /v1/marketplace/bids called with data keys: {bid_data.keys()}")
        result = await svc.create_bid(bid_data)
        logger.info(f"POST /v1/marketplace/bids created bid with id: {result.id}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/bids: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/marketplace/orders")
async def get_orders(
    wallet: str | None = None,
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace orders (alias for bids for CLI compatibility)"""
    try:
        logger.info(f"GET /v1/marketplace/orders called with wallet={wallet}")
        # Use list_bids with provider filter as orders are stored as bids
        result = await svc.list_bids(provider=wallet)
        # Return in format expected by CLI
        return {"orders": result}
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/orders: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/marketplace/analytics")
async def get_analytics(
    period_type: str = "daily",
    svc: MarketplaceService = Depends(get_marketplace_service),
):
    """Get marketplace analytics"""
    return await svc.get_analytics(period_type=period_type)


@app.post("/v1/marketplace/match")
async def find_match(
    bid_requirements: dict,
    max_price: float | None = None,
    preferred_region: str | None = None,
    min_gpu_memory: int | None = None,
    required_gpu_model: str | None = None,
    matching_svc: MatchingService = Depends(get_matching_service),
):
    """Find best matching offer for bid requirements"""
    try:
        logger.info(f"POST /v1/marketplace/match called with requirements: {bid_requirements.keys()}")
        result = await matching_svc.find_best_match(
            bid_requirements=bid_requirements,
            max_price=max_price,
            preferred_region=preferred_region,
            min_gpu_memory=min_gpu_memory,
            required_gpu_model=required_gpu_model
        )
        logger.info(f"Match result: {result is not None}")
        return result or {"message": "No matching offer found"}
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/match: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/marketplace/matches")
async def create_match(
    bid_id: str,
    offer_id: str,
    match_data: dict,
    matching_svc: MatchingService = Depends(get_matching_service),
):
    """Create a match between a bid and an offer"""
    try:
        logger.info(f"POST /v1/marketplace/matches called: bid_id={bid_id}, offer_id={offer_id}")
        result = await matching_svc.create_match(bid_id, offer_id, match_data)
        logger.info(f"Created match: {result['match_id']}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/matches: {type(e).__name__}: {str(e)}")
        raise


@app.get("/v1/marketplace/matches")
async def list_matches(
    status: str | None = None,
    provider: str | None = None,
    matching_svc: MatchingService = Depends(get_matching_service),
):
    """List all matches"""
    try:
        logger.info(f"GET /v1/marketplace/matches called with filters: status={status}, provider={provider}")
        result = await matching_svc.list_matches(status=status, provider=provider)
        logger.info(f"Found {len(result)} matches")
        return {"matches": result}
    except Exception as e:
        logger.error(f"Error in GET /v1/marketplace/matches: {type(e).__name__}: {str(e)}")
        raise


@app.post("/v1/marketplace/matches/auto")
async def auto_match(
    matching_svc: MatchingService = Depends(get_matching_service),
):
    """Automatically match all pending bids with available offers"""
    try:
        logger.info("POST /v1/marketplace/matches/auto called")
        result = await matching_svc.auto_match_pending_bids()
        logger.info(f"Auto-match complete: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in POST /v1/marketplace/matches/auto: {type(e).__name__}: {str(e)}")
        raise


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
    from marketplace_service.marketplace import MarketplaceBid, MarketplaceOffer

    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')

    if transaction_type != 'marketplace':
        return {"error": "Invalid transaction type for marketplace service"}, 400

    try:
        if action == 'offer':
            offer = MarketplaceOffer(**transaction_data)
            session.add(offer)
        elif action == 'bid':
            bid = MarketplaceBid(**transaction_data)
            session.add(bid)
        else:
            return {"error": f"Invalid action: {action}. Only 'offer' and 'bid' are currently supported"}, 400

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

    from marketplace_service.marketplace import MarketplaceBid, MarketplaceOffer

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

        # Query bids
        if action == 'bid' or not action:
            result = await session.execute(select(MarketplaceBid))
            bids = result.scalars().all()
            transactions.extend([{
                "id": b.id,
                "action": "bid",
                "provider": b.provider,
                "capacity": b.capacity,
                "price": b.price,
                "status": b.status,
                "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None
            } for b in bids])

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
    uvicorn.run(app, host="0.0.0.0", port=8102)
