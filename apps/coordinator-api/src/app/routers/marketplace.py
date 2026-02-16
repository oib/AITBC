from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from ..schemas import MarketplaceBidRequest, MarketplaceOfferView, MarketplaceStatsView, MarketplaceBidView
from ..services import MarketplaceService
from ..storage import SessionDep
from ..metrics import marketplace_requests_total, marketplace_errors_total

router = APIRouter(tags=["marketplace"])


def _get_service(session: SessionDep) -> MarketplaceService:
    return MarketplaceService(session)


@router.get(
    "/marketplace/offers",
    response_model=list[MarketplaceOfferView],
    summary="List marketplace offers",
)
async def list_marketplace_offers(
    *,
    session: SessionDep,
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
async def get_marketplace_stats(*, session: SessionDep) -> MarketplaceStatsView:
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
async def submit_marketplace_bid(
    payload: MarketplaceBidRequest,
    session: SessionDep,
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
    session: SessionDep,
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
    session: SessionDep,
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
