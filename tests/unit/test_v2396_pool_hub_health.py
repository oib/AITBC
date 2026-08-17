"""V23-96 — Pool Hub's health endpoint could not be reached, and lied when it could.

Three defects sat in one 54-line handler:

1. ``/health`` answered 404.  The router declared ``prefix="/v1"`` while ``main.py``
   included it with no prefix — the one combination that moves the route and leaves
   nothing at the root.  Every other router in this app declares a resource prefix and
   lets ``main.py`` add ``/v1``; every other service in the repo serves ``/health``
   unversioned.
2. A database or Redis outage produced a 500 with no body.  The handler caught
   ``SELECT 1`` failing, recorded the error — and then ran a second query on the same
   dead session, unguarded, throwing away the diagnosis it had just made.
3. A degraded service still answered HTTP 200, so anything reading the status code
   rather than parsing the body saw a healthy node.

These tests exercise the real router and the real ``MinerRepository`` against stub
session/Redis objects, so no database is required.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.sql.elements import TextClause

from poolhub.app.deps import db_session_dep, redis_dep
from poolhub.app.routers import health as health_module
from poolhub.app.routers import health_router


class StubResult:
    """The shape ``list_active_miners`` consumes: ``result.all()``."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class StubSession:
    """An AsyncSession stand-in that can fail the ping, the miner query, or neither.

    ``SELECT 1`` arrives as a ``TextClause`` and the miner listing as a ``Select``,
    so the two can be failed independently — which is what separates "the database is
    down" from "the miner query is broken".
    """

    def __init__(self, *, ping_fails: bool = False, query_fails: bool = False) -> None:
        self.ping_fails = ping_fails
        self.query_fails = query_fails

    async def execute(self, statement: Any) -> StubResult:
        if isinstance(statement, TextClause):
            if self.ping_fails:
                raise RuntimeError("connection refused")
            return StubResult([])
        if self.query_fails or self.ping_fails:
            raise RuntimeError('relation "miners" does not exist')
        return StubResult([])


class StubRedis:
    def __init__(self, *, ping_fails: bool = False) -> None:
        self.ping_fails = ping_fails

    async def ping(self) -> bool:
        if self.ping_fails:
            raise RuntimeError("redis unreachable")
        return True


def _client(session: StubSession, redis: StubRedis) -> TestClient:
    """A bare app including the health router exactly as ``main.py`` line 50 does."""
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[db_session_dep] = lambda: session
    app.dependency_overrides[redis_dep] = lambda: redis
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def healthy() -> TestClient:
    return _client(StubSession(), StubRedis())


# --- 1. the route exists where the include puts it ------------------------------------


def test_health_is_served_at_the_root(healthy: TestClient) -> None:
    """The defect: /health answered 404 because the router carried the /v1 prefix."""
    response = healthy.get("/health")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_the_previously_live_v1_path_still_answers(healthy: TestClient) -> None:
    """/v1/health is what the deployed service has been serving; it must keep working."""
    response = healthy.get("/v1/health")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_the_health_router_declares_no_version_prefix() -> None:
    """Guards the inversion itself, not just its symptom.

    ``main.py`` includes this router with no prefix.  A ``/v1`` prefix back on the
    router moves /health again, and the 404 returns.
    """
    assert health_router.prefix == ""


def test_the_real_app_exposes_both_health_paths() -> None:
    """The bare app above mirrors main.py; this checks main.py itself."""
    from poolhub.app.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/health" in paths
    assert "/v1/health" in paths


def test_only_the_root_path_is_advertised_in_the_schema() -> None:
    """/v1/health is a compatibility alias, so it stays out of the published schema."""
    from poolhub.app.main import app

    documented = set(app.openapi()["paths"])
    assert "/health" in documented
    assert "/v1/health" not in documented


# --- 2. an outage is described, not raised ---------------------------------------------


def test_a_database_outage_is_reported_rather_than_raised() -> None:
    """The defect: the second query ran on the dead session and the handler 500'd."""
    response = _client(StubSession(ping_fails=True), StubRedis()).get("/health")

    assert response.status_code != 500, "the outage this endpoint exists to report crashed it"
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] is False
    assert body["db_error"]


def test_a_redis_outage_is_reported_rather_than_raised() -> None:
    response = _client(StubSession(), StubRedis(ping_fails=True)).get("/health")

    assert response.status_code != 500
    body = response.json()
    assert body["status"] == "degraded"
    assert body["redis"] is False
    assert body["redis_error"]


def test_a_broken_miner_query_alone_still_degrades() -> None:
    """Both pings pass, but the listing fails — previously a bare 500."""
    response = _client(StubSession(query_fails=True), StubRedis()).get("/health")

    assert response.status_code != 500
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] is True
    assert body["redis"] is True
    assert body["miners_error"]


def test_an_unknown_miner_count_is_null_not_zero() -> None:
    """0 would read as "no miners are online", which is a different claim."""
    body = _client(StubSession(ping_fails=True), StubRedis()).get("/health").json()

    assert body["miners_online"] is None


def test_the_gauge_is_not_zeroed_when_the_count_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting the Prometheus series to 0 on failure fakes a miner exodus."""
    calls: list[float] = []

    class SpyGauge:
        def set(self, value: float) -> None:
            calls.append(value)

    monkeypatch.setattr(health_module, "miners_online_gauge", SpyGauge())
    _client(StubSession(ping_fails=True), StubRedis()).get("/health")

    assert calls == []


def test_the_gauge_is_set_when_the_count_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []

    class SpyGauge:
        def set(self, value: float) -> None:
            calls.append(value)

    monkeypatch.setattr(health_module, "miners_online_gauge", SpyGauge())
    _client(StubSession(), StubRedis()).get("/health")

    assert calls == [0]


# --- 3. the status code agrees with the body -------------------------------------------


def test_a_healthy_pool_hub_answers_200(healthy: TestClient) -> None:
    assert healthy.get("/health").status_code == 200


@pytest.mark.parametrize(
    "session,redis",
    [
        (StubSession(ping_fails=True), StubRedis()),
        (StubSession(), StubRedis(ping_fails=True)),
        (StubSession(query_fails=True), StubRedis()),
    ],
    ids=["db-down", "redis-down", "miner-query-broken"],
)
def test_a_degraded_pool_hub_answers_503(session: StubSession, redis: StubRedis) -> None:
    """The defect: 200 alongside "status": "degraded" — invisible to any load balancer."""
    response = _client(session, redis).get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


# --- the port the tooling aims at ------------------------------------------------------


def test_the_settings_default_port_is_the_one_the_unit_binds() -> None:
    """bind_port defaulted to 8203, which is coordinator-api's port."""
    from poolhub.settings import Settings

    assert Settings().bind_port == 8210
