"""Coverage pin: ``offset`` on market job listing (#1489/#1503 residual).

``GET /v1/market/jobs`` gained an ``offset`` query param (04e507343) so the
ipfs_pinning_sweeper can paginate the bounded result set, and
``MarketService.list_market_jobs`` floors it at 0 like ``limit``. No test
exercised the parameter — this pins service-level paging semantics and the
route accepting the param without a 422.

Coder: C
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

# asyncio_mode=auto in pyproject — no pytestmark needed (a module-wide
# asyncio mark would flag the sync route test below).

SEEDED = 6
PAGE = 2


async def _seed_jobs(session: AsyncSession, n: int = SEEDED) -> list[str]:
    u = uuid4().hex[:8]
    ids: list[str] = []
    for i in range(n):
        job_id = f"job_off_{u}_{i}"
        pay = MarketJobPayment(job_id=job_id, amount=1, status="locked")
        job = MarketJob(
            id=job_id,
            buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
            provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
            service_type="ipfs",
            state="PAID",
            payment_id=pay.id,
        )
        session.add(pay)
        session.add(job)
        ids.append(job_id)
    await session.commit()
    return ids


async def test_list_market_jobs_pages_with_offset() -> None:
    async with get_session_context() as session:
        seeded = await _seed_jobs(session)
        svc = MarketService(session)

        pages: list[list[str]] = []
        for offset in range(0, SEEDED, PAGE):
            jobs = await svc.list_market_jobs(limit=PAGE, offset=offset)
            pages.append([j["job_id"] for j in jobs])

        flat = [jid for page in pages for jid in page]
        # Every seeded job appears exactly once across the pages — offset
        # actually skips rows rather than re-reading the head each time.
        assert sorted(flat) == sorted(seeded)
        assert all(len(page) <= PAGE for page in pages)
        # Pages are disjoint: no job_id repeats between offsets.
        assert len(flat) == len(set(flat)) == SEEDED


async def test_list_market_jobs_offset_beyond_end_is_empty() -> None:
    async with get_session_context() as session:
        await _seed_jobs(session, n=3)
        svc = MarketService(session)
        jobs = await svc.list_market_jobs(limit=PAGE, offset=10_000)
        assert jobs == []


async def test_list_market_jobs_negative_offset_floored() -> None:
    """SQLite errors on negative OFFSET — the service floors it at 0, the
    same guard limit gets (limit=-5 must not mean 'unlimited')."""
    async with get_session_context() as session:
        await _seed_jobs(session, n=3)
        svc = MarketService(session)
        neg = await svc.list_market_jobs(limit=PAGE, offset=-5)
        zero = await svc.list_market_jobs(limit=PAGE, offset=0)
        assert [j["job_id"] for j in neg] == [j["job_id"] for j in zero]
        assert len(neg) <= PAGE


def test_jobs_route_accepts_offset_param() -> None:
    """Route-level: ?offset= must parse (the sweeper spells it explicitly)."""
    from fastapi.testclient import TestClient

    from market_service.main import app as market_app

    with TestClient(market_app) as client:
        response = client.get("/v1/market/jobs", params={"limit": 5, "offset": 0})
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) <= 5
