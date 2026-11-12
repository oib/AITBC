"""#1851: ratings/sync is insert-only — a remote payload can never rewrite an
existing (service_id, reviewer) rating.

Pre-fix the sync UPDATE branch overwrote score+comment whenever the forged
``created_at`` was newer, so any holder of the shared market API key could
mutate a known reviewer's real rating by spoofing their reviewer_id.
"""

from uuid import uuid4

import pytest
from sqlmodel import col, select

from market_service.domain.market import ServiceRating
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid4().hex[:8]


def _remote(service_id: str, reviewer_id: str, rating: float, created_at: str, **over) -> dict:
    base = {
        "id": uuid4().hex,
        "service_id": service_id,
        "rating": rating,
        "reviewer_id": reviewer_id,
        "comment": "orig",
        "created_at": created_at,
        "source_node": "peer-node",
    }
    base.update(over)
    return base


async def _fetch(session, service_id: str, reviewer_id: str) -> ServiceRating | None:
    stmt = select(ServiceRating).where(
        ServiceRating.service_id == service_id,
        col(ServiceRating.reviewer_id) == reviewer_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def test_newer_remote_cannot_overwrite_existing_rating():
    """The core exploit: forged newer created_at + different score must not
    rewrite the stored rating."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid, rev = f"svc_1851_{u}", f"0xReviewer{u}"
        first = _remote(sid, rev, 4.0, "2026-01-01T00:00:00")
        assert (await svc.sync_ratings_from_remote([first]))["synced"] == 1

        forged = _remote(sid, rev, 1.0, "2026-06-01T00:00:00", comment="defaced", id=uuid4().hex)
        out = await svc.sync_ratings_from_remote([forged])
        assert out["synced"] == 0
        assert out["skipped"] == 1
        assert out["updated"] == 0

        row = await _fetch(session, sid, rev)
        assert row is not None
        assert row.rating == 4.0
        assert row.comment == "orig"


async def test_case_variant_reviewer_cannot_overwrite():
    """'0xABC' vs '0xabc' dedup must also block the overwrite path."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid = f"svc_1851b_{u}"
        rev = f"0xAbC{u}"
        await svc.sync_ratings_from_remote([_remote(sid, rev, 5.0, "2026-01-01T00:00:00")])

        out = await svc.sync_ratings_from_remote([_remote(sid, rev.lower(), 1.0, "2026-06-01T00:00:00", comment="defaced")])
        assert out["synced"] == 0
        assert out["updated"] == 0
        rows = (await session.execute(select(ServiceRating).where(col(ServiceRating.service_id) == sid))).scalars().all()
        assert len(rows) == 1
        assert rows[0].rating == 5.0


async def test_local_rating_cannot_be_overwritten_by_sync():
    """A locally-submitted rating (the well-bound path) is equally immune —
    sync must never touch source_node='local' rows either."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid, rev = f"svc_1851c_{u}", f"local-reviewer-{u}"
        session.add(
            ServiceRating(
                service_id=sid,
                rating=3.0,
                reviewer_id=rev,
                comment="local review",
                source_node="local",
            )
        )
        await session.commit()

        out = await svc.sync_ratings_from_remote([_remote(sid, rev, 5.0, "2026-06-01T00:00:00", comment="remote deface")])
        assert out["synced"] == 0
        assert out["updated"] == 0
        row = await _fetch(session, sid, rev)
        assert row.rating == 3.0
        assert row.comment == "local review"
        assert row.source_node == "local"


async def test_distinct_reviewers_still_sync():
    """Insert-only must not break legitimate replication: a different
    reviewer_id for the same service still inserts."""
    async with get_session_context() as session:
        svc = MarketService(session)
        u = _uid()
        sid = f"svc_1851d_{u}"
        out = await svc.sync_ratings_from_remote(
            [
                _remote(sid, f"rev-a-{u}", 4.0, "2026-01-01T00:00:00"),
                _remote(sid, f"rev-b-{u}", 2.0, "2026-01-02T00:00:00"),
            ]
        )
        assert out["synced"] == 2
        assert out["skipped"] == 0
