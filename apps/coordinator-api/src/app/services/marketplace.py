from __future__ import annotations

from statistics import mean

from sqlmodel import Session, select

from ..domain import MarketplaceBid, MarketplaceOffer
from ..schemas import (
    MarketplaceBidRequest,
    MarketplaceBidView,
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
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketplaceOfferView]:
        stmt = select(MarketplaceOffer).order_by(MarketplaceOffer.created_at.desc())

        if status is not None:
            normalised = status.strip().lower()
            if normalised not in ("open", "reserved", "closed", "booked"):
                raise ValueError(f"invalid status: {status}")
            stmt = stmt.where(MarketplaceOffer.status == normalised)

        stmt = stmt.offset(offset).limit(limit)
        offers = self.session.execute(stmt).scalars().all()
        return [self._to_offer_view(o) for o in offers]

    def get_stats(self) -> MarketplaceStatsView:
        offers = self.session.execute(select(MarketplaceOffer)).scalars().all()
        open_offers = [offer for offer in offers if offer.status == "open"]

        total_offers = len(offers)
        open_capacity = sum(offer.capacity for offer in open_offers)
        average_price = mean([offer.price for offer in open_offers]) if open_offers else 0.0
        active_bids = self.session.execute(select(MarketplaceBid).where(MarketplaceBid.status == "pending")).all()

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

    def list_bids(
        self,
        *,
        status: str | None = None,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketplaceBidView]:
        stmt = select(MarketplaceBid).order_by(MarketplaceBid.submitted_at.desc())

        if status is not None:
            normalised = status.strip().lower()
            if normalised not in ("pending", "accepted", "rejected"):
                raise ValueError(f"invalid status: {status}")
            stmt = stmt.where(MarketplaceBid.status == normalised)

        if provider is not None:
            stmt = stmt.where(MarketplaceBid.provider == provider)

        stmt = stmt.offset(offset).limit(limit)
        bids = self.session.execute(stmt).all()
        return [self._to_bid_view(bid) for bid in bids]

    def get_bid(self, bid_id: str) -> MarketplaceBidView | None:
        bid = self.session.get(MarketplaceBid, bid_id)
        if bid:
            return self._to_bid_view(bid)
        return None

    @staticmethod
    def _to_bid_view(bid: MarketplaceBid) -> MarketplaceBidView:
        return MarketplaceBidView(
            id=bid.id,
            provider=bid.provider,
            capacity=bid.capacity,
            price=bid.price,
            status=str(bid.status),
            submitted_at=bid.submitted_at,
            notes=bid.notes,
        )

    @staticmethod
    def _to_offer_view(offer: MarketplaceOffer) -> MarketplaceOfferView:
        return MarketplaceOfferView(
            id=offer.id,
            provider=offer.provider,
            capacity=offer.capacity,
            price=offer.price,
            sla=offer.sla,
            status=str(offer.status),
            created_at=offer.created_at,
            gpu_model=offer.gpu_model,
            gpu_memory_gb=offer.gpu_memory_gb,
            gpu_count=offer.gpu_count,
            cuda_version=offer.cuda_version,
            price_per_hour=offer.price_per_hour,
            region=offer.region,
            attributes=offer.attributes,
        )
