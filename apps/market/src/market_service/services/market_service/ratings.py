"""
MarketService service-rating mixin.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import or_
from sqlmodel import col

from aitbc.aitbc_logging import get_logger

from ...domain.market import Bid, MarketJob, ServiceRating, SoftwareService


logger = get_logger(__name__)

from .shared import (
    _OPS_ERRORS,
    _coerce_remote_rating,
    _rating_created_at,
    max_page_size,
)

from .core import _CoreMixin


class _RatingsMixin(_CoreMixin):
    if TYPE_CHECKING:
        # Provided by _OffersMixin/_JobsMixin via MarketService MRO; declared for mypy.
        async def get_software_service(self, plugin_id: str) -> dict[str, Any] | None: ...
        async def get_service_by_offer_id(self, offer_id: str) -> dict[str, Any] | None: ...

    # Job states that prove a paid interaction completed — a rating is only
    # accepted from a reviewer who reached one of these with this service.
    _RATING_PROVEN_STATES = frozenset({"RELEASED", "COMPLETED"})

    async def _require_local_rating_binding(self, service_id: str, service: dict[str, Any] | None, reviewer_id: str) -> None:
        """Bind a locally-submitted rating to a real counterparty interaction (#1584).

        ``reviewer_id`` is caller-supplied, so without a check any caller
        could stuff a service's rating or bomb it with fake reviews. A local
        rating now requires the reviewer to be an address that completed a
        job or bid for this service, one rating per reviewer per service,
        and never the provider rating its own service. Remote-synced ratings
        keep their peer-trust model (cross-node proof is a separate problem).
        """
        from sqlalchemy import select

        reviewer = self._canonical_address(reviewer_id)
        provider = self._canonical_address(str((service or {}).get("provider_address") or ""))
        if provider and reviewer == provider:
            raise ValueError("Service provider cannot rate its own service")

        # One rating per reviewer per service — compare canonically so case or
        # whitespace variants of the same address cannot bypass it.
        existing_rows = (
            (await self.session.execute(select(ServiceRating).where(col(ServiceRating.service_id) == service_id)))
            .scalars()
            .all()
        )
        if any(self._canonical_address(str(r.reviewer_id)) == reviewer for r in existing_rows):
            raise ValueError("Reviewer has already rated this service")

        service = service or {}
        keys = {k for k in {service_id, service.get("plugin_id"), service.get("offer_id")} if k}

        def _buyer_proven(buyer: Any, state: str | None, completed_states: frozenset[str]) -> bool:
            return bool(buyer) and state in completed_states and self._canonical_address(str(buyer)) == reviewer

        job_rows = (
            (
                await self.session.execute(
                    select(MarketJob)
                    .where(or_(col(MarketJob.offer_id).in_(keys), col(MarketJob.plugin_id).in_(keys)))
                    .where(col(MarketJob.buyer_address).isnot(None))
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        for job in job_rows:
            if _buyer_proven(job.buyer_address, job.state, self._RATING_PROVEN_STATES):
                return
        bid_rows = (
            (
                await self.session.execute(
                    select(Bid).where(col(Bid.offer_id).in_(keys), col(Bid.status) == "completed").limit(200)
                )
            )
            .scalars()
            .all()
        )
        for bid in bid_rows:
            if _buyer_proven(bid.buyer, bid.status, frozenset({"completed"})):
                return
        raise ValueError("reviewer_id has no completed job or bid for this service")

    async def add_service_rating(
        self,
        service_id: str,
        rating: float,
        reviewer_id: str,
        comment: str = "",
        source_node: str = "local",
        service: dict[str, Any] | None = None,
    ) -> ServiceRating:
        """Add a service rating and update service average rating"""
        try:
            if not 1.0 <= rating <= 5.0:
                raise ValueError("Rating must be between 1.0 and 5.0")
            if source_node == "local":
                if service is None:
                    service = await self.get_software_service(service_id) or await self.get_service_by_offer_id(service_id)
                if service is None:
                    raise ValueError(f"Service not found: {service_id}")
                await self._require_local_rating_binding(service_id, service, reviewer_id)
            service_rating = ServiceRating(
                service_id=service_id, rating=rating, reviewer_id=reviewer_id, comment=comment, source_node=source_node
            )
            self.session.add(service_rating)
            await self.session.commit()
            await self.session.refresh(service_rating)
            logger.info("Added rating %s for service %s by reviewer %s from %s", rating, service_id, reviewer_id, source_node)
            await self._update_service_rating(service_id)
            return service_rating
        except Exception as e:
            logger.error("Error in add_service_rating: %s: %s", type(e).__name__, str(e))
            raise

    async def get_service_ratings(self, service_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get ratings for a specific service"""
        try:
            from sqlalchemy import select

            # Caller limits are clamped to the server page ceiling — a
            # negative or huge ?limit= must not become an unbounded read (#1543).
            limit = min(max(int(limit), 1), max_page_size())
            offset = max(int(offset), 0)
            stmt = select(ServiceRating).where(ServiceRating.service_id == service_id)  # type: ignore[arg-type]
            stmt = stmt.order_by(ServiceRating.created_at.desc())  # type: ignore[attr-defined]
            stmt = stmt.limit(limit).offset(offset)
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "service_id": r.service_id,
                    "rating": r.rating,
                    "reviewer_id": r.reviewer_id,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "source_node": r.source_node,
                }
                for r in ratings
            ]
        except Exception as e:
            logger.error("Error in get_service_ratings: %s: %s", type(e).__name__, str(e))
            raise

    async def get_unsynced_ratings(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get ratings that haven't been synced yet"""
        try:
            from sqlalchemy import select

            # Same ceiling as the sibling list paths — ?limit= was unchecked (#1543).
            limit = min(max(int(limit), 1), max_page_size())
            stmt = (
                select(ServiceRating)
                .where(ServiceRating.synced_at.is_(None))  # type: ignore[union-attr]
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "service_id": r.service_id,
                    "rating": r.rating,
                    "reviewer_id": r.reviewer_id,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat(),
                    "source_node": r.source_node,
                }
                for r in ratings
            ]
        except Exception as e:
            logger.error("Error in get_unsynced_ratings: %s: %s", type(e).__name__, str(e))
            raise

    async def mark_ratings_synced(self, rating_ids: list[str]) -> int:
        """Mark ratings as synced"""
        try:
            from datetime import UTC, datetime

            from sqlalchemy import select

            stmt = select(ServiceRating).where(ServiceRating.id.in_(rating_ids))  # type: ignore[attr-defined]
            result = await self.session.execute(stmt)
            ratings = result.scalars().all()
            for rating in ratings:
                rating.synced_at = datetime.now(UTC).replace(tzinfo=None)
            await self.session.commit()
            logger.info("Marked %s ratings as synced", len(ratings))
            return len(ratings)
        except Exception as e:
            logger.error("Error in mark_ratings_synced: %s: %s", type(e).__name__, str(e))
            raise

    async def sync_ratings_from_remote(self, remote_ratings: list[dict[str, Any]]) -> dict[str, Any]:
        """Sync ratings from remote node.

        Insert-only (#1851): an existing (service_id, reviewer) rating is
        never overwritten by sync — first-seen wins, so a spoofed reviewer_id
        cannot rewrite a real rating. ``updated`` stays in the response for
        API compatibility and is always 0.
        """
        try:
            from datetime import UTC, datetime

            from sqlalchemy import func, select

            synced_count = 0
            updated_count = 0
            skipped_count = 0
            failed_count = 0
            touched_services: set[str] = set()
            # Bound the batch like every other list path (#1634) — the route
            # is API-key gated but the payload size was caller-controlled.
            batch = remote_ratings[: max_page_size()]
            if len(remote_ratings) > len(batch):
                logger.warning("ratings/sync batch truncated to %s rows", len(batch))
            for remote_rating in batch:
                try:
                    # Same 1-5 range the local submit path enforces — a
                    # malformed peer payload must not poison avg_rating (#1446).
                    rating_value = float(remote_rating["rating"])
                    if not 1.0 <= rating_value <= 5.0:
                        raise ValueError(f"rating out of range: {remote_rating['rating']!r}")
                    remote_created = _rating_created_at(remote_rating["created_at"])
                    rating_value = _coerce_remote_rating(remote_rating["rating"])
                    # Dedup case-insensitively: "0xAbC" and "0xabc" are the
                    # same reviewer and must not become two ratings (#1634).
                    stmt = select(ServiceRating).where(
                        ServiceRating.service_id == remote_rating["service_id"],
                        func.lower(ServiceRating.reviewer_id) == str(remote_rating["reviewer_id"]).strip().lower(),
                    )
                    result = await self.session.execute(stmt)
                    existing = result.scalar_one_or_none()
                    if existing:
                        # #1851: sync is insert-only. The (service_id,
                        # reviewer) dedup key means a caller spoofing a known
                        # reviewer_id could previously rewrite that reviewer's
                        # real rating whenever the forged created_at was newer.
                        # First-seen wins; rating edits on the source node do
                        # not propagate (peer-trust model limitation).
                        skipped_count += 1
                    else:
                        new_rating = ServiceRating(
                            id=remote_rating["id"],
                            service_id=remote_rating["service_id"],
                            rating=rating_value,
                            reviewer_id=remote_rating["reviewer_id"],
                            comment=remote_rating["comment"],
                            created_at=remote_created,
                            synced_at=datetime.now(UTC).replace(tzinfo=None),
                            # source_node is caller-supplied provenance —
                            # sanitize it rather than trusting the raw value
                            # (#1634).
                            source_node=str(remote_rating.get("source_node") or "remote").strip()[:128] or "remote",
                        )
                        self.session.add(new_rating)
                        synced_count += 1
                    touched_services.add(remote_rating["service_id"])
                except _OPS_ERRORS as e:
                    failed_count += 1
                    logger.warning("Skipping malformed remote rating %s: %s", remote_rating.get("id", "?"), e)
            await self.session.commit()
            logger.info(
                "Synced %s new, updated %s, skipped %s, failed %s ratings",
                synced_count,
                updated_count,
                skipped_count,
                failed_count,
            )
            for service_id in touched_services:
                await self._update_service_rating(service_id)
            return {
                "synced": synced_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
            }
        except Exception as e:
            logger.error("Error in sync_ratings_from_remote: %s: %s", type(e).__name__, str(e))
            raise

    async def _update_service_rating(self, service_id: str) -> None:
        """Calculate and update service average rating"""
        try:
            from sqlalchemy import func, select

            stmt = select(func.avg(ServiceRating.rating), func.count(ServiceRating.id))  # type: ignore[arg-type]
            stmt = stmt.where(ServiceRating.service_id == service_id)  # type: ignore[arg-type]
            result = await self.session.execute(stmt)
            avg_rating, count = result.first()
            service_stmt = select(SoftwareService).where(SoftwareService.plugin_id == service_id)  # type: ignore[arg-type]
            service_result = await self.session.execute(service_stmt)
            service = service_result.scalar_one_or_none()
            if not service:
                service_stmt = select(SoftwareService).where(SoftwareService.offer_id == service_id)  # type: ignore[arg-type]
                service_result = await self.session.execute(service_stmt)
                service = service_result.scalar_one_or_none()
            if service:
                service.avg_rating = float(avg_rating) if avg_rating else 0.0
                service.rating_count = int(count) if count else 0
                await self.session.commit()
                logger.info(
                    "Updated service %s rating: avg=%s, count=%s", service_id, service.avg_rating, service.rating_count
                )
        except Exception as e:
            logger.error("Error in _update_service_rating: %s: %s", type(e).__name__, str(e))
            raise
