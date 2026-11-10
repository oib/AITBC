"""Regression tests for the coder-C defect sweep (#1442, #1445, #1446, #1448, #1449).

* #1442 — MatchingService filtered on the canonical ``available`` spelling
  only, hiding ``open``-spelled offers and crashing ``OfferFSM.from_string``
  on alias words.
* #1445 — remaining unbounded reads (graph query, edge-advertise, plugins,
  job usage, matcher candidate sets).
* #1446 — ``sync_ratings_from_remote`` stored remote ratings without the
  1-5 range check the local submit path enforces.
* #1448 — rental/access secrets accepted as URL query parameters; the
  ``X-Access-Secret`` header is now preferred.
* #1449 — pin-confirm accepted negative ``size``; the public job view could
  500 on a malformed stored address.
"""

import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import (
    EdgeNodeAdvertisement,
    GraphEdge,
    GraphNode,
    MarketJob,
    Plugin,
)
from market_service.services.market_service import MarketService
from market_service.services.matching_service import MatchingService
from market_service.storage import engine, get_session_context


@asynccontextmanager
async def _prod_session():
    """Mirror storage.get_session: expire_on_commit=False, as production uses."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


from aitbc_shared import MarketOffer

pytestmark = pytest.mark.asyncio

PAGE_ENV = "MARKET_MAX_PAGE_SIZE"
SEEDED = 12
CAP = 5


@pytest.fixture
def capped(monkeypatch):
    monkeypatch.setenv(PAGE_ENV, str(CAP))
    return CAP


def _uid() -> str:
    return uuid4().hex[:8]


async def _seed_offers(session, statuses, n_per=1):
    u = _uid()
    for i, status in enumerate(statuses):
        session.add(
            MarketOffer(
                id=f"offer_c_{u}_{i}",
                provider="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                status=status,
                capacity=4,
                price_per_hour=Decimal("1.5"),
                region="eu",
            )
        )
    await session.commit()


# ---------------------------------------------------------------------------
# #1442 — alias-aware matching
# ---------------------------------------------------------------------------


async def test_find_best_match_sees_open_spelled_offer():
    """An offer stored as 'open' (a deployed spelling) must be matchable."""
    async with _prod_session() as session:
        await _seed_offers(session, ["open"])
        svc = MatchingService(session)
        match = await svc.find_best_match({})
        assert match is not None
        assert match["id"].startswith("offer_c_")


async def test_match_and_assign_reserves_open_spelled_offer():
    """match_and_assign must not crash OfferFSM on the 'open' spelling and
    must reserve the offer when the coordinator accepts the task."""
    async with _prod_session() as session:
        await _seed_offers(session, ["open"])
        svc = MatchingService(session)

        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json.return_value = {"task_id": "t1", "escrow_id": "e1", "job_id": "j1"}
        client = Mock()
        client.is_closed = False
        client.post = AsyncMock(return_value=resp)
        svc._http_client = client

        out = await svc.match_and_assign({})
        assert out["status"] == "matched"
        assert out["task_id"] == "t1"
        offer = await session.get(MarketOffer, out["offer_id"])
        assert offer is not None
        assert offer.status == "reserved"


async def test_find_best_match_statement_is_bounded():
    """The matcher must not materialise the whole offer table (#1445)."""
    async with _prod_session() as session:
        await _seed_offers(session, ["available"] * SEEDED)
        svc = MatchingService(session)
        statements: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "marketplaceoffer" in statement.lower():
                statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            await svc.find_best_match({})
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        assert statements, "expected a marketplaceoffer select"
        assert all("limit" in s.lower() for s in statements), f"unbounded matcher query: {statements}"


# ---------------------------------------------------------------------------
# #1445 — remaining bounded reads
# ---------------------------------------------------------------------------


async def test_query_graph_is_bounded(capped):
    async with get_session_context() as session:
        gid = f"g_{_uid()}"
        for i in range(SEEDED):
            session.add(GraphNode(graph_id=gid, node_type="entity", label=f"n{i}"))
            session.add(GraphEdge(graph_id=gid, source_node_id="a", target_node_id="b", edge_type="rel"))
        await session.commit()
        svc = MarketService(session)
        out = await svc.query_graph(gid)
        assert len(out["nodes"]) <= CAP
        assert len(out["edges"]) <= CAP


async def test_list_plugins_is_bounded(capped):
    async with get_session_context() as session:
        u = _uid()
        for i in range(SEEDED):
            session.add(Plugin(name=f"plug_{u}_{i}", status="approved"))
        await session.commit()
        svc = MarketService(session)
        plugins = await svc.list_plugins(status="approved")
        mine = [p for p in plugins if p["name"].startswith(f"plug_{u}_")]
        assert len(mine) <= CAP


async def test_market_job_usage_statement_is_bounded(capped):
    async with get_session_context() as session:
        u = _uid()
        for i in range(SEEDED):
            job = MarketJob(
                id=f"job_c_{u}_{i}",
                buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
                provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
                service_type="ipfs",
                state="RUNNING",
                offer_id=f"offer_c_{u}",
                payload={"size": 10},
            )
            session.add(job)
        await session.commit()
        svc = MarketService(session)
        statements: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "marketplace_jobs" in statement.lower():
                statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            await svc.get_market_job_usage("0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76", f"offer_c_{u}")
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        assert statements, "expected a marketjob select"
        assert all("limit" in s.lower() for s in statements), f"unbounded usage query: {statements}"


async def test_edge_advertise_route_is_bounded(capped):
    from fastapi.testclient import TestClient

    from market_service.main import app

    u = _uid()
    async with get_session_context() as session:
        for i in range(SEEDED):
            session.add(EdgeNodeAdvertisement(node_id=f"edge_c_{u}_{i}", status="active"))
        await session.commit()
    with TestClient(app) as client:
        body = client.get("/v1/market/edge-advertise").json()
        mine = [n for n in body["nodes"] if n["node_id"].startswith(f"edge_c_{u}_")]
        assert len(mine) <= CAP
        assert body["total"] <= CAP or len(body["nodes"]) <= CAP


# ---------------------------------------------------------------------------
# #1446 — remote rating range validation
# ---------------------------------------------------------------------------


def _remote_rating(u: str, i: int, rating) -> dict:
    return {
        "id": f"rr_{u}_{i}",
        "service_id": f"svc_c_{u}",
        "rating": rating,
        "reviewer_id": f"rev_{i}",
        "comment": "",
        "created_at": datetime.now(UTC).isoformat(),
        "source_node": "remote-test",
    }


async def test_sync_ratings_rejects_out_of_range():
    async with get_session_context() as session:
        u = _uid()
        svc = MarketService(session)
        out = await svc.sync_ratings_from_remote(
            [
                _remote_rating(u, 0, 4.5),
                _remote_rating(u, 1, 9.0),
                _remote_rating(u, 2, 0.0),
                _remote_rating(u, 3, "not-a-number"),
            ]
        )
        assert out["synced"] == 1
        assert out["failed"] == 3
        # The rejected rows must not have been stored.
        from market_service.domain.market import ServiceRating
        from sqlmodel import col, select

        stmt = select(ServiceRating).where(col(ServiceRating.service_id) == f"svc_c_{u}")
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 1
        assert rows[0].rating == 4.5


# ---------------------------------------------------------------------------
# #1448 — access secret via header
# ---------------------------------------------------------------------------


async def test_access_routes_accept_secret_header():
    """X-Access-Secret must authenticate; the query param still works."""
    from fastapi.testclient import TestClient

    from market_service.main import app

    with TestClient(app) as client:
        # No credential at all -> 401, not a 422 for the missing query param.
        r = client.get("/v1/market/access/somekey")
        assert r.status_code == 401
        r = client.get("/v1/market/ipfs/rental/somekey")
        assert r.status_code == 401
        # Header path reaches the service (unknown key -> 404 from the lookup).
        r = client.get("/v1/market/access/somekey", headers={"X-Access-Secret": "s3cret"})
        assert r.status_code == 404
        # Query-param path still works for existing callers.
        r = client.get("/v1/market/access/somekey", params={"access_secret": "s3cret"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# #1449 — pin-confirm size validation + public job view robustness
# ---------------------------------------------------------------------------


async def test_pin_confirm_rejects_negative_size(capped):
    from fastapi.testclient import TestClient

    from market_service.main import app

    async with get_session_context() as session:
        job_id = f"job_c_pin_{_uid()}"
        job = MarketJob(
            id=job_id,
            buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
            provider_address="0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
            service_type="ipfs",
            state="QUEUED",
            offer_id="offer_x",
            payload={},
        )
        session.add(job)
        await session.commit()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json={"size": -5})
        assert r.status_code == 400
        r = client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json={"size": "lots"})
        assert r.status_code == 400
        r = client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json={"size": 42})
        assert r.status_code == 200


