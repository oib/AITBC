from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi import status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ....config import settings
from ....metrics import market_errors_total, market_requests_total
from ....schemas import MarketOfferView, MarketStatsView
from ....storage import get_session
from ....utils.cache import cached, get_cache_config
from ..services import MarketService

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["market"])


def _get_service(session: Annotated[Session, Depends(get_session)]) -> MarketService:
    return MarketService(session)  # type: ignore[arg-type]


@router.get("/market/offers", response_model=list[MarketOfferView], summary="List market offers")
@limiter.limit("100/minute")
async def list_market_offers(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    status_filter: str | None = Query(default=None, alias="status", description="Filter by offer status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MarketOfferView]:
    market_requests_total.labels(endpoint="/market/offers", method="GET").inc()
    service = _get_service(session)
    try:
        return service.list_offers(status=status_filter, limit=limit, offset=offset)
    except ValueError:
        market_errors_total.labels(endpoint="/market/offers", method="GET", error_type="invalid_request").inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="invalid status filter") from None
    except Exception:
        market_errors_total.labels(endpoint="/market/offers", method="GET", error_type="internal").inc()
        raise


@router.get("/market/stats", response_model=MarketStatsView, summary="Get market summary statistics")
@limiter.limit(lambda: settings.rate_limit_market_stats)
@cached(**get_cache_config("market_stats"))
async def get_market_stats(request: Request, *, session: Annotated[Session, Depends(get_session)]) -> MarketStatsView:
    market_requests_total.labels(endpoint="/market/stats", method="GET").inc()
    service = _get_service(session)
    try:
        return service.get_stats()
    except Exception:
        market_errors_total.labels(endpoint="/market/stats", method="GET", error_type="internal").inc()
        raise


@router.get("/market/plugins", summary="List market plugins")
async def list_market_plugins(
    request: Request,
    *,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List available market plugins"""
    market_requests_total.labels(endpoint="/market/plugins", method="GET").inc()
    try:
        plugins = [
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
        ]
        return {"plugins": plugins[offset : offset + limit], "total": len(plugins), "offset": offset, "limit": limit}
    except Exception as e:
        market_errors_total.labels(endpoint="/market/plugins", method="GET", error_type="internal").inc()
        logger.error("Error listing plugins: %s", e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list plugins") from e


class _CapacityUpdate(BaseModel):
    capacity: int


@router.post(
    "/market/providers/{provider_id}/capacity",
    response_model=MarketOfferView,
    summary="Publish updated provider capacity",
)
@limiter.limit("100/minute")
async def update_provider_capacity(
    request: Request,
    provider_id: str,
    body: _CapacityUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> MarketOfferView:
    """Publish updated provider capacity after reinvestment."""
    market_requests_total.labels(endpoint="/market/providers/{provider_id}/capacity", method="POST").inc()
    service = _get_service(session)
    try:
        return service.update_provider_capacity(provider_id, body.capacity)
    except ValueError as e:
        market_errors_total.labels(
            endpoint="/market/providers/{provider_id}/capacity",
            method="POST",
            error_type="invalid_request",
        ).inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception:
        market_errors_total.labels(
            endpoint="/market/providers/{provider_id}/capacity",
            method="POST",
            error_type="internal",
        ).inc()
        raise
