"""
Marketplace Service main application
Manages hardware+software bundle marketplace operations
"""

import os
from aitbc.constants import BLOCKCHAIN_RPC_URL as _DEFAULT_RPC_URL
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from aitbc.middleware import setup_cors
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", _DEFAULT_RPC_URL)
from aitbc.auth import APIKeyAuthenticator  # noqa: E402
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.marketplace import OfferStatus  # noqa: E402
from aitbc.middleware import (  # noqa: E402
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)
from aitbc.rate_limiting import RateLimitMiddleware  # noqa: E402

from .config import settings  # noqa: E402
from .domain.offer_status import try_to_offer_status  # noqa: E402
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
setup_cors(app, allow_origins=["http://localhost:3000", "http://localhost:8080"])
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
# V23-32a: this service had no rate limiting at all, while feature_flags.json reported
# `enable_marketplace_rate_limiting` as on at 100% rollout since 2026-05-24.
#
# Middleware rather than the @rate_limit decorator: none of the 38 handlers here declare a
# `request: Request` parameter, so the decorator would find nothing to key on and put every
# caller in one shared bucket -- one client could then lock out the rest. The middleware
# always has the request and keys by client IP.
app.add_middleware(
    RateLimitMiddleware,
    rate=settings.rate_limit_requests,
    per=settings.rate_limit_window_seconds,
    exclude_paths=["/health", "/ready", "/live", "/metrics"],
    error_message="Marketplace rate limit exceeded",
)
app.add_middleware(ErrorHandlerMiddleware)
get_session_dep = get_session


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(**create_simple_health_response("marketplace-service"))


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


require_marketplace_api_key = APIKeyAuthenticator(
    expected_key=settings.api_key,
    auth_enabled=settings.auth_enabled,
    success_role="marketplace_admin",
)


@app.get("/v1/marketplace/offers")
async def get_offers(
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    status: str | None = None,
    region: str | None = None,
    gpu_model: str | None = None,
    chain_id: str | None = None,
) -> Any:
    """Get marketplace offers (v0.6.6: optional chain_id filter)"""
    try:
        logger.info(
            "GET /v1/marketplace/offers called with filters: status=%s, region=%s, gpu_model=%s, chain_id=%s",
            status,
            region,
            gpu_model,
            chain_id,
        )
        result = await svc.list_offers(status=status, region=region, gpu_model=gpu_model, chain_id=chain_id)
        logger.info("GET /v1/marketplace/offers returned %s offers", len(result))
        return result
    except ValueError as e:
        # A status filter naming a state that does not exist. It used to return 200 and an
        # empty list, which reads as "no offers are in that state" rather than "there is no
        # such state" -- the same answer a typo gets and a real filter gets (V23-83).
        logger.info("Rejecting offer listing: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offers: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offers/{offer_id}")
