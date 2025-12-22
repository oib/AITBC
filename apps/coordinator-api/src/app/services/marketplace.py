from __future__ import annotations

from statistics import mean
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..domain import MarketplaceOffer, MarketplaceBid, OfferStatus
from ..models import (
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
        statement = select(MarketplaceOffer).order_by(MarketplaceOffer.created_at.desc())
        if status:
            try:
                desired_status = OfferStatus(status.lower())
            except ValueError as exc:  # pragma: no cover - validated in router
                raise ValueError("invalid status filter") from exc
            statement = statement.where(MarketplaceOffer.status == desired_status)
        if offset:
            statement = statement.offset(offset)
        if limit:
            statement = statement.limit(limit)
        offers = self.session.exec(statement).all()
        return [self._to_offer_view(offer) for offer in offers]

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
