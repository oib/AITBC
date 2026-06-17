"""
Marketplace Service main application
Manages hardware+software bundle marketplace operations
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.middleware import (  # noqa: E402
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

from .services.marketplace_service import MarketplaceService  # noqa: E402
from .services.matching_service import MatchingService  # noqa: E402
from .storage import get_session, init_db  # noqa: E402

configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Marketplace Service."""
    logger.info("Starting Marketplace Service")
    await init_db()
    yield
    logger.info("Shutting down Marketplace Service")


app = FastAPI(
    title="AITBC Marketplace Service",
    description="Manages hardware+software bundle marketplace operations",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
app.add_middleware(ErrorHandlerMiddleware)
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
async def ready() -> Any:
    """Readiness check - verifies database connectivity"""
    try:
        from .storage import get_session_context

        async with get_session_context() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        return {"status": "ready", "service": "marketplace-service"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "service": "marketplace-service", "error": str(e)}
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "marketplace-service"}


@app.get("/v1/marketplace/status")
async def marketplace_status() -> dict[str, str]:
    """Get marketplace status"""
    return {"status": "operational", "service": "marketplace-service", "message": "Marketplace service is running"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def get_marketplace_service(session: Annotated[AsyncSession, Depends(get_session)]) -> MarketplaceService:
    """Get marketplace service instance"""
    return MarketplaceService(session)


async def get_matching_service(session: Annotated[AsyncSession, Depends(get_session)]) -> MatchingService:
    """Get matching service instance"""
    return MatchingService(session)


@app.get("/v1/marketplace/offers")
async def get_offers(
    status: str | None,
    region: str | None,
    gpu_model: str | None,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """Get marketplace offers"""
    try:
        logger.info(
            "GET /v1/marketplace/offers called with filters: status=%s, region=%s, gpu_model=%s", status, region, gpu_model
        )
        result = await svc.list_offers(status=status, region=region, gpu_model=gpu_model)
        logger.info("GET /v1/marketplace/offers returned %s offers", len(result))
        return result
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offers: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offers/{offer_id}")
async def get_offer(offer_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get a specific marketplace offer"""
    try:
        logger.info("GET /v1/marketplace/offers/%s called", offer_id)
        result = await svc.get_offer(offer_id)
        logger.info("GET /v1/marketplace/offers/%s returned: %s", offer_id, result is not None)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offers/%s: %s: %s", offer_id, type(e).__name__, str(e))
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
                logger.info("Escrow created for job %s: %s", job_id, resp.json().get("contract_id"))
            else:
                logger.warning("Escrow creation returned %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logger.warning("Escrow creation skipped (non-fatal): %s", e)


@app.post("/v1/marketplace/offers/{offer_id}/book")
async def book_offer(
    offer_id: str,
    booking_data: dict[str, Any],
    background_tasks: BackgroundTasks,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """Book/purchase a marketplace offer"""
    try:
        logger.info("POST /v1/marketplace/offers/%s/book called with data keys: %s", offer_id, booking_data.keys())
        result = await svc.book_offer(offer_id, booking_data)
        logger.info("POST /v1/marketplace/offers/%s/book completed", offer_id)
        buyer = booking_data.get("wallet") or booking_data.get("buyer")
        provider = result.get("provider") or booking_data.get("provider")
        amount = float(booking_data.get("amount") or booking_data.get("price") or 0)
        bid_id = result.get("bid_id")
        if bid_id and buyer and provider and amount:
            background_tasks.add_task(_create_escrow_bg, bid_id, buyer, provider, amount)
            result["escrow_contract_id"] = "(pending — created in background)"
        return result
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offers/%s/book: %s: %s", offer_id, type(e).__name__, str(e))
        raise


@app.post("/v1/marketplace/offers")
async def create_offer(
    offer_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Create a new marketplace offer"""
    try:
        logger.info("POST /v1/marketplace/offers called with data keys: %s", offer_data.keys())
        if "provider" not in offer_data:
            if "wallet" in offer_data:
                offer_data["provider"] = offer_data["wallet"]
            elif "metadata" in offer_data and "provider" in offer_data.get("metadata", {}):
                offer_data["provider"] = offer_data["metadata"]["provider"]
            else:
                offer_data["provider"] = "default-provider"
        result = await svc.create_offer(offer_data)
        logger.info("POST /v1/marketplace/offers created offer with id: %s", result.id)
        return result
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offers: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/analytics")
async def get_analytics(period_type: str | None, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get marketplace analytics"""
    return await svc.get_analytics(period_type=period_type)


@app.get("/v1/marketplace")
async def get_marketplace_overview(svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get hardware+software bundle marketplace overview"""
    logger.info("GET /v1/marketplace called - marketplace overview")
    offers = await svc.list_offers()
    active_offers = [o for o in offers if o.get("status") == "active"]
    avg_price = 0
    if active_offers:
        total_price = sum(o.get("price_per_hour", 0) for o in active_offers)
        avg_price = total_price / len(active_offers)
    return {
        "status": "operational",
        "total_offers": len(offers),
        "active_offers": len(active_offers),
        "average_price_per_hour": avg_price,
        "regions": list({o.get("region", "unknown") for o in active_offers}),
        "service_types": list({o.get("service_type", "unknown") for o in active_offers}),
        "timestamp": svc.get_current_timestamp(),
    }


@app.get("/v1/marketplace/offers/{offer_id}/history")
async def get_offer_history(offer_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get offer history (migrated from Coordinator API)"""
    logger.info("GET /v1/marketplace/offers/%s/history called", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return ({"error": "Offer not found"}, 404)
    history = {
        "offer_id": offer_id,
        "created_at": offer.created_at,
        "price_history": [{"price": offer.price_per_hour, "timestamp": offer.created_at, "reason": "initial_listing"}],
        "booking_count": 0,
        "total_revenue": 0,
        "last_booked": None,
    }
    return history


@app.post("/v1/marketplace/offers/{offer_id}/cancel")
async def cancel_offer(
    offer_id: str, reason: str | None, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Cancel offer (migrated from Coordinator API)"""
    logger.info("POST /v1/marketplace/offers/%s/cancel called", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return ({"error": "Offer not found"}, 404)
    if offer.status == "cancelled":
        return ({"error": "Offer already cancelled"}, 400)
    await svc.update_offer_status(offer_id, "cancelled")
    cancelled_offer = {
        "offer_id": offer_id,
        "status": "cancelled",
        "cancelled_at": svc.get_current_timestamp(),
        "reason": reason or "user_requested",
    }
    logger.info("Cancelled offer %s", offer_id)
    return cancelled_offer


@app.get("/v1/marketplace/performance")
async def get_marketplace_performance(
    period: str | None, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Get marketplace performance metrics (migrated from Coordinator API)"""
    logger.info("GET /v1/marketplace/performance called with period=%s", period)
    analytics = await svc.get_analytics(period_type=period)
    performance = {
        "period": period,
        "total_volume": analytics.get("total_volume", 0),
        "total_trades": analytics.get("total_trades", 0),
        "average_price": analytics.get("average_price", 0),
        "price_volatility": analytics.get("price_volatility", 0),
        "liquidity_score": analytics.get("liquidity_score", 0),
        "active_providers": analytics.get("active_providers", 0),
        "utilization_rate": analytics.get("utilization_rate", 0),
        "fill_rate": analytics.get("fill_rate", 0),
    }
    return performance


@app.post("/v1/marketplace/dynamic-pricing")
async def calculate_dynamic_pricing(
    offer_id: str,
    current_demand: int,
    current_supply: int,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """Calculate dynamic pricing based on supply/demand (migrated from Coordinator API)"""
    logger.info("POST /v1/marketplace/dynamic-pricing called for offer %s", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return ({"error": "Offer not found"}, 404)
    base_price = offer.price_per_hour or 0
    supply_demand_ratio = current_demand / max(current_supply, 1)
    if supply_demand_ratio > 1.5:
        price_multiplier = 1.2
    elif supply_demand_ratio > 1.0:
        price_multiplier = 1.1
    elif supply_demand_ratio < 0.5:
        price_multiplier = 0.9
    else:
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
        "reason": "dynamic_pricing_calculation",
    }


@app.get("/v1/marketplace/plugins")
async def get_plugins(plugin_type: str | None = None, status: str = "approved") -> Any:
    """Get marketplace plugins"""
    logger.info("GET /v1/marketplace/plugins called with type=%s, status=%s", plugin_type, status)
    return {
        "plugins": [
            {
                "id": "ollama-integration",
                "name": "Ollama Integration",
                "version": "1.0.0",
                "description": "Integrate Ollama for local LLM inference",
                "author": "AITBC Team",
                "status": "active",
                "downloads": 1250,
            },
            {
                "id": "ipfs-storage",
                "name": "IPFS Storage",
                "version": "1.2.0",
                "description": "Decentralized storage using IPFS",
                "author": "AITBC Team",
                "status": "active",
                "downloads": 890,
            },
            {
                "id": "gpu-optimizer",
                "name": "GPU Optimizer",
                "version": "0.9.0",
                "description": "Optimize GPU utilization for ML workloads",
                "author": "Community",
                "status": "beta",
                "downloads": 450,
            },
        ],
        "total": 3,
    }


@app.post("/v1/marketplace/plugins")
async def register_plugin(
    plugin_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Register a new plugin"""
    try:
        logger.info("POST /v1/marketplace/plugins called with data keys: %s", plugin_data.keys())
        result = await svc.register_plugin(plugin_data)
        logger.info("POST /v1/marketplace/plugins registered plugin with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/plugins: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offer")
async def list_software_offers(
    service_type: str | None,
    status: str | None,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """List marketplace offers (hardware+software bundles)"""
    try:
        logger.info("GET /v1/marketplace/offer called with filters: service_type=%s, status=%s", service_type, status)
        result = await svc.list_software_services(service_type=service_type, status=status)
        logger.info("GET /v1/marketplace/offer returned %s offers", len(result))
        return {"offers": result, "total": len(result)}
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offer: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offer/{plugin_id}")
async def get_software_offer(plugin_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get a specific marketplace offer"""
    try:
        logger.info("GET /v1/marketplace/offer/%s called", plugin_id)
        result = await svc.get_software_service(plugin_id)
        if not result:
            return ({"error": "Offer not found"}, 404)
        logger.info("GET /v1/marketplace/offer/%s returned offer", plugin_id)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offer/%s: %s: %s", plugin_id, type(e).__name__, str(e))
        raise


@app.post("/v1/marketplace/offer")
async def register_offer(
    service_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Register or update a marketplace offer"""
    try:
        logger.info("POST /v1/marketplace/offer called with data keys: %s", service_data.keys())
        result = await svc.register_software_service(service_data)
        logger.info("POST /v1/marketplace/offer registered offer: %s", result["plugin_id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offer: %s: %s", type(e).__name__, str(e))
        raise


@app.delete("/v1/marketplace/offer/{plugin_id}")
async def unregister_offer(plugin_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Unregister a marketplace offer"""
    try:
        logger.info("DELETE /v1/marketplace/offer/%s called", plugin_id)
        result = await svc.unregister_software_service(plugin_id)
        logger.info("DELETE /v1/marketplace/offer/%s completed", plugin_id)
        return result
    except Exception as e:
        logger.error("Error in DELETE /v1/marketplace/offer/%s: %s: %s", plugin_id, type(e).__name__, str(e))
        raise


@app.post("/v1/knowledge-graph")
async def create_graph(
    graph_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Create a new knowledge graph"""
    try:
        logger.info("POST /v1/knowledge-graph called with data keys: %s", graph_data.keys())
        result = await svc.create_graph(graph_data)
        logger.info("POST /v1/knowledge-graph created graph with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/knowledge-graph: %s: %s", type(e).__name__, str(e))
        raise


@app.post("/v1/knowledge-graph/{graph_id}/nodes")
async def add_node(
    graph_id: str, node_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Add a node to a knowledge graph"""
    try:
        node_data["graph_id"] = graph_id
        logger.info("POST /v1/knowledge-graph/%s/nodes called", graph_id)
        result = await svc.add_node(node_data)
        logger.info("Added node with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/knowledge-graph/%s/nodes: %s: %s", graph_id, type(e).__name__, str(e))
        raise


@app.post("/v1/knowledge-graph/{graph_id}/edges")
async def add_edge(
    graph_id: str, edge_data: dict[str, Any], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Add an edge to a knowledge graph"""
    try:
        edge_data["graph_id"] = graph_id
        logger.info("POST /v1/knowledge-graph/%s/edges called", graph_id)
        result = await svc.add_edge(edge_data)
        logger.info("Added edge with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/knowledge-graph/%s/edges: %s: %s", graph_id, type(e).__name__, str(e))
        raise


@app.get("/v1/knowledge-graph/{graph_id}")
async def query_graph(graph_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Query a knowledge graph"""
    try:
        logger.info("GET /v1/knowledge-graph/%s called", graph_id)
        result = await svc.query_graph(graph_id)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/knowledge-graph/%s: %s: %s", graph_id, type(e).__name__, str(e))
        raise


class RatingRequest(BaseModel):
    """Request model for service rating"""

    rating: float
    reviewer_id: str
    comment: str = ""


@app.post("/v1/marketplace/offer/{service_id}/rate")
async def rate_service(
    service_id: str, rating_data: RatingRequest, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Rate a marketplace service offer"""
    try:
        logger.info("POST /v1/marketplace/offer/%s/rate called with rating=%s", service_id, rating_data.rating)
        rating = await svc.add_service_rating(
            service_id=service_id, rating=rating_data.rating, reviewer_id=rating_data.reviewer_id, comment=rating_data.comment
        )
        return {
            "status": "success",
            "rating": {
                "id": rating.id,
                "service_id": rating.service_id,
                "rating": rating.rating,
                "reviewer_id": rating.reviewer_id,
                "comment": rating.comment,
                "created_at": rating.created_at.isoformat() if rating.created_at else None,
            },
        }
    except ValueError as e:
        logger.error("Validation error in rate_service: %s", str(e))
        return ({"error": str(e)}, 400)
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offer/%s/rate: %s: %s", service_id, type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offer/{service_id}/ratings")
async def get_service_ratings(
    service_id: str,
    limit: int | None,
    offset: int | None,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """Get ratings for a marketplace service offer"""
    try:
        logger.info("GET /v1/marketplace/offer/%s/ratings called", service_id)
        ratings = await svc.get_service_ratings(service_id, limit, offset)
        service = await svc.get_software_service(service_id)
        if not service:
            service = await svc.get_service_by_offer_id(service_id)
        service_info = (
            {
                "avg_rating": service.get("avg_rating", 0.0) if service else 0.0,
                "rating_count": service.get("rating_count", 0) if service else 0,
            }
            if service
            else {"avg_rating": 0.0, "rating_count": 0}
        )
        return {
            "service_id": service_id,
            "service_info": service_info,
            "ratings": ratings,
            "count": len(ratings),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offer/%s/ratings: %s: %s", service_id, type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offer-by-id/{offer_id}")
async def get_offer_by_id(offer_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get a marketplace service offer by offer_id (blockchain offer ID)"""
    try:
        logger.info("GET /v1/marketplace/offer-by-id/%s called", offer_id)
        service = await svc.get_service_by_offer_id(offer_id)
        if not service:
            return ({"error": "Service not found"}, 404)
        return service
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offer-by-id/%s: %s: %s", offer_id, type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/ratings/unsynced")
async def get_unsynced_ratings(limit: int | None, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get ratings that haven't been synced to remote nodes"""
    try:
        logger.info("GET /v1/marketplace/ratings/unsynced called")
        ratings = await svc.get_unsynced_ratings(limit)
        return {"ratings": ratings, "count": len(ratings)}
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/ratings/unsynced: %s: %s", type(e).__name__, str(e))
        raise


@app.post("/v1/marketplace/ratings/sync")
async def sync_ratings(
    ratings: list[dict[str, Any]], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Sync ratings from remote node"""
    try:
        logger.info("POST /v1/marketplace/ratings/sync called with %s ratings", len(ratings))
        result = await svc.sync_ratings_from_remote(ratings)
        return {"status": "success", **result}
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/ratings/sync: %s: %s", type(e).__name__, str(e))
        raise


@app.post("/v1/marketplace/ratings/mark-synced")
async def mark_ratings_synced(
    rating_ids: list[str], svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]
) -> Any:
    """Mark ratings as synced to remote nodes"""
    try:
        logger.info("POST /v1/marketplace/ratings/mark-synced called with %s IDs", len(rating_ids))
        count = await svc.mark_ratings_synced(rating_ids)
        return {"status": "success", "marked_synced": count}
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/ratings/mark-synced: %s: %s", type(e).__name__, str(e))
        raise


@app.post("/v1/transactions")
async def submit_transaction(
    transaction_data: dict[str, Any], session: Annotated[AsyncSession, Depends(get_session_dep)]
) -> Any:
    """Submit marketplace transaction"""
    from .domain.marketplace import MarketplaceOffer

    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "marketplace":
        return ({"error": "Invalid transaction type for marketplace service"}, 400)
    try:
        if action == "offer":
            offer = MarketplaceOffer(**transaction_data)
            session.add(offer)
        else:
            return ({"error": f"Invalid action: {action}. Only 'offer' is currently supported"}, 400)
        await session.commit()
        return {"status": "success"}
    except Exception as e:
        await session.rollback()
        logger.error("Transaction submission error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None,
    action: str | None,
    status: str | None,
    island_id: str | None,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> Any:
    """Query marketplace transactions"""
    from sqlalchemy import select

    from .domain.marketplace import MarketplaceOffer

    try:
        transactions = []
        if action == "offer" or not action:
            result = await session.execute(select(MarketplaceOffer))
            offers = result.scalars().all()
            transactions.extend(
                [
                    {
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
                        "created_at": o.created_at.isoformat() if o.created_at else None,
                    }
                    for o in offers
                ]
            )
        if status:
            transactions = [t for t in transactions if t.get("status") == status]
        if island_id:
            transactions = [t for t in transactions if t.get("provider") == island_id]
        return transactions
    except Exception as e:
        logger.error("Transaction query error: %s", e)
        return ({"error": str(e)}, 500)


if __name__ == "__main__":
    import os

    import uvicorn

    # Allow configuration via environment variable for multi-node deployments
    # Default to 0.0.0.0 to accept connections from other nodes
    host = os.getenv("MARKETPLACE_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("MARKETPLACE_BIND_PORT", "8102"))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
