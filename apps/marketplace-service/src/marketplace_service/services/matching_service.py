"""
Marketplace matching service for matching GPU providers with consumers
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc import get_logger

from ..domain.marketplace import MarketplaceBid, MarketplaceOffer

logger = get_logger(__name__)


class MatchingService:
    """Service for matching GPU offers with consumer bids"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_best_match(
        self,
        bid_requirements: dict,
        max_price: float | None = None,
        preferred_region: str | None = None,
        min_gpu_memory: int | None = None,
        required_gpu_model: str | None = None
    ) -> dict | None:
        """
        Find the best matching offer for a bid based on requirements
        
        Args:
            bid_requirements: Bid requirements (capacity, duration, etc.)
            max_price: Maximum price per hour willing to pay
            preferred_region: Preferred region for GPU location
            min_gpu_memory: Minimum GPU memory in GB
            required_gpu_model: Specific GPU model required
        
        Returns:
            Best matching offer as dict, or None if no match found
        """
        try:
            logger.info(f"Finding best match for bid requirements: {bid_requirements.keys()}")

            # Build query for available offers
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.status == "active")

            # Apply filters
            if max_price:
                stmt = stmt.where(MarketplaceOffer.price_per_hour <= max_price)

            if preferred_region:
                stmt = stmt.where(MarketplaceOffer.region == preferred_region)

            if min_gpu_memory:
                stmt = stmt.where(MarketplaceOffer.gpu_memory_gb >= min_gpu_memory)

            if required_gpu_model:
                stmt = stmt.where(MarketplaceOffer.gpu_model == required_gpu_model)

            # Order by price (lowest first) and capacity (highest first)
            stmt = stmt.order_by(
                MarketplaceOffer.price_per_hour.asc(),
                MarketplaceOffer.capacity.desc()
            )

            result = await self.session.execute(stmt)
            offers = result.scalars().all()

            if not offers:
                logger.info("No matching offers found")
                return None

            # Return best match (first result due to ordering)
            best_offer = offers[0]
            logger.info(f"Found best match: offer_id={best_offer.id}, price={best_offer.price_per_hour}")

            return {
                'id': best_offer.id,
                'provider': best_offer.provider,
                'capacity': best_offer.capacity,
                'price': best_offer.price,
                'price_per_hour': best_offer.price_per_hour,
                'gpu_model': best_offer.gpu_model,
                'gpu_memory_gb': best_offer.gpu_memory_gb,
                'gpu_count': best_offer.gpu_count,
                'region': best_offer.region,
                'match_score': self._calculate_match_score(best_offer, bid_requirements),
            }

        except Exception as e:
            logger.error(f"Error in find_best_match: {type(e).__name__}: {str(e)}")
            raise

    def _calculate_match_score(self, offer: MarketplaceOffer, requirements: dict) -> float:
        """
        Calculate a match score for an offer based on requirements
        
        Args:
            offer: Marketplace offer
            requirements: Bid requirements
        
        Returns:
            Match score between 0.0 and 1.0
        """
        score = 1.0

        # Penalize higher prices
        if requirements.get('max_price'):
            price_ratio = offer.price_per_hour / requirements['max_price']
            score *= (1.0 - price_ratio * 0.3)  # Price contributes 30% to score

        # Bonus for higher capacity
        if requirements.get('capacity'):
            capacity_ratio = min(offer.capacity / requirements['capacity'], 2.0)
            score *= (0.7 + capacity_ratio * 0.15)  # Capacity contributes 15%

        # Bonus for region match
        if requirements.get('preferred_region') and offer.region == requirements['preferred_region']:
            score *= 1.1  # 10% bonus for region match

        return min(max(score, 0.0), 1.0)

    async def create_match(
        self,
        bid_id: str,
        offer_id: str,
        match_data: dict
    ) -> dict:
        """
        Create a match between a bid and an offer
        
        Args:
            bid_id: ID of the bid
            offer_id: ID of the offer
            match_data: Additional match data
        
        Returns:
            Match record as dict
        """
        try:
            logger.info(f"Creating match: bid_id={bid_id}, offer_id={offer_id}")

            # Get bid and offer
            bid_stmt = select(MarketplaceBid).where(MarketplaceBid.id == bid_id)
            bid_result = await self.session.execute(bid_stmt)
            bid = bid_result.scalar_one_or_none()

            if not bid:
                raise ValueError(f"Bid not found: {bid_id}")

            offer_stmt = select(MarketplaceOffer).where(MarketplaceOffer.id == offer_id)
            offer_result = await self.session.execute(offer_stmt)
            offer = offer_result.scalar_one_or_none()

            if not offer:
                raise ValueError(f"Offer not found: {offer_id}")

            # Update bid status to matched
            bid.status = "matched"
            bid.notes = f"Matched with offer {offer_id}"

            # Update offer status if capacity is fully utilized
            if offer.capacity <= bid.capacity:
                offer.status = "booked"
            else:
                offer.capacity -= bid.capacity

            await self.session.commit()

            match_record = {
                'match_id': f"match_{bid_id[:8]}_{offer_id[:8]}",
                'bid_id': bid_id,
                'offer_id': offer_id,
                'provider': offer.provider,
                'consumer': bid.provider,
                'price_per_hour': offer.price_per_hour,
                'capacity': bid.capacity,
                'status': 'active',
                'created_at': datetime.now(UTC).isoformat(),
                'match_score': match_data.get('match_score', 0.0),
            }

            logger.info(f"Created match: {match_record['match_id']}")
            return match_record

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error in create_match: {type(e).__name__}: {str(e)}")
            raise

    async def list_matches(
        self,
        status: str | None = None,
        provider: str | None = None
    ) -> list[dict]:
        """
        List all matches (derived from matched bids)
        
        Args:
            status: Filter by match status
            provider: Filter by provider
        
        Returns:
            List of match records
        """
        try:
            logger.info(f"Listing matches with filters: status={status}, provider={provider}")

            # Query matched bids
            stmt = select(MarketplaceBid).where(MarketplaceBid.status == "matched")

            if provider:
                stmt = stmt.where(MarketplaceBid.provider == provider)

            result = await self.session.execute(stmt)
            bids = result.scalars().all()

            matches = []
            for bid in bids:
                # Extract offer_id from notes
                offer_id = None
                if bid.notes and "Matched with offer" in bid.notes:
                    offer_id = bid.notes.split()[-1]

                matches.append({
                    'bid_id': bid.id,
                    'offer_id': offer_id,
                    'provider': bid.provider,
                    'capacity': bid.capacity,
                    'price': bid.price,
                    'status': bid.status,
                    'created_at': bid.submitted_at.isoformat() if bid.submitted_at else None,
                })

            logger.info(f"Found {len(matches)} matches")
            return matches

        except Exception as e:
            logger.error(f"Error in list_matches: {type(e).__name__}: {str(e)}")
            raise

    async def auto_match_pending_bids(self) -> dict:
        """
        Automatically match all pending bids with available offers
        
        Returns:
            Summary of matching results
        """
        try:
            logger.info("Starting auto-match for pending bids")

            # Get all pending bids
            stmt = select(MarketplaceBid).where(MarketplaceBid.status == "pending")
            result = await self.session.execute(stmt)
            pending_bids = result.scalars().all()

            matched_count = 0
            failed_count = 0

            for bid in pending_bids:
                try:
                    # Find best match
                    match = await self.find_best_match(
                        bid_requirements={
                            'capacity': bid.capacity,
                            'max_price': bid.price,
                        }
                    )

                    if match:
                        # Create the match
                        await self.create_match(
                            bid_id=bid.id,
                            offer_id=match['id'],
                            match_data=match
                        )
                        matched_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(f"Failed to match bid {bid.id}: {e}")
                    failed_count += 1

            summary = {
                'total_pending': len(pending_bids),
                'matched': matched_count,
                'failed': failed_count,
                'timestamp': datetime.now(UTC).isoformat(),
            }

            logger.info(f"Auto-match complete: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error in auto_match_pending_bids: {type(e).__name__}: {str(e)}")
            raise
