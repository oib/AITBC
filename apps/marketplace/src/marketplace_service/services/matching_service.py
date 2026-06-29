"""Marketplace matching service for matching GPU providers with consumers"""

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.marketplace import OfferFSM, OfferStatus

from ..config import settings
from ..domain.marketplace import MarketplaceOffer

logger = get_logger(__name__)


class MatchingService:
    """Service for matching GPU offers with consumer bids"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_best_match(
        self,
        bid_requirements: dict[str, Any],
        max_price: float | None = None,
        preferred_region: str | None = None,
        min_gpu_memory: int | None = None,
        required_gpu_model: str | None = None,
    ) -> dict[str, Any] | None:
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
            logger.info("Finding best match for bid requirements: %s", bid_requirements.keys())
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.status == "active")
            if max_price is not None:
                stmt = stmt.where(MarketplaceOffer.price_per_hour.isnot(None))  # type: ignore
                stmt = stmt.where(MarketplaceOffer.price_per_hour <= max_price)  # type: ignore
            if preferred_region:
                stmt = stmt.where(MarketplaceOffer.region == preferred_region)
            if min_gpu_memory is not None:
                stmt = stmt.where(MarketplaceOffer.gpu_memory_gb.isnot(None))  # type: ignore
                stmt = stmt.where(MarketplaceOffer.gpu_memory_gb >= min_gpu_memory)  # type: ignore
            if required_gpu_model:
                stmt = stmt.where(MarketplaceOffer.gpu_model == required_gpu_model)
            stmt = stmt.order_by(MarketplaceOffer.price_per_hour.asc(), MarketplaceOffer.capacity.desc())  # type: ignore[union-attr,attr-defined]
            result = await self.session.execute(stmt)
            offers = result.scalars().all()
            if not offers:
                logger.info("No matching offers found")
                return None
            best_offer = offers[0]
            logger.info("Found best match: offer_id=%s, price=%s", best_offer.id, best_offer.price_per_hour)
            return {
                "id": best_offer.id,
                "provider": best_offer.provider,
                "capacity": best_offer.capacity,
                "price": best_offer.price,
                "price_per_hour": best_offer.price_per_hour,
                "gpu_model": best_offer.gpu_model,
                "gpu_memory_gb": best_offer.gpu_memory_gb,
                "gpu_count": best_offer.gpu_count,
                "region": best_offer.region,
                "match_score": self._calculate_match_score(best_offer, bid_requirements),
            }
        except Exception as e:
            logger.error("Error in find_best_match: %s: %s", type(e).__name__, str(e))
            raise

    def _calculate_match_score(self, offer: MarketplaceOffer, requirements: dict[str, Any]) -> float:
        """
        Calculate a match score for an offer based on requirements

        Args:
            offer: Marketplace offer
            requirements: Bid requirements

        Returns:
            Match score between 0.0 and 1.0
        """
        score = 1.0
        if requirements.get("max_price"):
            price_ratio = offer.price_per_hour / requirements["max_price"]
            score *= 1.0 - price_ratio * 0.3
        if requirements.get("capacity"):
            capacity_ratio = min(offer.capacity / requirements["capacity"], 2.0)
            score *= 0.7 + capacity_ratio * 0.15
        if requirements.get("preferred_region") and offer.region == requirements["preferred_region"]:
            score *= 1.1
        return min(max(score, 0.0), 1.0)

    async def match_and_assign(
        self,
        requirements: dict[str, Any],
        max_price: float | None = None,
        preferred_region: str | None = None,
        chain_id: str | None = None,
    ) -> dict[str, Any]:
        """Match a compute request to the best available GPU offer (v0.6.6).

        Implements price-time priority: offers are sorted by price (ascending)
        then by registration time (oldest first). The best match is reserved
        via OfferFSM and a task is submitted to the agent-coordinator.

        Returns a dict with the match details, task_id, and escrow_id.
        """
        try:
            # Price-time priority: order by price asc, then created_at asc (oldest first)
            stmt = select(MarketplaceOffer).where(MarketplaceOffer.status == "active")
            if max_price is not None:
                stmt = stmt.where(MarketplaceOffer.price_per_hour.isnot(None))  # type: ignore
                stmt = stmt.where(MarketplaceOffer.price_per_hour <= max_price)  # type: ignore
            if preferred_region:
                stmt = stmt.where(MarketplaceOffer.region == preferred_region)
            if chain_id:
                stmt = stmt.where(MarketplaceOffer.chain_id == chain_id)
            stmt = stmt.order_by(
                MarketplaceOffer.price_per_hour.asc(),  # type: ignore[union-attr]
                MarketplaceOffer.created_at.asc(),  # type: ignore[union-attr]
            )
            result = await self.session.execute(stmt)
            offers = result.scalars().all()
            if not offers:
                logger.info("No matching offers found for requirements (chain_id=%s)", chain_id)
                return {"status": "no_match", "chain_id": chain_id}

            best_offer = offers[0]

            # Reserve the offer via OfferFSM
            current = OfferFSM.from_string(best_offer.status)
            fsm = OfferFSM(current)
            fsm.transition(OfferStatus.RESERVED)
            best_offer.status = OfferStatus.RESERVED.value
            await self.session.commit()

            # Submit task to agent-coordinator
            task_id = None
            escrow_id = None
            try:
                task_payload = {
                    "chain_id": chain_id or best_offer.chain_id or settings.default_chain_id,
                    "offer_id": best_offer.id,
                    "requirements": requirements,
                    "max_price": max_price,
                    "preferred_region": preferred_region,
                    "payment": {"escrow_required": True},
                }
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{settings.agent_coordinator_url}/tasks/submit",
                        json=task_payload,
                    )
                    resp.raise_for_status()
                    task_data = resp.json()
                    task_id = task_data.get("task_id")
                    escrow_id = task_data.get("escrow_id")
            except Exception as e:
                logger.warning("Failed to submit task to agent-coordinator: %s", e)

            logger.info(
                "Matched offer %s (price=%s) for chain_id=%s, task_id=%s",
                best_offer.id,
                best_offer.price_per_hour,
                chain_id,
                task_id,
            )
            return {
                "status": "matched",
                "offer_id": best_offer.id,
                "provider": best_offer.provider,
                "price_per_hour": best_offer.price_per_hour,
                "gpu_model": best_offer.gpu_model,
                "region": best_offer.region,
                "chain_id": best_offer.chain_id,
                "task_id": task_id,
                "escrow_id": escrow_id,
                "match_score": self._calculate_match_score(best_offer, requirements),
            }
        except Exception as e:
            logger.error("Error in match_and_assign: %s: %s", type(e).__name__, str(e))
            raise
