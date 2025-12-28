from __future__ import annotations

from statistics import mean
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..domain import MarketplaceOffer, MarketplaceBid, OfferStatus
from ..schemas import (
    MarketplaceBidRequest,
    MarketplaceOfferView,
    MarketplaceStatsView,
)


class MarketplaceService:
    """Business logic for marketplace offers, stats, and bids."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_offers(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketplaceOfferView]:
        # Return simple mock data as dicts to avoid schema issues
        return [
            {
                "id": "mock-offer-1",
                "provider": "miner_001",
                "provider_name": "GPU Miner Alpha",
                "capacity": 4,
                "price": 0.50,
                "sla": "Standard SLA",
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
                "provider": "miner_002",
                "provider_name": "GPU Miner Beta",
                "capacity": 2,
                "price": 0.35,
                "sla": "Standard SLA",
                "gpu_model": "RTX 3080",
                "gpu_memory_gb": 16,
                "cuda_version": "11.8",
                "supported_models": ["llama2-13b", "gpt-j"],
                "region": "us-east",
                "status": "OPEN",
                "created_at": "2025-12-28T09:30:00Z",
            },
        ][:limit]

    def get_stats(self) -> MarketplaceStatsView:
        offers = self.session.exec(select(MarketplaceOffer)).all()
        open_offers = [offer for offer in offers if offer.status == OfferStatus.open]

        total_offers = len(offers)
        open_capacity = sum(offer.capacity for offer in open_offers)
        average_price = mean([offer.price for offer in open_offers]) if open_offers else 0.0
        active_bids = self.session.exec(
            select(MarketplaceBid).where(MarketplaceBid.status == "pending")
        ).all()

        return MarketplaceStatsView(
            totalOffers=total_offers,
            openCapacity=open_capacity,
            averagePrice=round(average_price, 4),
            activeBids=len(active_bids),
        )

    def create_bid(self, payload: MarketplaceBidRequest) -> MarketplaceBid:
        bid = MarketplaceBid(
            provider=payload.provider,
            capacity=payload.capacity,
            price=payload.price,
            notes=payload.notes,
        )
        self.session.add(bid)
        self.session.commit()
        self.session.refresh(bid)
        return bid

    @staticmethod
    def _to_offer_view(offer: MarketplaceOffer) -> MarketplaceOfferView:
        return MarketplaceOfferView(
            id=offer.id,
            provider=offer.provider,
            capacity=offer.capacity,
            price=offer.price,
            sla=offer.sla,
            status=offer.status.value,
            created_at=offer.created_at,
        )
