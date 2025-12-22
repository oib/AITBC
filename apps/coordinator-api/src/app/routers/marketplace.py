from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from ..models import MarketplaceBidRequest, MarketplaceOfferView, MarketplaceStatsView
from ..services import MarketplaceService
from ..storage import SessionDep

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
    service = _get_service(session)
    try:
        return service.list_offers(status=status_filter, limit=limit, offset=offset)
    except ValueError:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="invalid status filter") from None


@router.get(
    "/marketplace/stats",
    response_model=MarketplaceStatsView,
    summary="Get marketplace summary statistics",
)
async def get_marketplace_stats(*, session: SessionDep) -> MarketplaceStatsView:
    service = _get_service(session)
    return service.get_stats()


@router.post(
    "/marketplace/bids",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Submit a marketplace bid",
)
async def submit_marketplace_bid(
    payload: MarketplaceBidRequest,
    session: SessionDep,
) -> dict[str, str]:
    service = _get_service(session)
    bid = service.create_bid(payload)
    return {"id": bid.id}
