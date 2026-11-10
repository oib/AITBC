"""Market matching service for matching GPU providers with consumers"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.market import OfferFSM, OfferStatus
from aitbc.utils.chain_id import resolve_chain_id

from ..config import settings
from ..domain.market import MarketOffer
from ..domain.offer_status import spellings_of, to_offer_status
from .market_service import max_page_size, offer_reservation_ttl_seconds

logger = get_logger(__name__)


class MatchingService:
    """Service for matching GPU offers with consumer bids"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._http_client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create a shared HTTP client for coordinator calls."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10)
        return self._http_client

    async def aclose(self) -> None:
        """Close the shared HTTP client."""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def find_best_match(
        self,
        bid_requirements: dict[str, Any],
        max_price: Decimal | None = None,
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
            # Match every stored spelling that means AVAILABLE ("available",
            # "open", ...) — filtering on the canonical word alone hides
            # legacy-spelled offers (#1442). Bounded like every other list
            # read: the matcher only ever needs the head of the ordering
            # (#1445).
            stmt = select(MarketOffer).where(col(MarketOffer.status).in_(spellings_of(OfferStatus.AVAILABLE)))
            # #1566: a NULL price_per_hour can never be priced — exclude it
            # unconditionally. Gating this on max_price let priceless offers
            # sort first under ORDER BY price ASC (SQLite sorts NULLs ahead of
            # every value) and win "best match" whenever no max_price was given.
            stmt = stmt.where(MarketOffer.price_per_hour.isnot(None))  # type: ignore
            if max_price is not None:
                stmt = stmt.where(MarketOffer.price_per_hour <= max_price)  # type: ignore
            if preferred_region:
                stmt = stmt.where(MarketOffer.region == preferred_region)
            if min_gpu_memory is not None:
                stmt = stmt.where(MarketOffer.gpu_memory_gb.isnot(None))  # type: ignore
                stmt = stmt.where(MarketOffer.gpu_memory_gb >= min_gpu_memory)  # type: ignore
            if required_gpu_model:
                stmt = stmt.where(MarketOffer.gpu_model == required_gpu_model)
            stmt = stmt.order_by(MarketOffer.price_per_hour.asc(), MarketOffer.capacity.desc())  # type: ignore[union-attr,attr-defined]
            stmt = stmt.limit(max_page_size())
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

    def _calculate_match_score(self, offer: MarketOffer, requirements: dict[str, Any]) -> float:
        """
        Calculate a match score for an offer based on requirements

        Args:
            offer: Market offer
            requirements: Bid requirements

        Returns:
            Match score between 0.0 and 1.0
        """
        score = 1.0
        if requirements.get("max_price"):
            max_price_val = Decimal(str(requirements["max_price"]))
            offer_price = offer.price_per_hour or Decimal("0")
            price_ratio = float(offer_price / max_price_val) if max_price_val > 0 else 0.0
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
        max_price: Decimal | None = None,
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
            # Same alias-aware status filter as find_best_match (#1442), same
            # bound (#1445) — the matcher only consumes offers[0].
            stmt = select(MarketOffer).where(col(MarketOffer.status).in_(spellings_of(OfferStatus.AVAILABLE)))
            # #1566: NULL price_per_hour offers are unpriceable — exclude them
            # unconditionally (see find_best_match); NULLs sort first in SQLite.
            stmt = stmt.where(MarketOffer.price_per_hour.isnot(None))  # type: ignore
            if max_price is not None:
                stmt = stmt.where(MarketOffer.price_per_hour <= max_price)  # type: ignore
            if preferred_region:
                stmt = stmt.where(MarketOffer.region == preferred_region)
            if chain_id:
                stmt = stmt.where(MarketOffer.chain_id == chain_id)
            stmt = stmt.order_by(
                MarketOffer.price_per_hour.asc(),  # type: ignore[union-attr]
                MarketOffer.created_at.asc(),  # type: ignore[attr-defined]
            )
            stmt = stmt.limit(max_page_size())
            result = await self.session.execute(stmt)
            offers = result.scalars().all()
            if not offers:
                logger.info("No matching offers found for requirements (chain_id=%s)", chain_id)
                return {"status": "no_match", "chain_id": chain_id}

            best_offer = offers[0]

            # Reserve the offer via OfferFSM. The stored word may be an alias
            # ("open"), which OfferFSM.from_string rejects — map it first
            # (#1442).
            current = to_offer_status(best_offer.status)
            fsm = OfferFSM(current)
            fsm.transition(OfferStatus.RESERVED)
            best_offer.status = OfferStatus.RESERVED.value
            # #1554: a matched offer stays RESERVED until the coordinator
            # task completes or the reservation TTL lapses — the sweeper
            # returns expired holds to AVAILABLE. Stored in attributes (JSON)
            # because MarketOffer is a shared model (see book_offer).
            reserved_attrs = dict(best_offer.attributes or {})
            reserved_attrs["_reserved_until"] = (
                datetime.now(UTC) + timedelta(seconds=offer_reservation_ttl_seconds())
            ).isoformat()
            best_offer.attributes = reserved_attrs
            await self.session.commit()

            # Submit task to agent-coordinator
            task_id = None
            escrow_id = None
            job_id = None
            try:
                task_payload: dict[str, Any] = {
                    "task_data": {
                        "chain_id": chain_id or best_offer.chain_id or settings.default_chain_id or resolve_chain_id(),
                        "offer_id": best_offer.id,
                        "provider": best_offer.provider,
                        "price_per_hour": str(best_offer.price_per_hour) if best_offer.price_per_hour is not None else None,
                        "requirements": requirements,
                    },
                    "priority": "normal",
                    "requirements": requirements,
                    "chain_id": chain_id or best_offer.chain_id or settings.default_chain_id or resolve_chain_id(),
                    "payment": None,
                }
                if max_price is not None:
                    task_payload["task_data"]["max_price"] = str(max_price)
                client = self._ensure_client()
                resp = await client.post(
                    f"{settings.agent_coordinator_url}/tasks/submit",
                    json=task_payload,
                )
                resp.raise_for_status()
                task_data = resp.json()
                task_id = task_data.get("task_id")
                escrow_id = task_data.get("escrow_id")
                # v0.10.1: job_id is the preferred identifier for escrow verification
                job_id = task_data.get("job_id") or escrow_id
            except Exception as e:
                logger.warning("Failed to submit task to agent-coordinator: %s", e)
                # Release the reservation so the offer does not stay stuck.
                fsm.transition(OfferStatus.AVAILABLE)
                best_offer.status = OfferStatus.AVAILABLE.value
                released_attrs = dict(best_offer.attributes or {})
                released_attrs.pop("_reserved_until", None)
                best_offer.attributes = released_attrs
                await self.session.commit()

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
                "job_id": job_id,
                "match_score": self._calculate_match_score(best_offer, requirements),
            }
        except Exception as e:
            logger.error("Error in match_and_assign: %s: %s", type(e).__name__, str(e))
            raise
