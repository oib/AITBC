from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from ....schemas import (
    MarketplaceBidRequest,
    MarketplaceBidView,
    MarketplaceOfferView,
    MarketplaceStatsView,
)
from ..domain.marketplace import AuctionConfig, MarketplaceOffer

# Import plugin manager
try:
    from .plugin_manager import get_plugin_manager
except ImportError:
    def get_plugin_manager():
        return None


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
        stmt = select(MarketplaceOffer).order_by(MarketplaceOffer.created_at.desc())  # type: ignore[attr-defined]

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

        return MarketplaceStatsView(
            totalOffers=total_offers,
            openCapacity=open_capacity,
            averagePrice=round(average_price, 4),
            activeBids=0,  # Bids deprecated in v0.4.7
        )

    # Bids deprecated in v0.4.7 - GPU-only marketplace removed

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

    # Auction methods
    def create_auction(
        self,
        resource_id: str,
        auction_type: str,
        reserve_price: float = 0.0,
        start_price: float | None = None,
        decrement_rate: float | None = None,
        decrement_interval: int | None = None,
        duration_hours: int = 24,
    ) -> AuctionConfig:
        """Create a new auction for a resource."""
        auction_id = str(uuid4())
        end_time = datetime.now(UTC) + timedelta(hours=duration_hours)
        
        auction = AuctionConfig(
            id=str(uuid4()),
            auction_id=auction_id,
            auction_type=auction_type,
            resource_id=resource_id,
            start_time=datetime.now(UTC),
            end_time=end_time,
            reserve_price=reserve_price,
            start_price=start_price,
            decrement_rate=decrement_rate,
            decrement_interval=decrement_interval,
            status="active",
        )
        
        self.session.add(auction)
        self.session.commit()
        self.session.refresh(auction)
        return auction

    def submit_auction_bid(
        self,
        auction_id: str,
        provider: str,
        price: float,
        capacity: int = 1,
        notes: str | None = None,
        sealed_bid: str | None = None,
    ) -> MarketplaceBid:
        """Submit a bid for an auction."""
        auction = self.session.execute(
            select(AuctionConfig).where(AuctionConfig.auction_id == auction_id)
        ).first()
        
        if not auction:
            raise ValueError(f"Auction {auction_id} not found")
        
        if auction.status != "active":
            raise ValueError(f"Auction {auction_id} is not active")
        
        bid = MarketplaceBid(
            provider=provider,
            capacity=capacity,
            price=price,
            notes=notes,
            auction_type=auction.auction_type,
            auction_id=auction_id,
            sealed_bid_encrypted=sealed_bid,
        )
        
        self.session.add(bid)
        self.session.commit()
        self.session.refresh(bid)
        return bid

    def reveal_sealed_bids(self, auction_id: str) -> list[MarketplaceBid]:
        """Reveal and evaluate sealed bids for an auction."""
        auction = self.session.execute(
            select(AuctionConfig).where(AuctionConfig.auction_id == auction_id)
        ).first()
        
        if not auction:
            raise ValueError(f"Auction {auction_id} not found")
        
        if auction.auction_type != "sealed":
            raise ValueError(f"Auction {auction_id} is not a sealed auction")
        
        # Get all sealed bids for this auction
        bids = self.session.execute(
            select(MarketplaceBid).where(
                MarketplaceBid.auction_id == auction_id,
                MarketplaceBid.auction_type == "sealed"
            )
        ).scalars().all()
        
        # Mark bids as revealed
        for bid in bids:
            bid.reveal_timestamp = datetime.now(UTC)
        
        self.session.commit()
        return list(bids)

    def update_dutch_price(self, auction_id: str) -> float:
        """Update Dutch auction price based on decrement rate."""
        auction = self.session.execute(
            select(AuctionConfig).where(AuctionConfig.auction_id == auction_id)
        ).first()
        
        if not auction:
            raise ValueError(f"Auction {auction_id} not found")
        
        if auction.auction_type != "dutch":
            raise ValueError(f"Auction {auction_id} is not a Dutch auction")
        
        if not auction.start_price or not auction.decrement_rate or not auction.decrement_interval:
            raise ValueError(f"Auction {auction_id} missing Dutch auction parameters")
        
        # Calculate elapsed time
        elapsed = (datetime.now(UTC) - auction.start_time).total_seconds()
        decrements = int(elapsed / auction.decrement_interval)
        
        # Calculate current price
        current_price = max(
            auction.reserve_price,
            auction.start_price - (decrements * auction.decrement_rate)
        )
        
        # Update all bids for this auction with current Dutch price
        bids = self.session.execute(
            select(MarketplaceBid).where(MarketplaceBid.auction_id == auction_id)
        ).scalars().all()
        
        for bid in bids:
            bid.dutch_price = current_price
        
        self.session.commit()
        return current_price

    def evaluate_reverse_auction(self, auction_id: str) -> MarketplaceBid | None:
        """Evaluate reverse auction and select lowest bid winner."""
        auction = self.session.execute(
            select(AuctionConfig).where(AuctionConfig.auction_id == auction_id)
        ).first()
        
        if not auction:
            raise ValueError(f"Auction {auction_id} not found")
        
        if auction.auction_type != "reverse":
            raise ValueError(f"Auction {auction_id} is not a reverse auction")
        
        # Get all bids for this auction
        bids = self.session.execute(
            select(MarketplaceBid).where(
                MarketplaceBid.auction_id == auction_id,
                MarketplaceBid.auction_type == "reverse"
            )
        ).scalars().all()
        
        if not bids:
            return None
        
        # Select lowest bid as winner
        winning_bid = min(bids, key=lambda b: b.price)
        
        # Update auction with winner
        auction.winner_id = winning_bid.provider
        auction.winning_price = winning_bid.price
        auction.status = "completed"
        auction.updated_at = datetime.now(UTC)
        
        # Update winning bid status
        winning_bid.status = "accepted"
        
        # Reject other bids
        for bid in bids:
            if bid.id != winning_bid.id:
                bid.status = "rejected"
        
        self.session.commit()
        self.session.refresh(winning_bid)
        return winning_bid

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

    def before_pricing(self, resource_id: str, base_price: float, context: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def after_pricing(self, resource_id: str, final_price: float, context: dict[str, Any] | None = None) -> dict[str, Any]:
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


