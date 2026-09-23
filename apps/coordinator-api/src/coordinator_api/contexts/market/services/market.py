from __future__ import annotations

from decimal import Decimal
from statistics import mean
from typing import Any

from aitbc_shared import MarketOffer
from sqlmodel import Session, select

from ....schemas import (
    MarketOfferView,
    MarketStatsView,
)

# Import plugin manager
try:
    from .plugin_manager import get_plugin_manager
except ImportError:

    def get_plugin_manager() -> Any:  # type: ignore[misc]
        return None


class MarketService:
    """Business logic for market offers, stats, and bids."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_offers(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketOfferView]:
        stmt = select(MarketOffer).order_by(MarketOffer.created_at.desc())  # type: ignore[attr-defined]

        if status is not None:
            normalised = status.strip().lower()
            if normalised not in ("open", "reserved", "closed", "booked"):
                raise ValueError(f"invalid status: {status}")
            stmt = stmt.where(MarketOffer.status == normalised)

        stmt = stmt.offset(offset).limit(limit)
        offers = self.session.execute(stmt).scalars().all()
        return [self._to_offer_view(o) for o in offers]

    def get_stats(self) -> MarketStatsView:
        offers = self.session.execute(select(MarketOffer)).scalars().all()
        open_offers = [offer for offer in offers if offer.status == "open"]

        total_offers = len(offers)
        open_capacity = sum(offer.capacity for offer in open_offers)
        average_price = mean([offer.price for offer in open_offers]) if open_offers else 0.0

        return MarketStatsView(
            totalOffers=total_offers,
            openCapacity=open_capacity,
            averagePrice=round(average_price, 4),
            activeBids=0,  # Bids deprecated in v0.4.7
        )

    # Bids deprecated in v0.4.7 - GPU-only market removed
    # Auction functionality removed - legacy GPU market code

    @staticmethod
    def _to_offer_view(offer: MarketOffer) -> MarketOfferView:
        return MarketOfferView(
            id=offer.id,
            provider=offer.provider,
            capacity=offer.capacity,
            price=offer.price,
            sla=offer.sla,
            status=str(offer.status),
            created_at=offer.created_at,
            gpu_model=offer.gpu_model,
            gpu_memory_gb=offer.gpu_memory_gb,
            disk_quota_mb=offer.disk_quota_mb,
            gpu_count=offer.gpu_count,
            cuda_version=offer.cuda_version,
            price_per_hour=offer.price_per_hour,
            region=offer.region,
            attributes=offer.attributes,
        )

    def update_provider_capacity(self, provider: str, capacity: int) -> MarketOfferView:
        """Publish updated provider capacity after reinvestment or hardware changes.

        Updates the most recent offer for the provider. If no offer exists, the
        caller must create one first; this avoids orphan records.
        """
        stmt = (
            select(MarketOffer).where(MarketOffer.provider == provider).order_by(MarketOffer.created_at.desc())  # type: ignore[attr-defined]
        )
        offer = self.session.execute(stmt.limit(1)).scalars().first()
        if offer is None:
            raise ValueError(f"no market offer for provider {provider}")
        offer.capacity = capacity
        self.session.add(offer)
        self.session.commit()
        self.session.refresh(offer)
        return self._to_offer_view(offer)

    # Plugin hook methods
    def before_booking(self, resource_id: str, user_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute before_booking plugin hooks."""
        plugin_manager = get_plugin_manager()
        if plugin_manager:
            hook_context = {
                "resource_id": resource_id,
                "user_id": user_id,
                "context": context or {},
            }
            return plugin_manager.execute_hook("before_booking", hook_context)
        return context or {}

    def after_booking(self, booking_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute after_booking plugin hooks."""
        plugin_manager = get_plugin_manager()
        if plugin_manager:
            hook_context = {
                "booking_id": booking_id,
                "context": context or {},
            }
            return plugin_manager.execute_hook("after_booking", hook_context)
        return context or {}

    def before_pricing(self, resource_id: str, base_price: Decimal, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute before_pricing plugin hooks."""
        plugin_manager = get_plugin_manager()
        if plugin_manager:
            hook_context = {
                "resource_id": resource_id,
                "base_price": base_price,
                "context": context or {},
            }
            return plugin_manager.execute_hook("before_pricing", hook_context)
        return context or {}

    def after_pricing(self, resource_id: str, final_price: Decimal, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute after_pricing plugin hooks."""
        plugin_manager = get_plugin_manager()
        if plugin_manager:
            hook_context = {
                "resource_id": resource_id,
                "final_price": final_price,
                "context": context or {},
            }
            return plugin_manager.execute_hook("after_pricing", hook_context)
        return context or {}
