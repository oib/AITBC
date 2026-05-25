from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from aitbc import get_logger
from ....config import settings
from ....metrics import marketplace_errors_total, marketplace_requests_total
from ....schemas import MarketplaceBidRequest, MarketplaceBidView, MarketplaceOfferView, MarketplaceStatsView
from ..services import MarketplaceService
from ....storage import get_session
from ....utils.cache import cached, get_cache_config

logger = get_logger(__name__)


limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["marketplace"])


def _get_service(session: Session = Depends(get_session)) -> MarketplaceService:
    return MarketplaceService(session)  # type: ignore[arg-type]


@router.get(
    "/marketplace/offers",
    response_model=list[MarketplaceOfferView],
    summary="List marketplace offers",
)
@limiter.limit("100/minute")
async def list_marketplace_offers(
    request: Request,
    *,
    session: Session = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by offer status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MarketplaceOfferView]:
    marketplace_requests_total.labels(endpoint="/marketplace/offers", method="GET").inc()
    service = _get_service(session)
    try:
        return service.list_offers(status=status_filter, limit=limit, offset=offset)
    except ValueError:
        marketplace_errors_total.labels(endpoint="/marketplace/offers", method="GET", error_type="invalid_request").inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="invalid status filter") from None
    except Exception:
        marketplace_errors_total.labels(endpoint="/marketplace/offers", method="GET", error_type="internal").inc()
        raise


@router.get(
    "/marketplace/stats",
    response_model=MarketplaceStatsView,
    summary="Get marketplace summary statistics",
)
@limiter.limit(lambda: settings.rate_limit_marketplace_stats)
@cached(**get_cache_config("marketplace_stats"))
async def get_marketplace_stats(request: Request, *, session: Session = Depends(get_session)) -> MarketplaceStatsView:
    marketplace_requests_total.labels(endpoint="/marketplace/stats", method="GET").inc()
    service = _get_service(session)
    try:
        return service.get_stats()
    except Exception:
        marketplace_errors_total.labels(endpoint="/marketplace/stats", method="GET", error_type="internal").inc()
        raise


@router.post(
    "/marketplace/bids",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Submit a marketplace bid",
)
@limiter.limit("30/minute")
async def submit_marketplace_bid(
    request: Request,
    payload: MarketplaceBidRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    marketplace_requests_total.labels(endpoint="/marketplace/bids", method="POST").inc()
    service = _get_service(session)
    try:
        bid = service.create_bid(payload)
        return {"id": bid.id}
    except ValueError:
        marketplace_errors_total.labels(endpoint="/marketplace/bids", method="POST", error_type="invalid_request").inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="invalid bid data") from None
    except Exception:
        marketplace_errors_total.labels(endpoint="/marketplace/bids", method="POST", error_type="internal").inc()
        raise


@router.get(
    "/marketplace/bids",
    response_model=list[MarketplaceBidView],
    summary="List marketplace bids",
)
async def list_marketplace_bids(
    *,
    session: Session = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by bid status"),
    provider_filter: str | None = Query(default=None, alias="provider", description="Filter by provider ID"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MarketplaceBidView]:
    marketplace_requests_total.labels(endpoint="/marketplace/bids", method="GET").inc()
    service = _get_service(session)
    try:
        return service.list_bids(status=status_filter, provider=provider_filter, limit=limit, offset=offset)
    except ValueError:
        marketplace_errors_total.labels(endpoint="/marketplace/bids", method="GET", error_type="invalid_request").inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="invalid filter") from None
    except Exception:
        marketplace_errors_total.labels(endpoint="/marketplace/bids", method="GET", error_type="internal").inc()
        raise


@router.get(
    "/marketplace/bids/{bid_id}",
    response_model=MarketplaceBidView,
    summary="Get bid details",
)
async def get_marketplace_bid(
    bid_id: str,
    session: Session = Depends(get_session),
) -> MarketplaceBidView:
    marketplace_requests_total.labels(endpoint="/marketplace/bids/{bid_id}", method="GET").inc()
    service = _get_service(session)
    try:
        bid = service.get_bid(bid_id)
        if not bid:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="bid not found")
        return bid
    except HTTPException:
        raise
    except Exception:
        marketplace_errors_total.labels(endpoint="/marketplace/bids/{bid_id}", method="GET", error_type="internal").inc()
        raise


@router.get(
    "/marketplace/plugins",
    summary="List marketplace plugins",
)
async def list_marketplace_plugins(
    request: Request,
    *,
    session: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List available marketplace plugins"""
    marketplace_requests_total.labels(endpoint="/marketplace/plugins", method="GET").inc()
    try:
        # Return a list of available plugins (mock data for now)
        plugins = [
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
        ]
        return {
            "plugins": plugins[offset:offset+limit],
            "total": len(plugins),
            "offset": offset,
            "limit": limit
        }
    except Exception as e:
        marketplace_errors_total.labels(endpoint="/marketplace/plugins", method="GET", error_type="internal").inc()
        logger.error(f"Error listing plugins: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list plugins")
