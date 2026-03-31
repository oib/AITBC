from typing import Annotated

from sqlalchemy.orm import Session

"""
Router to create marketplace offers from registered miners
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import require_admin_key
from ..domain import MarketplaceOffer, Miner
from ..schemas import MarketplaceOfferView
from ..storage import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketplace-offers"])


@router.post("/marketplace/sync-offers", summary="Create offers from registered miners")
async def sync_offers(
    session: Annotated[Session, Depends(get_session)],
    admin_key: str = Depends(require_admin_key()),
) -> dict[str, Any]:
    """Create marketplace offers from all registered miners"""

    # Get all registered miners
    miners = session.execute(select(Miner).where(Miner.status == "ONLINE")).scalars().all()

    created_offers = []
    offer_objects = []

    for miner in miners:
        # Check if offer already exists
        existing = session.execute(select(MarketplaceOffer).where(MarketplaceOffer.provider == miner.id)).first()

        if not existing:
            # Create offer from miner capabilities
            capabilities = miner.capabilities or {}

            offer = MarketplaceOffer(
                provider=miner.id,
                capacity=miner.concurrency or 1,
                price=capabilities.get("pricing_per_hour", 0.50),
                gpu_model=capabilities.get("gpu", None),
                gpu_memory_gb=capabilities.get("gpu_memory_gb", None),
                gpu_count=capabilities.get("gpu_count", 1),
                cuda_version=capabilities.get("cuda_version", None),
                price_per_hour=capabilities.get("pricing_per_hour", 0.50),
                region=miner.region or None,
                attributes={
                    "supported_models": capabilities.get("supported_models", []),
                },
            )

            session.add(offer)
            offer_objects.append(offer)

    session.commit()

    # Collect offer IDs after commit (when IDs are generated)
    for offer in offer_objects:
        created_offers.append(offer.id)

    return {"status": "ok", "created_offers": len(created_offers), "offer_ids": created_offers}


@router.get("/marketplace/miner-offers", summary="List all miner offers", response_model=list[MarketplaceOfferView])
async def list_miner_offers(session: Annotated[Session, Depends(get_session)]) -> list[MarketplaceOfferView]:
    """List all offers created from miners"""

    # Get all offers with miner details
    offers = session.execute(select(MarketplaceOffer).where(MarketplaceOffer.provider.like("miner_%"))).all()

    result = []
    for offer in offers:
        # Get miner details
        miner = session.get(Miner, offer.provider)

        # Extract attributes
        attrs = offer.attributes or {}

        offer_view = MarketplaceOfferView(
            id=offer.id,
            provider_id=offer.provider,
            provider_name=f"Miner {offer.provider}" if miner else "Unknown Miner",
            capacity=offer.capacity,
            price=offer.price,
            gpu_model=attrs.get("gpu_model", "Unknown"),
            gpu_memory_gb=attrs.get("gpu_memory_gb", 0),
            cuda_version=attrs.get("cuda_version", "Unknown"),
            supported_models=attrs.get("supported_models", []),
            region=attrs.get("region", "unknown"),
            status=offer.status.value,
            created_at=offer.created_at,
        )
        result.append(offer_view)

    return result


@router.get("/offers", summary="List all marketplace offers (Fixed)")
async def list_all_offers(session: Annotated[Session, Depends(get_session)]) -> list[dict[str, Any]]:
    """List all marketplace offers - Fixed version to avoid AttributeError"""
    try:
        # Use direct database query instead of GlobalMarketplaceService
        from sqlmodel import select

        offers = session.execute(select(MarketplaceOffer)).scalars().all()

        result = []
        for offer in offers:
            # Extract attributes safely
            attrs = offer.attributes or {}

            offer_data = {
                "id": offer.id,
                "provider": offer.provider,
                "capacity": offer.capacity,
                "price": offer.price,
                "status": offer.status,
                "created_at": offer.created_at.isoformat(),
                "gpu_model": attrs.get("gpu_model", "Unknown"),
                "gpu_memory_gb": attrs.get("gpu_memory_gb", 0),
                "cuda_version": attrs.get("cuda_version", "Unknown"),
                "supported_models": attrs.get("supported_models", []),
                "region": attrs.get("region", "unknown"),
            }
            result.append(offer_data)

        return result

    except Exception as e:
        logger.error(f"Error listing offers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