async def test_signed_job_view_tolerates_malformed_stored_address(capped):
    """A job row whose stored address cannot canonicalize must still serve
    the (redacted or authorised) view instead of 500ing — the parties check
    skips unparseable stored addresses (#1449)."""
    import time

    from fastapi.testclient import TestClient

    from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings
    from market_service.main import app

    private_key = "0x" + "44" * 32
    provider = derive_ethereum_address(private_key)
    chain_id = settings.default_chain_id or resolve_chain_id()

    async with get_session_context() as session:
        job_id = f"job_c_bad_{_uid()}"
        job = MarketJob(
            id=job_id,
            buyer_address="not-an-address!!!",
            provider_address=provider,
            service_type="ipfs",
            state="QUEUED",
            offer_id="offer_x",
            payload={},
        )
        session.add(job)
        await session.commit()

    issued_at = int(time.time())
    signature = sign_transaction_data(
        jobs_request_message(provider, chain_id, issued_at, f"/v1/market/jobs/{job_id}"), private_key
    )
    with TestClient(app) as client:
        r = client.get(
            f"/v1/market/jobs/{job_id}",
            params={
                "signer_address": provider,
                "chain_id": chain_id,
                "issued_at": issued_at,
                "signature": signature,
            },
        )
        assert r.status_code == 200
