"""
Router to create marketplace offers from registered miners
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import require_admin_key
from ..domain import MarketplaceOffer, Miner, OfferStatus
from ..schemas import MarketplaceOfferView
from ..storage import SessionDep

router = APIRouter(tags=["marketplace-offers"])


@router.post("/marketplace/sync-offers", summary="Create offers from registered miners")
async def sync_offers(
    session: SessionDep,
    admin_key: str = Depends(require_admin_key()),
) -> dict[str, Any]:
    """Create marketplace offers from all registered miners"""
    
    # Get all registered miners
    miners = session.exec(select(Miner).where(Miner.status == "ONLINE")).all()
    
    created_offers = []
    
    for miner in miners:
        # Check if offer already exists
        existing = session.exec(
            select(MarketplaceOffer).where(MarketplaceOffer.provider == miner.id)
        ).first()
        
        if not existing:
            # Create offer from miner capabilities
            capabilities = miner.capabilities or {}
            
            offer = MarketplaceOffer(
                provider=miner.id,
                capacity=miner.concurrency or 1,
                price=capabilities.get("pricing_per_hour", 0.50),
                attributes={
                    "gpu_model": capabilities.get("gpu", "Unknown GPU"),
                    "gpu_memory_gb": capabilities.get("gpu_memory_gb", 0),
                    "cuda_version": capabilities.get("cuda_version", "Unknown"),
                    "supported_models": capabilities.get("supported_models", []),
                    "region": miner.region or "unknown"
                }
            )
            
            session.add(offer)
            created_offers.append(offer.id)
    
    session.commit()
    
    return {
        "status": "ok",
        "created_offers": len(created_offers),
        "offer_ids": created_offers
    }


@router.get("/marketplace/offers", summary="List all marketplace offers")
async def list_offers() -> list[dict]:
    """List all marketplace offers"""
    
    # Return simple mock data
    return [
        {
            "id": "mock-offer-1",
            "provider_id": "miner_001",
            "provider_name": "GPU Miner Alpha",
            "capacity": 4,
            "price": 0.50,
            "gpu_model": "RTX 4090",
            "gpu_memory_gb": 24,
            "cuda_version": "12.0",
            "supported_models": ["llama2-7b", "stable-diffusion-xl"],
            "region": "us-west",
            "status": "OPEN",
            "created_at": "2025-12-28T10:00:00Z",
        },
        {
            "id": "mock-offer-2",
            "provider_id": "miner_002",
            "provider_name": "GPU Miner Beta",
            "capacity": 2,
            "price": 0.35,
            "gpu_model": "RTX 3080",
            "gpu_memory_gb": 16,
            "cuda_version": "11.8",
            "supported_models": ["llama2-13b", "gpt-j"],
            "region": "us-east",
            "status": "OPEN",
            "created_at": "2025-12-28T09:30:00Z",
        },
    ]


@router.get("/marketplace/miner-offers", summary="List all miner offers", response_model=list[MarketplaceOfferView])
async def list_miner_offers(session: SessionDep) -> list[MarketplaceOfferView]:
    """List all offers created from miners"""
    
    # Get all offers with miner details
    offers = session.exec(select(MarketplaceOffer).where(MarketplaceOffer.provider.like("miner_%"))).all()
    
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
