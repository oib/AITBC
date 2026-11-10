"""Phase-0 pin for MARKET-UNBOUNDED-READS-1 (#818).

Four unbounded reads on the market service:

1. ``GET /v1/market/jobs?limit=…`` takes the caller's limit unchecked —
   ``?limit=10**8`` is passed straight to ``.limit()`` — and then runs one
   ``session.get`` per job for the payment row (N+1).
2. ``GET /v1/transactions`` selects every ``MarketOffer`` row with no LIMIT.
3. ``GET /v1/market/offers`` and ``list_software_services`` do the same on
   their tables.
4. ``check_software_offer_health`` materialises the whole IPFS ``pin/ls``
   response via ``resp.text`` — every pin on the provider in memory — just
   to count lines.

Desired behaviour (pinned here): a server-side ceiling — env
``MARKET_MAX_PAGE_SIZE`` (default pinned at 500) — clamps every list
endpoint regardless of the caller's ``limit`` or its absence, payments are
fetched in one batched select instead of a per-job ``get``, and the health
check counts a bounded stream of pin lines (``HEALTH_PIN_SAMPLE_LIMIT``)
without reading the body whole. All tests FAIL on current main — that is
the bug demonstration.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import engine, get_session_context

pytestmark = pytest.mark.asyncio

PAGE_ENV = "MARKET_MAX_PAGE_SIZE"
PIN_ENV = "HEALTH_PIN_SAMPLE_LIMIT"
SEEDED = 12
CAP = 5
PIN_CAP = 3


@pytest.fixture
def capped(monkeypatch):
    monkeypatch.setenv(PAGE_ENV, str(CAP))
    monkeypatch.setenv(PIN_ENV, str(PIN_CAP))
    return CAP


def _uid() -> str:
    from uuid import uuid4

    return uuid4().hex[:8]


async def _seed_jobs(session: AsyncSession, n: int = SEEDED) -> None:
    u = _uid()
    for i in range(n):
        pay = MarketJobPayment(job_id=f"job_pin_{u}_{i}", amount=1, status="locked")
        job = MarketJob(
            id=f"job_pin_{u}_{i}",
            buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
            provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
            service_type="ipfs",
            state="PAID",
            payment_id=pay.id,
        )
        session.add(pay)
        session.add(job)
    await session.commit()


async def _seed_offers(session: AsyncSession, n: int = SEEDED) -> None:
    from aitbc_shared import MarketOffer

    u = _uid()
    for i in range(n):
        session.add(MarketOffer(id=f"offer_pin_{u}_{i}", provider="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2", status="open"))
    await session.commit()


async def _seed_services(session: AsyncSession, n: int = SEEDED) -> None:
    u = _uid()
    for i in range(n):
        session.add(SoftwareService(plugin_id=f"svc_pin_{u}_{i}", service_type="whisper", status="active"))
    await session.commit()


async def test_jobs_limit_is_server_capped(capped):
    """?limit=10**8 must not return more than the server page ceiling."""
    async with get_session_context() as session:
        await _seed_jobs(session)
        svc = MarketService(session)
        jobs = await svc.list_market_jobs(limit=10**8)
        assert len(jobs) <= CAP, f"caller limit was honoured unchecked: got {len(jobs)} jobs, cap is {CAP}"


async def test_jobs_payments_are_one_batched_query(capped):
    """The payment join must not run one session.get per job (N+1)."""
    async with get_session_context() as session:
        await _seed_jobs(session)
        svc = MarketService(session)
        seen: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "marketplace_job_payments" in statement.lower():
                seen.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            await svc.list_market_jobs(limit=CAP)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        assert len(seen) <= 1, f"{len(seen)} payment queries for one page — N+1 fetch pattern"


async def test_transactions_endpoint_is_bounded(capped):
    """GET /v1/transactions selects every offer row with no LIMIT today."""
    from fastapi.testclient import TestClient

    from market_service.main import app

    async with get_session_context() as session:
        await _seed_offers(session)
    with TestClient(app) as client:
        body = client.get("/v1/transactions").json()
        assert len(body) <= CAP, f"no-LIMIT select returned {len(body)} rows, cap is {CAP}"


async def test_offers_list_is_bounded(capped):
    async with get_session_context() as session:
        await _seed_offers(session)
        svc = MarketService(session)
        offers = await svc.list_offers()
        assert len(offers) <= CAP, f"unbounded select returned {len(offers)} offers, cap is {CAP}"


async def test_software_services_list_is_bounded(capped):
    async with get_session_context() as session:
        await _seed_services(session)
        svc = MarketService(session)
        with patch.object(svc._rpc_client, "query_offers", new=AsyncMock(return_value=[])):
            services = await svc.list_software_services()
        assert len(services) <= CAP, f"unbounded select returned {len(services)} services, cap is {CAP}"


async def test_edge_advertise_is_bounded(capped):
    """GET /v1/market/edge-advertise must not return more than the page ceiling (#1507)."""
    from fastapi.testclient import TestClient

    from market_service.domain.market import EdgeNodeAdvertisement
    from market_service.main import app

    u = _uid()
    async with get_session_context() as session:
        for i in range(SEEDED):
            session.add(EdgeNodeAdvertisement(node_id=f"edge_pin_{u}_{i}", endpoint="http://edge.test", status="active"))
        await session.commit()
    with TestClient(app) as client:
        body = client.get("/v1/market/edge-advertise").json()
        assert len(body["nodes"]) <= CAP, f"no-LIMIT select returned {len(body['nodes'])} nodes, cap is {CAP}"


async def test_service_ratings_limit_is_server_capped(capped):
    """?limit= on the ratings endpoints must clamp to the page ceiling (#1543)."""
    from market_service.domain.market import ServiceRating

    u = _uid()
    async with get_session_context() as session:
        for i in range(SEEDED):
            session.add(ServiceRating(service_id=f"svc_pin_{u}", rating=4.0, reviewer_id=f"rev_{i}"))
        await session.commit()
        svc = MarketService(session)
        ratings = await svc.get_service_ratings(f"svc_pin_{u}", limit=10**8)
        assert len(ratings) <= CAP, f"caller limit honoured unchecked: {len(ratings)} ratings, cap {CAP}"
        # A negative limit must not become SQLite "unlimited" either.
        ratings = await svc.get_service_ratings(f"svc_pin_{u}", limit=-1)
        assert len(ratings) <= CAP, f"negative limit unbounded: {len(ratings)} ratings, cap {CAP}"
        unsynced = await svc.get_unsynced_ratings(limit=10**8)
        assert len(unsynced) <= CAP, f"unsynced caller limit unchecked: {len(unsynced)}, cap {CAP}"


async def test_query_graph_is_bounded(capped):
    """GET /v1/knowledge-graph/{id} must cap nodes and edges at the ceiling (#1543)."""
    from market_service.domain.market import GraphEdge, GraphNode

    u = _uid()
    gid = f"graph_pin_{u}"
    async with get_session_context() as session:
        for i in range(SEEDED):
            session.add(GraphNode(graph_id=gid, node_type="entity", label=f"n{i}", properties={}))
            session.add(
                GraphEdge(
                    graph_id=gid,
                    source_node_id=f"s{i}",
                    target_node_id=f"t{i}",
                    edge_type="relates_to",
                    properties={},
                )
            )
        await session.commit()
        svc = MarketService(session)
        result = await svc.query_graph(gid)
        assert len(result["nodes"]) <= CAP, f"unbounded node select: {len(result['nodes'])}, cap {CAP}"
        assert len(result["edges"]) <= CAP, f"unbounded edge select: {len(result['edges'])}, cap {CAP}"


async def test_health_check_does_not_materialise_pin_body(capped):
    """pin/ls must be counted as a bounded stream, never read via .text whole."""
    async with get_session_context() as session:
        session.add(
            SoftwareService(
                plugin_id="ipfs_pin_1",
                service_type="ipfs",
                status="active",
                health_url="http://ipfs.test/api/v0/version",
            )
        )
        await session.commit()
        svc = MarketService(session)

        version_resp = Mock()
        version_resp.status_code = 200
        version_resp.json.return_value = {"Version": "0.1", "ID": "peer1"}
        version_resp.raise_for_status = Mock()

        pin_resp = Mock()
        pin_resp.status_code = 200
        accessed: list[str] = []
        # Any whole-body access is recorded: the fix must stream lines instead.
        type(pin_resp).text = property(
            lambda self: accessed.append("text") or "\n".join(f'{{"Cid":"x{i}"}}' for i in range(SEEDED))
        )
        type(pin_resp).content = property(lambda self: accessed.append("content") or b"")
        pin_resp.aiter_lines = lambda: _aiter([f'{{"Cid":"x{i}"}}' for i in range(SEEDED)])

        client = AsyncMock()
        client.post = AsyncMock(side_effect=[version_resp, pin_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        # ipfs.test is not a resolvable public host; the address guard has its
        # own tests (test_health_url_guard.py), this one is about the stream.
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch("market_service.services.market_service._check_health_url", new=AsyncMock(return_value=None)),
        ):
            out = await svc.check_software_offer_health("ipfs_pin_1")
        assert not accessed, f"health check materialised the pin/ls body via .{accessed[0]}"
        assert out["pinned_count"] is not None
        assert out["pinned_count"] <= PIN_CAP, f"unbounded pin count {out['pinned_count']}, cap is {PIN_CAP}"


async def _aiter(lines):
    for line in lines:
        yield line
