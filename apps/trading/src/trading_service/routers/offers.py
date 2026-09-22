"""Offer sync and discovery endpoints for the Trading Service."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from aitbc.trading.offer_types import OfferDiscoveryRequest

from ..dependencies import get_offer_sync_service
from ..services.offer_sync_service import OfferSyncService
from ..state import _discovery_result_to_dict, _status_entry_to_dict, _synced_offer_to_dict

router = APIRouter(tags=["offers"])


@router.post("/v1/trading/offers/discover")
async def discover_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    request: OfferDiscoveryRequest,
):
    """Discover offers across chains with filters.

    Queries the OfferCache. If cached offers are stale, triggers an
    on-demand sync before returning results.
    """
    result = await svc.discover_offers(request)
    return _discovery_result_to_dict(result)


@router.post("/v1/trading/offers/sync")
async def sync_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    chain_id: Annotated[str | None, Body(embed=True)] = None,
    service_type: Annotated[str | None, Body(embed=True)] = None,
):
    """Trigger offer sync for a specific chain or all chains."""
    if chain_id:
        result = await svc.sync_chain(chain_id)
    else:
        results = await svc.sync_all_chains()
        result = {"results": results, "total_chains": len(results)}
    return result


@router.get("/v1/trading/offers/sync-status")
async def get_offer_sync_status(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
):
    """Get offer sync status per chain."""
    entries = svc.get_sync_status()
    return [_status_entry_to_dict(e) for e in entries]


@router.get("/v1/trading/offers/cache")
async def get_cached_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    chain_id: str | None = None,
    service_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    """Get cached offers with optional filters."""
    offers = svc.get_cached_offers(
        chain_id=chain_id,
        service_type=service_type,
        status=status,
        limit=limit,
    )
    return [_synced_offer_to_dict(o) for o in offers]
