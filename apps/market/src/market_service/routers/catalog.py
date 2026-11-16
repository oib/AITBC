"""Catalog, plugin, IPFS-rental, knowledge-graph, rating, transaction,
governance-parameter, and edge-node routes for the market service.

Extracted verbatim from ``main.py`` — route paths, methods, dependencies,
and handler bodies are unchanged; only the registration target moved from
``app`` to an ``APIRouter`` included by ``main``. Routes keep their
original relative order.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc.network.url_safety import validate_fleet_outbound_url

from ..config import settings
from ..deps import get_market_service, get_session_dep, require_market_api_key
from ..gates import _warn_secret_query_transport
from ..services.market_service import MarketService, coerce_offer_expires_at, max_page_size
from ..storage import get_session

# Keep the historic logger name: caplog filters and log-schema checks key on
# "market_service.main".
logger = get_logger("market_service.main")

router = APIRouter()


@router.get("/v1/market/plugins")
async def get_plugins(
    svc: Annotated[MarketService, Depends(get_market_service)],
    plugin_type: str | None = None,
    status: str = "approved",
) -> Any:
    """Get market plugins.

    Reads the ``plugin`` table written by ``POST /v1/market/plugins`` —
    the previous hardcoded demo list meant registered plugins were never
    listed and the endpoint served fabricated download counts (#1505).
    """
    try:
        logger.info("GET /v1/market/plugins called with type=%s, status=%s", plugin_type, status)
        plugins = await svc.list_plugins(plugin_type=plugin_type, status=status)
        return {"plugins": plugins, "total": len(plugins)}
    except Exception as e:
        logger.error("Error in GET /v1/market/plugins: %s: %s", type(e).__name__, str(e))
        raise


@router.post("/v1/market/plugins", dependencies=[Depends(require_market_api_key)])
async def register_plugin(plugin_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Register a new plugin"""
    try:
        logger.info("POST /v1/market/plugins called with data keys: %s", plugin_data.keys())
        result = await svc.register_plugin(plugin_data)
        logger.info("POST /v1/market/plugins registered plugin with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/market/plugins: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/offer")
async def list_software_offers(
    svc: Annotated[MarketService, Depends(get_market_service)],
    service_type: str | None = None,
    status: str | None = None,
) -> Any:
    """List market offers (hardware+software bundles).

    Without ``status``, on-chain GPU registrations their registrant deactivated
    are left out; pass ``status=deactivated`` to list them.
    """
    try:
        logger.info("GET /v1/market/offer called with filters: service_type=%s, status=%s", service_type, status)
        result = await svc.list_software_services(service_type=service_type, status=status)
        logger.info("GET /v1/market/offer returned %s offers", len(result))
        return {"offers": result, "total": len(result)}
    except Exception as e:
        logger.error("Error in GET /v1/market/offer: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/offer/{plugin_id}")
async def get_software_offer(plugin_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Get a specific market offer"""
    try:
        logger.info("GET /v1/market/offer/%s called", plugin_id)
        result = await svc.get_software_service(plugin_id)
        if not result:
            return JSONResponse(status_code=404, content={"error": "Offer not found"})
        logger.info("GET /v1/market/offer/%s returned offer", plugin_id)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/market/offer/%s: %s: %s", plugin_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/offer", dependencies=[Depends(require_market_api_key)])
async def register_offer(service_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Register or update a market offer"""
    try:
        logger.info("POST /v1/market/offer called with data keys: %s", service_data.keys())
        result = await svc.register_software_service(service_data)
        logger.info("POST /v1/market/offer registered offer: %s", result["plugin_id"])
        return result
    except PermissionError as e:
        # Rejected provider signature — 403, not a server error.
        logger.info("POST /v1/market/offer rejected: %s", e)
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        # Malformed registration (e.g. missing plugin_id) — the caller's.
        logger.info("POST /v1/market/offer rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error in POST /v1/market/offer: %s: %s", type(e).__name__, str(e))
        raise


@router.delete("/v1/market/offer/{plugin_id}", dependencies=[Depends(require_market_api_key)])
async def unregister_offer(
    plugin_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    provider_address: str | None = None,
    chain_id: str | None = None,
    issued_at: int | None = None,
    signature: str | None = None,
) -> Any:
    """Unregister a market offer (provider-signed: the signer must be the offer's provider)"""
    try:
        logger.info("DELETE /v1/market/offer/%s called", plugin_id)
        result = await svc.unregister_software_service(
            plugin_id,
            {"provider_address": provider_address, "chain_id": chain_id, "issued_at": issued_at, "signature": signature},
        )
        logger.info("DELETE /v1/market/offer/%s completed", plugin_id)
        return result
    except PermissionError as e:
        # Missing or rejected provider proof, or a signer who is not the offer's provider.
        logger.info("DELETE /v1/market/offer/%s rejected: %s", plugin_id, e)
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        # The service signals "not found" with ValueError; without this it surfaced as a 500.
        logger.info("DELETE /v1/market/offer/%s not found: %s", plugin_id, e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error in DELETE /v1/market/offer/%s: %s: %s", plugin_id, type(e).__name__, str(e))
        raise


@router.post("/v1/market/ipfs/rental-token", dependencies=[Depends(require_market_api_key)])
async def register_ipfs_rental_token(
    token_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]
) -> Any:
    """Register an access token for a paid IPFS rental."""
    try:
        logger.info("POST /v1/ipfs/rental-token called with data keys: %s", token_data.keys())
        result = await svc.register_ipfs_rental_token(token_data)
        logger.debug("POST /v1/ipfs/rental-token registered token: %s", result.get("access_key"))
        return result
    except ValueError as e:
        logger.info("Rejecting IPFS rental token registration: %s", e)
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in POST /v1/ipfs/rental-token: %s: %s", type(e).__name__, str(e))
        raise


@router.get("/v1/market/ipfs/rental/{access_key}")
async def get_ipfs_rental_token(
    access_key: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    access_secret: str | None = None,
    x_access_secret: Annotated[str | None, Header()] = None,
) -> Any:
    """Validate an IPFS rental token and return its details.

    Same credential transport rule as ``/v1/market/access/{key}``: the secret
    may arrive as the ``access_secret`` query parameter (legacy callers) or
    the ``X-Access-Secret`` header, which keeps it out of URLs and access
    logs (#1448). Header wins when both are sent.
    """
    secret = x_access_secret if x_access_secret is not None else access_secret
    _warn_secret_query_transport(access_key, access_secret, x_access_secret)
    if not secret:
        return JSONResponse(status_code=401, content={"error": "access_secret is required (X-Access-Secret header preferred)"})
    try:
        logger.info("GET /v1/ipfs/rental/%s called", access_key)
        result = await svc.get_ipfs_rental_token(access_key, secret)
        if not result:
            return JSONResponse(status_code=404, content={"error": "Invalid, expired, or unknown IPFS rental token"})
        logger.info("GET /v1/ipfs/rental/%s returned token", access_key)
        return result
    except Exception as e:
        logger.error("Error in GET /v1/ipfs/rental/%s: %s: %s", access_key, type(e).__name__, str(e))
        raise


@router.get("/v1/market/offer/{plugin_id}/health")
async def get_software_offer_health(plugin_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Check the health of a software offer."""
    try:
        logger.info("GET /v1/market/offer/%s/health called", plugin_id)
        return await svc.check_software_offer_health(plugin_id)
    except ValueError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error("Error in GET /v1/market/offer/%s/health: %s: %s", plugin_id, type(e).__name__, str(e))
        raise


@router.post("/v1/knowledge-graph", dependencies=[Depends(require_market_api_key)])
async def create_graph(graph_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Create a new knowledge graph"""
    try:
        logger.info("POST /v1/knowledge-graph called with data keys: %s", graph_data.keys())
        result = await svc.create_graph(graph_data)
        logger.info("POST /v1/knowledge-graph created graph with id: %s", result["id"])
        return result
    except Exception as e:
        logger.error("Error in POST /v1/knowledge-graph: %s: %s", type(e).__name__, str(e))
        raise


@router.post("/v1/knowledge-graph/{graph_id}/nodes", dependencies=[Depends(require_market_api_key)])
async def add_node(
    graph_id: str, node_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]
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


@router.post("/v1/knowledge-graph/{graph_id}/edges", dependencies=[Depends(require_market_api_key)])
async def add_edge(
    graph_id: str, edge_data: dict[str, Any], svc: Annotated[MarketService, Depends(get_market_service)]
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


@router.get("/v1/knowledge-graph/{graph_id}")
async def query_graph(graph_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
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


@router.post("/v1/market/offer/{service_id}/rate", dependencies=[Depends(require_market_api_key)])
async def rate_service(
    service_id: str, rating_data: RatingRequest, svc: Annotated[MarketService, Depends(get_market_service)]
) -> Any:
    """Rate a market service offer"""
    try:
        logger.info("POST /v1/market/offer/%s/rate called with rating=%s", service_id, rating_data.rating)
        # `add_service_rating` never checked that the service exists, and the aggregate it
        # then updates is guarded by `if service:` -- so rating a service that is not there
        # answered 200 and wrote an orphan row that no aggregate would ever count (V23-81).
        # A service id resolves either way round, the same two lookups `get_service_ratings`
        # does below.
        service = await svc.get_software_service(service_id) or await svc.get_service_by_offer_id(service_id)
        if not service:
            return JSONResponse(status_code=404, content={"error": "Service not found"})
        rating = await svc.add_service_rating(
            service_id=service_id,
            rating=rating_data.rating,
            reviewer_id=rating_data.reviewer_id,
            comment=rating_data.comment,
            service=service,
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
        logger.error("Error in POST /v1/market/offer/%s/rate: %s: %s", service_id, type(e).__name__, str(e))
        raise


@router.get("/v1/market/offer/{service_id}/ratings")
async def get_service_ratings(
    service_id: str,
    svc: Annotated[MarketService, Depends(get_market_service)],
    # Paging that could not be omitted: both were required, so "give me the first page" was
    # spelled `?limit=50&offset=0` or it was a 422. The service's own `limit: int = 50,
    # offset: int = 0` say what the first page should be; these now say the same thing.
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Get ratings for a market service offer"""
    try:
        logger.info("GET /v1/market/offer/%s/ratings called", service_id)
        limit = min(max(limit, 1), max_page_size())
        offset = max(offset, 0)
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
        logger.error("Error in GET /v1/market/offer/%s/ratings: %s: %s", service_id, type(e).__name__, str(e))
        raise


@router.get("/v1/market/offer-by-id/{offer_id}")
async def get_offer_by_id(offer_id: str, svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Get a market service offer by offer_id (blockchain offer ID)"""
    try:
        logger.info("GET /v1/market/offer-by-id/%s called", offer_id)
        service = await svc.get_service_by_offer_id(offer_id)
        if not service:
            return JSONResponse(status_code=404, content={"error": "Service not found"})
        return service
    except Exception as e:
        logger.error("Error in GET /v1/market/offer-by-id/%s: %s: %s", offer_id, type(e).__name__, str(e))
        raise


@router.get("/v1/market/ratings/unsynced")
async def get_unsynced_ratings(
    svc: Annotated[MarketService, Depends(get_market_service)],
    # Same accident, same shape: the service declares `limit: int = 100`.
    limit: int = 100,
) -> Any:
    """Get ratings that haven't been synced to remote nodes"""
    try:
        logger.info("GET /v1/market/ratings/unsynced called")
        limit = min(max(limit, 1), max_page_size())
        ratings = await svc.get_unsynced_ratings(limit)
        return {"ratings": ratings, "count": len(ratings)}
    except Exception as e:
        logger.error("Error in GET /v1/market/ratings/unsynced: %s: %s", type(e).__name__, str(e))
        raise


@router.post("/v1/market/ratings/sync", dependencies=[Depends(require_market_api_key)])
async def sync_ratings(ratings: list[dict[str, Any]], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Sync ratings from remote node"""
    try:
        logger.info("POST /v1/market/ratings/sync called with %s ratings", len(ratings))
        result = await svc.sync_ratings_from_remote(ratings)
        return {"status": "success", **result}
    except Exception as e:
        logger.error("Error in POST /v1/market/ratings/sync: %s: %s", type(e).__name__, str(e))
        raise


@router.post("/v1/market/ratings/mark-synced", dependencies=[Depends(require_market_api_key)])
async def mark_ratings_synced(rating_ids: list[str], svc: Annotated[MarketService, Depends(get_market_service)]) -> Any:
    """Mark ratings as synced to remote nodes"""
    try:
        logger.info("POST /v1/market/ratings/mark-synced called with %s IDs", len(rating_ids))
        count = await svc.mark_ratings_synced(rating_ids)
        return {"status": "success", "marked_synced": count}
    except Exception as e:
        logger.error("Error in POST /v1/market/ratings/mark-synced: %s: %s", type(e).__name__, str(e))
        raise


@router.post("/v1/transactions", dependencies=[Depends(require_market_api_key)])
async def submit_transaction(
    transaction_data: dict[str, Any], session: Annotated[AsyncSession, Depends(get_session_dep)]
) -> Any:
    """Submit market transaction"""
    from aitbc_shared import MarketOffer

    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "market":
        return JSONResponse(status_code=400, content={"error": "Invalid transaction type for market service"})
    try:
        if action == "offer":
            # #1554: normalize expires_at to naive UTC before the model sees it.
            if transaction_data.get("expires_at") is not None:
                transaction_data["expires_at"] = coerce_offer_expires_at(transaction_data["expires_at"])
            # #1553: a caller-supplied offer id is the natural idempotency
            # key — a retry replays success instead of dying on the PK.
            offer_id = transaction_data.get("id")
            if offer_id:
                existing = await session.get(MarketOffer, str(offer_id))
                if existing is not None:
                    return {"status": "success", "deduplicated": True, "offer_id": str(offer_id)}
            offer = MarketOffer(**transaction_data)
            session.add(offer)
        else:
            return JSONResponse(
                status_code=400, content={"error": f"Invalid action: {action}. Only 'offer' is currently supported"}
            )
        try:
            await session.commit()
        except IntegrityError:
            # Lost the first-write race on a caller-supplied id — the winner's
            # row is the replay target (#1553).
            await session.rollback()
            offer_id = transaction_data.get("id")
            if offer_id and await session.get(MarketOffer, str(offer_id)) is not None:
                return {"status": "success", "deduplicated": True, "offer_id": str(offer_id)}
            raise
        return {"status": "success"}
    except ValueError as exc:
        # Caller-supplied field failed validation (e.g. malformed expires_at).
        await session.rollback()
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        await session.rollback()
        logger.exception("Transaction submission error")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/v1/transactions")
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
    """Query market transactions"""
    from sqlalchemy import select

    from aitbc_shared import MarketOffer

    try:
        transactions = []
        if action == "offer" or not action:
            result = await session.execute(select(MarketOffer).limit(max_page_size()))
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
    except Exception:
        logger.exception("Transaction query error")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ============================================================================
# v0.7.4 §B4: Governance-triggered parameter change API
# ============================================================================


class ParameterChangeRequest(BaseModel):
    """Request body for applying a governance-approved parameter change."""

    proposal_id: str = Field(..., description="Governance proposal ID that approved this change")
    target_service: str = Field(default="market", description="Service type (must be 'market')")
    parameter_name: str = Field(..., description="Name of the parameter to change")
    old_value: Any = Field(default=None, description="Expected old value (for validation)")
    new_value: Any = Field(..., description="New value to apply")
    description: str = Field(default="", description="Human-readable description of the change")


# Allowed parameters that governance can change on the market service
_MARKET_GOVERNANCE_PARAMETERS: dict[str, type] = {
    "default_chain_id": str,
    "agent_coordinator_url": str,
    "matching_algorithm": str,
}


@router.post("/v1/market/parameters/apply", dependencies=[Depends(require_market_api_key)])
def apply_market_parameter(
    request: ParameterChangeRequest,
    authenticated: Annotated[dict[str, Any], Depends(require_market_api_key)],
) -> dict[str, Any]:
    """Apply a governance-approved parameter change to the market service (v0.7.4 §B4).

    Validates that the parameter is known and the old_value matches the
    current config, then applies the new value to the running settings.
    """
    if request.target_service != "market":
        return JSONResponse(  # type: ignore[return-value]
            status_code=400, content={"error": f"target_service must be 'market', got '{request.target_service}'"}
        )

    param_type = _MARKET_GOVERNANCE_PARAMETERS.get(request.parameter_name)
    if param_type is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=400,
            content={
                "error": f"Unknown parameter: {request.parameter_name}",
                "allowed": sorted(_MARKET_GOVERNANCE_PARAMETERS),
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

    # SSRF-AUDIT-1 (#1523): agent_coordinator_url is POSTed to on every
    # match->task submit — reject loopback/link-local/metadata targets
    # (private fleet LAN allowed). Loopback deployments must allowlist the
    # target via AITBC_OUTBOUND_URL_ALLOWED_TARGETS.
    if request.parameter_name == "agent_coordinator_url":
        try:
            validate_fleet_outbound_url(str(request.new_value))
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": f"invalid agent_coordinator_url: {e}"})  # type: ignore[return-value]

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
    except Exception:
        logger.exception("Failed to apply parameter change")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})  # type: ignore[return-value]


# ============================================================================
# v0.6.6: Edge node advertisement & health endpoints
# ============================================================================


class EdgeAdvertiseRequest(BaseModel):
    """Request body for edge node advertisement (POST /v1/market/edge-advertise)."""

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


@router.post("/v1/market/edge-advertise", dependencies=[Depends(require_market_api_key)])
async def edge_advertise(
    request: EdgeAdvertiseRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, Any]:
    """Register or update an edge node's GPU capabilities in the market (v0.6.6).

    Edge nodes call this endpoint on startup to advertise their available
    GPU resources. If the node_id already exists, the record is updated.
    """
    from datetime import UTC, datetime
    from sqlalchemy import select

    from ..domain.market import EdgeNodeAdvertisement

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

    now = datetime.now(UTC).replace(tzinfo=None)
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


@router.get("/v1/market/edge-advertise")
async def list_edge_nodes(session: Annotated[AsyncSession, Depends(get_session)], region: str | None = None) -> dict[str, Any]:
    """List all registered edge nodes (v0.6.6)."""
    from sqlalchemy import select

    from ..domain.market import EdgeNodeAdvertisement

    stmt = select(EdgeNodeAdvertisement).where(EdgeNodeAdvertisement.status == "active")  # type: ignore[arg-type]
    if region:
        stmt = stmt.where(EdgeNodeAdvertisement.region == region)  # type: ignore[arg-type]
    # Same ceiling as every other public list path — this route was the one
    # unbounded read left (#1507).
    stmt = stmt.limit(max_page_size())
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


@router.get("/v1/market/edge/{node_id}/health")
async def get_edge_health(node_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    """Get health status for a specific edge node (v0.6.6).

    Returns the edge node's health score, last health check time, and
    basic capability info from the market database.
    """
    from sqlalchemy import select

    from ..domain.market import EdgeNodeAdvertisement

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
