"""
Marketplace service for managing marketplace operations
"""

from typing import Any

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import get_logger
from ..domain.marketplace import MarketplaceOffer, MarketplaceBid

logger = get_logger(__name__)


class MarketplaceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_offers(
        self,
        status: str | None = None,
        region: str | None = None,
        gpu_model: str | None = None,
    ) -> list[dict]:
        """List marketplace offers"""
        try:
            logger.info(f"list_offers called with filters: status={status}, region={region}, gpu_model={gpu_model}")
            stmt = select(MarketplaceOffer)
            if status:
                stmt = stmt.where(MarketplaceOffer.status == status)
            if region:
                stmt = stmt.where(MarketplaceOffer.region == region)
            if gpu_model:
                stmt = stmt.where(MarketplaceOffer.gpu_model == gpu_model)
            logger.info("Executing database query for offers")
            result = list((await self.session.execute(stmt)).all())
            logger.info(f"Retrieved {len(result)} offers")
            # Convert SQLAlchemy model objects to dictionaries for JSON serialization
            offers_list = []
            for row in result:
                offer = row[0] if row else None
                if offer:
                    offers_list.append({
                        'id': offer.id,
                        'provider': offer.provider,
                        'capacity': offer.capacity,
                        'price': offer.price,
                        'sla': offer.sla,
                        'status': offer.status,
                        'created_at': offer.created_at.isoformat() if offer.created_at else None,
                        'attributes': offer.attributes,
                        'gpu_model': offer.gpu_model,
                        'gpu_memory_gb': offer.gpu_memory_gb,
                        'gpu_count': offer.gpu_count,
                        'cuda_version': offer.cuda_version,
                        'price_per_hour': offer.price_per_hour,
                        'region': offer.region,
                    })
            logger.info(f"Converted {len(offers_list)} offers to dictionaries")
            return offers_list
        except Exception as e:
            logger.error(f"Error in list_offers: {type(e).__name__}: {str(e)}")
            raise

    async def get_offer(self, offer_id: str) -> MarketplaceOffer | None:
        """Get a specific marketplace offer"""
        try:
            logger.info(f"get_offer called with offer_id={offer_id}")
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.id == offer_id)
            result = (await self.session.execute(stmt)).first()
            offer = result[0] if result else None
            logger.info(f"Retrieved offer: {offer_id}, found: {offer is not None}")
            return offer
        except Exception as e:
            logger.error(f"Error in get_offer: {type(e).__name__}: {str(e)}")
            raise

    async def create_offer(self, offer_data: dict) -> MarketplaceOffer:
        """Create a new marketplace offer"""
        try:
            logger.info(f"create_offer called with data keys: {offer_data.keys()}")
            # Map wallet to provider for CLI compatibility
            if 'wallet' in offer_data and 'provider' not in offer_data:
                offer_data['provider'] = offer_data['wallet']
                logger.info(f"Mapped wallet '{offer_data['wallet']}' to provider")
            offer = MarketplaceOffer(**offer_data)
            self.session.add(offer)
            await self.session.commit()
            await self.session.refresh(offer)
            logger.info(f"Created offer with id: {offer.id}")
            return offer
        except Exception as e:
            logger.error(f"Error in create_offer: {type(e).__name__}: {str(e)}")
            raise

    async def list_bids(
        self,
        status: str | None = None,
        provider: str | None = None,
    ) -> list[MarketplaceBid]:
        """List marketplace bids"""
        try:
            logger.info(f"list_bids called with filters: status={status}, provider={provider}")
            stmt = select(MarketplaceBid)
            if status:
                stmt = stmt.where(MarketplaceBid.status == status)
            if provider:
                stmt = stmt.where(MarketplaceBid.provider == provider)
            logger.info("Executing database query for bids")
            result = list((await self.session.execute(stmt)).all())
            logger.info(f"Retrieved {len(result)} bids")
            return result
        except Exception as e:
            logger.error(f"Error in list_bids: {type(e).__name__}: {str(e)}")
            raise

    async def create_bid(self, bid_data: dict) -> MarketplaceBid:
        """Create a new marketplace bid"""
        try:
            logger.info(f"create_bid called with data keys: {bid_data.keys()}")
            bid = MarketplaceBid(**bid_data)
            self.session.add(bid)
            await self.session.commit()
            await self.session.refresh(bid)
            logger.info(f"Created bid with id: {bid.id}")
            return bid
        except Exception as e:
            logger.error(f"Error in create_bid: {type(e).__name__}: {str(e)}")
            raise

    async def get_analytics(self, period_type: str = "daily") -> dict[str, Any]:
        """Get marketplace analytics"""
        # Placeholder for analytics logic
        return {
            "period_type": period_type,
            "total_offers": 0,
            "total_transactions": 0,
            "total_volume": 0.0,
            "average_price": 0.0,
        }
