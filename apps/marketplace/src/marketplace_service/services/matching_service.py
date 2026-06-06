"""
Marketplace matching service for matching GPU providers with consumers
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc import get_logger

from ..domain.marketplace import MarketplaceOffer

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
        # Bids deprecated in v0.4.7 - GPU-only marketplace removed
        # This method is no longer functional
        raise NotImplementedError("Bid-based matching deprecated in v0.4.7")

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
        # Bids deprecated in v0.4.7 - no bid matching available
        raise NotImplementedError("Bid-based matching deprecated in v0.4.7")

    async def auto_match_pending_bids(self) -> dict:
        """
        Automatically match all pending bids with available offers
        
        Returns:
            Summary of matching results
        """
        # Bids deprecated in v0.4.7 - auto-matching no longer available
        raise NotImplementedError("Bid-based auto-matching deprecated in v0.4.7")
