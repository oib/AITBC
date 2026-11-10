"""MKT-RATING-1 (#1446): sync_ratings_from_remote must validate remote ratings.

The local submit path (``add_service_rating`` / ``RatingRequest``) enforces
``1.0 <= rating <= 5.0``, but the sync path used to persist whatever a peer
sent — out-of-range, non-finite or non-numeric values were folded into
``avg_rating``/``rating_count``. These tests pin the range/type check:
legitimate ratings still sync, malformed ones are counted as failed and never
stored.
"""

from uuid import uuid4

import pytest

from market_service.domain.market import ServiceRating
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _remote_rating(**overrides) -> dict:
    base = {
        "id": uuid4().hex,
        "service_id": f"svc_{uuid4().hex[:8]}",
        "rating": 4.5,
        "reviewer_id": f"rev_{uuid4().hex[:8]}",
        "comment": "solid",
        "created_at": "2026-01-01T00:00:00",
        "source_node": "peer-node",
    }
    base.update(overrides)
    return base


async def _count_ratings(session, service_id: str) -> int:
    from sqlalchemy import func, select

    stmt = select(func.count(ServiceRating.id)).where(ServiceRating.service_id == service_id)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def test_sync_accepts_valid_remote_rating():
    """Control case: an in-range remote rating is stored as before."""
    async with get_session_context() as session:
        svc = MarketService(session)
        remote = _remote_rating(rating=4.5)
        result = await svc.sync_ratings_from_remote([remote])
        assert result["synced"] == 1
        assert result["failed"] == 0
        assert await _count_ratings(session, remote["service_id"]) == 1


async def test_sync_rejects_out_of_range_ratings():
    """Ratings outside [1.0, 5.0] are counted failed and never stored."""
    async with get_session_context() as session:
        svc = MarketService(session)
        remotes = [_remote_rating(rating=bad) for bad in (0.0, -1.0, 5.5, 99.0)]
        result = await svc.sync_ratings_from_remote(remotes)
        assert result["synced"] == 0
        assert result["failed"] == len(remotes)
        for remote in remotes:
            assert await _count_ratings(session, remote["service_id"]) == 0


async def test_sync_rejects_non_finite_and_non_numeric_ratings():
    """NaN/inf and non-numeric payloads must not reach the rating column."""
    async with get_session_context() as session:
        svc = MarketService(session)
        remotes = [
            _remote_rating(rating=float("nan")),
            _remote_rating(rating=float("inf")),
            _remote_rating(rating="excellent"),
            _remote_rating(rating=None),
            _remote_rating(rating=True),  # bool is an int subclass — reject explicitly
        ]
        result = await svc.sync_ratings_from_remote(remotes)
        assert result["synced"] == 0
        assert result["failed"] == len(remotes)
        for remote in remotes:
            assert await _count_ratings(session, remote["service_id"]) == 0


async def test_sync_rejects_out_of_range_update_of_existing_rating():
    """A poisoned update must not overwrite a stored rating either."""
    async with get_session_context() as session:
        svc = MarketService(session)
        remote = _remote_rating(rating=4.0)
        await svc.sync_ratings_from_remote([remote])

        # Same service+reviewer, newer timestamp, absurd rating.
        poisoned = _remote_rating(
            id=remote["id"],
            service_id=remote["service_id"],
            reviewer_id=remote["reviewer_id"],
            rating=42.0,
            created_at="2026-02-01T00:00:00",
        )
        result = await svc.sync_ratings_from_remote([poisoned])
        assert result["failed"] == 1
        assert result["updated"] == 0

        from sqlalchemy import select

        stmt = select(ServiceRating).where(
            ServiceRating.service_id == remote["service_id"],
            ServiceRating.reviewer_id == remote["reviewer_id"],
        )
        row = (await session.execute(stmt)).scalar_one()
        assert row.rating == 4.0