async def get_offer(offer_id: str, svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get a specific marketplace offer"""
    try:
        logger.info("GET /v1/marketplace/offers/%s called", offer_id)
        result = await svc.get_offer(offer_id)
        if not result:
            # `get_offer` returns None for an offer that is not there, and this route used to
            # hand that straight back -- 200 with a body of `null`. Every other "not found" in
            # this service is a 404 with this exact body, including the three other callers of
            # this same method and the sibling `/offers/{id}/history` over the same resource.
            # A client that checked the status code got told the offer existed (V23-76).
            logger.info("GET /v1/marketplace/offers/%s: not found", offer_id)
            return JSONResponse(status_code=404, content={"error": "Offer not found"})
        logger.info("GET /v1/marketplace/offers/%s returned an offer", offer_id)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offers/%s: %s: %s", offer_id, type(e).__name__, str(e))
        raise


async def _create_escrow_bg(job_id: str, buyer: str, provider: str, amount: Decimal) -> None:
    """Fire-and-forget escrow creation — runs outside the SQLAlchemy session."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.blockchain_rpc_url}/rpc/escrow/create",
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
        # `svc.book_offer` signals both "no such offer" and "offer is not available" by
        # raising ValueError, and this handler re-raised both into a 500 -- so booking a
        # typo'd offer id looked like the service had fallen over (V23-81). Checked here in
        # the shape `cancel_offer` uses over the same resource: 404 for absent, 400 for the
        # wrong state, same body. The service keeps its ValueErrors as the backstop.
        offer = await svc.get_offer(offer_id)
        if not offer:
            return JSONResponse(status_code=404, content={"error": "Offer not found"})
        if try_to_offer_status(offer.status) is not OfferStatus.AVAILABLE:
            return JSONResponse(status_code=400, content={"error": f"Offer is not available (status={offer.status})"})
        result = await svc.book_offer(offer_id, booking_data)
        logger.info("POST /v1/marketplace/offers/%s/book completed", offer_id)
        buyer = booking_data.get("wallet") or booking_data.get("buyer")
        provider = booking_data.get("provider") or result.get("provider")
        amount = Decimal(str(booking_data.get("amount") or booking_data.get("price") or 0))
        bid_id = result.get("bid_id")
        if bid_id and buyer and provider and amount:
            background_tasks.add_task(_create_escrow_bg, bid_id, buyer, provider, amount)
            result["escrow_contract_id"] = "(pending — created in background)"
        return result
    except ValueError as e:
        # The pre-check narrows the window but does not close it: another request can book
        # the offer between the two calls, and `svc.book_offer` raises `ValueError` again.
        # Every `ValueError` reachable from here is the caller's -- the service's two status
        # checks, plus `float(duration_hours)` over a request field -- so 400 is right for
        # all of them, and a race no longer reads as the service failing.
        #
        # Not `Decimal(price)`: that raises `InvalidOperation`, an `ArithmeticError`, and
        # still reaches the client as a 500. Left alone because the same conversion runs
        # again below on `amount`, after the bid has been committed, where answering 400
        # would deny a booking that happened.
        logger.info("Rejecting booking of offer %s: %s", offer_id, e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offers/%s/book: %s: %s", offer_id, type(e).__name__, str(e))
        raise


@app.post("/v1/marketplace/bids/{bid_id}/complete")
async def complete_bid(
    bid_id: str,
    request_data: dict[str, Any],
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
) -> Any:
    """Complete a marketplace bid after on-chain payment confirms."""
    try:
        tx_hash = request_data.get("tx_hash") or request_data.get("transaction_hash", "")
        if not tx_hash:
            return JSONResponse(status_code=400, content={"error": "tx_hash is required"})
        result = await svc.complete_bid(bid_id, tx_hash)
        return result
    except ValueError as e:
        logger.info("Rejecting bid completion: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/bids/%s/complete: %s: %s", bid_id, type(e).__name__, str(e))
        raise


class MatchRequest(BaseModel):
    """Request model for marketplace matching (v0.6.6)."""

    requirements: dict[str, Any] = Field(default_factory=dict)
    max_price: Decimal | None = None
    preferred_region: str | None = None
    chain_id: str | None = None


@app.post("/v1/marketplace/match")
async def match_request(request: MatchRequest, svc: Annotated[MatchingService, Depends(get_matching_service)]) -> Any:
    """Match a compute request to the best available GPU offer (v0.6.6).

    Uses price-time priority matching and integrates with the agent-coordinator
    task queue. Reserves the matched offer via OfferFSM.
    """
    try:
        logger.info("POST /v1/marketplace/match called (chain_id=%s)", request.chain_id)
        match = await svc.match_and_assign(
            request.requirements,
            max_price=request.max_price,
            preferred_region=request.preferred_region,
            chain_id=request.chain_id,
        )
        return {"status": "success", "match": match}
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/match: %s: %s", type(e).__name__, str(e))
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
    except ValueError as e:
        # Only reachable from the status validation the service now does: a request naming a
        # state this service does not have. 400 rather than the 500 that splatting the body
        # into the model produced for every other kind of bad field (V23-83).
        logger.info("Rejecting offer creation: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offers: %s: %s", type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/analytics")
async def get_analytics(
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    # `period_type: str | None` with no default is a *required* query parameter to FastAPI --
    # the same accident V23-83 found on cancel_offer and v0.6.6 found on /offers. The service
    # below has always declared `period_type: str = "daily"`, and that default was unreachable:
    # a caller who omitted the parameter got 422 instead, and one who supplied it overrode it.
    # Stating "daily" here restores the intended behaviour and puts the default in the spec.
    period_type: str = "daily",
) -> Any:
    """Get marketplace analytics"""
    return await svc.get_analytics(period_type=period_type)


@app.get("/v1/marketplace")
async def get_marketplace_overview(svc: Annotated[MarketplaceService, Depends(get_marketplace_service)]) -> Any:
    """Get hardware+software bundle marketplace overview"""
    logger.info("GET /v1/marketplace called - marketplace overview")
    offers = await svc.list_offers()
    # By state, not by spelling: one of the four offers in the deployed database is stored as
    # "open", so it was counted in `total_offers` and left out of `active_offers`, and left out
    # of the regions and service types the overview advertises -- an offer that is available
    # and invisible (V23-83).
    active_offers = [o for o in offers if try_to_offer_status(str(o.get("status", ""))) is OfferStatus.AVAILABLE]
    avg_price = Decimal("0")
    if active_offers:
        # `.get("price_per_hour", 0)` returns the default only when the key is missing, and it
        # never is -- `list_offers` puts it in every dict. `price_per_hour` is nullable and
        # defaults to None, so one priceless offer made this `int + None` and the whole
        # overview answered 500. Not reachable before: `active_offers` was only ever empty in
        # the tests, and every offer in the deployed database happens to carry a price
        # (V23-83).
        # Via `str` because these dicts are untyped: a price that arrived as a float would
        # otherwise raise on `Decimal + float` rather than quietly rounding.
        prices = [Decimal(str(o.get("price_per_hour") or 0)) for o in active_offers]
        avg_price = sum(prices, Decimal("0")) / len(active_offers)
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
        return JSONResponse(status_code=404, content={"error": "Offer not found"})
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
    offer_id: str,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    # `reason: str | None` with no default is a *required* query parameter to FastAPI, and the
    # published spec said so. Cancelling without one answered 422 -- so the 500 underneath was
    # only reachable by a caller who happened to send `?reason=`, which is why this endpoint
    # looked merely awkward rather than broken. The body already defaults it (V23-83).
    reason: str | None = None,
) -> Any:
    """Cancel offer (migrated from Coordinator API)"""
    logger.info("POST /v1/marketplace/offers/%s/cancel called", offer_id)
    offer = await svc.get_offer(offer_id)
    if not offer:
        return JSONResponse(status_code=404, content={"error": "Offer not found"})

    current = try_to_offer_status(offer.status)
    if current is OfferStatus.DELISTED:
        # Compared by state: "closed" and "delisted" are this end state too, and an offer
        # stored under either used to fall through to the transition and be told the
        # transition was invalid, rather than that it was already cancelled.
        return JSONResponse(status_code=400, content={"error": "Offer already cancelled"})
    if current is None:
        return JSONResponse(status_code=400, content={"error": f"Offer has an unknown status: '{offer.status}'"})
    try:
        await svc.update_offer_status(offer_id, "cancelled")
    except ValueError:
        # Reached for an offer someone holds: RESERVED can go to IN_USE, back to AVAILABLE, or
        # EXPIRED, but not straight to DELISTED -- a provider cannot delist out from under a
        # buyer who has reserved. 400 rather than 409 to match `book_offer` over this same
        # resource, where 409 is reserved for optimistic-concurrency mismatches (V23-81).
        logger.info("Refusing to cancel offer %s in status %s", offer_id, offer.status)
        return JSONResponse(
            status_code=400,
            content={"error": f"Offer cannot be cancelled while it is {offer.status}"},
        )
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
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    # Required by the same accident as /analytics above, and feeding the same service default.
    period: str = "daily",
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
        return JSONResponse(status_code=404, content={"error": "Offer not found"})
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
    suggested_price = base_price * Decimal(str(price_multiplier))
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
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    service_type: str | None = None,
    status: str | None = None,
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
            return JSONResponse(status_code=404, content={"error": "Offer not found"})
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
    except ValueError as e:
        # The service signals "not found" with ValueError; without this it surfaced as a 500.
        logger.info("DELETE /v1/marketplace/offer/%s not found: %s", plugin_id, e)
        raise HTTPException(status_code=404, detail=str(e)) from e
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
        # `add_service_rating` never checked that the service exists, and the aggregate it
        # then updates is guarded by `if service:` -- so rating a service that is not there
        # answered 200 and wrote an orphan row that no aggregate would ever count (V23-81).
        # A service id resolves either way round, the same two lookups `get_service_ratings`
        # does below.
        if not (await svc.get_software_service(service_id) or await svc.get_service_by_offer_id(service_id)):
            return JSONResponse(status_code=404, content={"error": "Service not found"})
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
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/marketplace/offer/%s/rate: %s: %s", service_id, type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/offer/{service_id}/ratings")
async def get_service_ratings(
    service_id: str,
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    # Paging that could not be omitted: both were required, so "give me the first page" was
    # spelled `?limit=50&offset=0` or it was a 422. The service's own `limit: int = 50,
    # offset: int = 0` say what the first page should be; these now say the same thing.
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Get ratings for a marketplace service offer"""
    try:
        logger.info("GET /v1/marketplace/offer/%s/ratings called", service_id)
        ratings = await svc.get_service_ratings(service_id, limit, offset)
        service = await svc.get_software_service(service_id)
        if not service:
            service = await svc.get_service_by_offer_id(service_id)
        # The handler already resolved the service and already knew it was absent; it just
        # never said so, answering 200 with a zeroed `service_info` and an empty list that a
        # client cannot tell from a real service nobody has rated yet (V23-81).
        if not service:
            return JSONResponse(status_code=404, content={"error": "Service not found"})
        service_info = {
            "avg_rating": service.get("avg_rating", 0.0),
            "rating_count": service.get("rating_count", 0),
        }
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
            return JSONResponse(status_code=404, content={"error": "Service not found"})
        return service
    except Exception as e:
        logger.error("Error in GET /v1/marketplace/offer-by-id/%s: %s: %s", offer_id, type(e).__name__, str(e))
        raise


@app.get("/v1/marketplace/ratings/unsynced")
async def get_unsynced_ratings(
    svc: Annotated[MarketplaceService, Depends(get_marketplace_service)],
    # Same accident, same shape: the service declares `limit: int = 100`.
    limit: int = 100,
) -> Any:
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
    from aitbc_shared import MarketplaceOffer

    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "marketplace":
        return JSONResponse(status_code=400, content={"error": "Invalid transaction type for marketplace service"})
    try:
        if action == "offer":
            offer = MarketplaceOffer(**transaction_data)
            session.add(offer)
        else:
            return JSONResponse(
                status_code=400, content={"error": f"Invalid action: {action}. Only 'offer' is currently supported"}
            )
        await session.commit()
        return {"status": "success"}
    except Exception as e:
        await session.rollback()
        logger.error("Transaction submission error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/v1/transactions")
async def get_transactions(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    # Four filters that the body below already treats as optional -- it branches on
    # `not action` and guards `if status:` and `if island_id:` -- but which FastAPI made
    # required, so an unfiltered "list the transactions" answered 422. Listing everything is
    # what no filter means, and now says so.
    action: str | None = None,
    status: str | None = None,
    island_id: str | None = None,
    # Accepted and ignored. Nothing in this handler reads it, and the rows it returns are all
    # `"action": "offer"`, so there is no field for it to select on. Kept rather than removed
    # so a caller already sending it is not met with a changed contract; wiring it up or
    # dropping it is a separate decision, recorded in the release log.
    transaction_type: str | None = None,
) -> Any:
    """Query marketplace transactions"""
    from sqlalchemy import select

    from aitbc_shared import MarketplaceOffer

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
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================================
# v0.7.4 §B4: Governance-triggered parameter change API
# ============================================================================


class ParameterChangeRequest(BaseModel):
    """Request body for applying a governance-approved parameter change."""

    proposal_id: str = Field(..., description="Governance proposal ID that approved this change")
    target_service: str = Field(default="marketplace", description="Service type (must be 'marketplace')")
    parameter_name: str = Field(..., description="Name of the parameter to change")
    old_value: Any = Field(default=None, description="Expected old value (for validation)")
    new_value: Any = Field(..., description="New value to apply")
    description: str = Field(default="", description="Human-readable description of the change")


# Allowed parameters that governance can change on the marketplace service
_MARKETPLACE_GOVERNANCE_PARAMETERS: dict[str, type] = {
    "default_chain_id": str,
    "agent_coordinator_url": str,
    "matching_algorithm": str,
}


@app.post("/v1/marketplace/parameters/apply")
async def apply_marketplace_parameter(
    request: ParameterChangeRequest,
    authenticated: Annotated[dict[str, Any], Depends(require_marketplace_api_key)],
) -> dict[str, Any]:
    """Apply a governance-approved parameter change to the marketplace service (v0.7.4 §B4).

    Validates that the parameter is known and the old_value matches the
    current config, then applies the new value to the running settings.
    """
    if request.target_service != "marketplace":
        return JSONResponse(  # type: ignore[return-value]
            status_code=400, content={"error": f"target_service must be 'marketplace', got '{request.target_service}'"}
        )

    param_type = _MARKETPLACE_GOVERNANCE_PARAMETERS.get(request.parameter_name)
    if param_type is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=400,
            content={
                "error": f"Unknown parameter: {request.parameter_name}",
                "allowed": sorted(_MARKETPLACE_GOVERNANCE_PARAMETERS),
            },
        )

    current_value = getattr(settings, request.parameter_name, None)
    if request.old_value is not None and str(current_value) != str(request.old_value):
        return JSONResponse(  # type: ignore[return-value]
            status_code=409,
            content={
                "error": f"old_value mismatch: expected {request.old_value} but current is {current_value}",
            },
        )

    # Apply the change
    try:
        setattr(settings, request.parameter_name, param_type(request.new_value))
        logger.info(
            "Applied governance parameter change: %s = %s (proposal=%s)",
            request.parameter_name,
            request.new_value,
            request.proposal_id,
        )
        from datetime import UTC, datetime

        return {
            "proposal_id": request.proposal_id,
            "applied": True,
            "parameter_name": request.parameter_name,
            "old_value": current_value,
            "new_value": request.new_value,
            "applied_at": datetime.now(UTC).isoformat(),
            "message": f"Parameter {request.parameter_name} updated successfully",
        }
    except Exception as e:
        logger.error("Failed to apply parameter change: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})  # type: ignore[return-value]


# ============================================================================
# v0.6.6: Edge node advertisement & health endpoints
# ============================================================================


class EdgeAdvertiseRequest(BaseModel):
    """Request body for edge node advertisement (POST /v1/marketplace/edge-advertise)."""

    node_id: str = Field(..., description="Unique edge node identifier")
    endpoint: str = Field(default="", description="Edge service endpoint URL")
    node_type: str = Field(default="edge")
    service: str = Field(default="aitbc-edge")
    gpu_models: list[str] = Field(default_factory=list)
    gpu_count: int = Field(default=0)
    total_vram: int = Field(default=0)
    region: str = Field(default="")
    capabilities: list[str] = Field(default_factory=list)
    gpus: list[dict[str, Any]] = Field(default_factory=list, description="Raw GPU profiles from edge service")


@app.post("/v1/marketplace/edge-advertise")
async def edge_advertise(
    request: EdgeAdvertiseRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, Any]:
    """Register or update an edge node's GPU capabilities in the marketplace (v0.6.6).

    Edge nodes call this endpoint on startup to advertise their available
    GPU resources. If the node_id already exists, the record is updated.
    """
    from datetime import datetime
    from sqlalchemy import select

    from .domain.marketplace import EdgeNodeAdvertisement

    # Extract gpu_models from gpus list if not provided directly
    gpu_models = request.gpu_models
    if not gpu_models and request.gpus:
        gpu_models = [g.get("model", "Unknown") for g in request.gpus]
    gpu_count = request.gpu_count or len(request.gpus)
    total_vram = request.total_vram or sum(g.get("memory_gb", 0) for g in request.gpus)
    capabilities = request.capabilities
    if not capabilities and request.gpus:
        capabilities = list(set(c for g in request.gpus for c in g.get("capabilities", [])))

    stmt = select(EdgeNodeAdvertisement).where(EdgeNodeAdvertisement.node_id == request.node_id)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    existing = result.scalars().first()

    now = datetime.utcnow()
    if existing:
        existing.endpoint = request.endpoint
        existing.gpu_models = gpu_models
        existing.gpu_count = gpu_count
        existing.total_vram = total_vram
        existing.region = request.region
        existing.capabilities = capabilities
        existing.updated_at = now
        await session.commit()
        logger.info("Updated edge node advertisement: %s", request.node_id)
        return {"status": "updated", "node_id": request.node_id, "gpu_count": gpu_count}
    else:
        adv = EdgeNodeAdvertisement(
            node_id=request.node_id,
            endpoint=request.endpoint,
            node_type=request.node_type,
            service=request.service,
            gpu_models=gpu_models,
            gpu_count=gpu_count,
            total_vram=total_vram,
            region=request.region,
            capabilities=capabilities,
            created_at=now,
            updated_at=now,
        )
        session.add(adv)
        await session.commit()
        logger.info("Registered new edge node advertisement: %s", request.node_id)
        return {"status": "registered", "node_id": request.node_id, "gpu_count": gpu_count}


@app.get("/v1/marketplace/edge-advertise")
async def list_edge_nodes(session: Annotated[AsyncSession, Depends(get_session)], region: str | None = None) -> dict[str, Any]:
    """List all registered edge nodes (v0.6.6)."""
    from sqlalchemy import select

    from .domain.marketplace import EdgeNodeAdvertisement

    stmt = select(EdgeNodeAdvertisement).where(EdgeNodeAdvertisement.status == "active")  # type: ignore[arg-type]
    if region:
        stmt = stmt.where(EdgeNodeAdvertisement.region == region)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    nodes = result.scalars().all()
    return {
        "nodes": [
            {
                "node_id": n.node_id,
                "endpoint": n.endpoint,
                "gpu_models": n.gpu_models,
                "gpu_count": n.gpu_count,
                "total_vram": n.total_vram,
                "region": n.region,
                "capabilities": n.capabilities,
                "health_score": n.health_score,
                "status": n.status,
            }
            for n in nodes
        ],
        "total": len(nodes),
    }


@app.get("/v1/marketplace/edge/{node_id}/health")
async def get_edge_health(node_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    """Get health status for a specific edge node (v0.6.6).

    Returns the edge node's health score, last health check time, and
    basic capability info from the marketplace database.
    """
    from sqlalchemy import select

    from .domain.marketplace import EdgeNodeAdvertisement

    stmt = select(EdgeNodeAdvertisement).where(EdgeNodeAdvertisement.node_id == node_id)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    node = result.scalars().first()
    if not node:
        return JSONResponse(status_code=404, content={"error": f"Edge node {node_id} not found"})  # type: ignore[return-value]
    return {
        "node_id": node.node_id,
        "health_score": node.health_score,
        "last_health_check": node.last_health_check,
        "status": node.status,
        "gpu_count": node.gpu_count,
        "endpoint": node.endpoint,
        "region": node.region,
    }


if __name__ == "__main__":
    import os

    import uvicorn

    # Allow configuration via environment variable for multi-node deployments
    # Default to 0.0.0.0 to accept connections from other nodes
    host = os.getenv("MARKETPLACE_BIND_HOST", "0.0.0.0")  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    port = int(os.getenv("MARKETPLACE_BIND_PORT", "8102"))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
