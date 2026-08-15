"""V23-17: the sync endpoint must not report work it did not do.

``sync_database`` had no sync behind it. It set ``last_sync_at`` to now, advanced
``records_synced`` by a literal 100 and returned ``{"success": True}`` — and
committed all of it. Anything reading ``last_sync_at`` to decide whether a replica
is current was told the sync happened, and the counter climbing by 100 a call made
it look like progress.

The tests that matter here are the ones asserting nothing is *written*. A response
can be corrected later; a fabricated ``last_sync_at`` in the database outlives the
call that made it.
"""

from __future__ import annotations

import importlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from aitbc_edge.services import database_service as svc_module
from aitbc_edge.services.database_service import DatabaseService, SyncNotImplementedError

EXISTING_SYNC_AT = datetime(2026, 1, 1, tzinfo=UTC)
EXISTING_RECORDS = 4_242


class FakeDb:
    def __init__(self):
        self.database_id = "db_1"
        self.sync_status = "idle"
        self.last_sync_at = EXISTING_SYNC_AT
        self.records_synced = EXISTING_RECORDS
        self.updated_at = EXISTING_SYNC_AT


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeSession:
    def __init__(self, row):
        self._row = row
        self.commits = 0

    async def execute(self, stmt):
        return _Result(self._row)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def db():
    return FakeDb()


@pytest.fixture
def session(db, monkeypatch):
    fake = FakeSession(db)

    @asynccontextmanager
    async def _get_session():
        yield fake

    monkeypatch.setattr(svc_module, "get_session", _get_session)
    return fake


class TestRefusesByDefault:
    async def test_sync_raises_rather_than_reporting_success(self, session, monkeypatch):
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", False)

        with pytest.raises(SyncNotImplementedError, match="not implemented"):
            await DatabaseService().sync_database("db_1")

    async def test_nothing_is_written(self, db, session, monkeypatch):
        """The core of V23-17: the fiction was persisted, not merely returned."""
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", False)

        with pytest.raises(SyncNotImplementedError):
            await DatabaseService().sync_database("db_1")

        assert db.last_sync_at == EXISTING_SYNC_AT
        assert db.records_synced == EXISTING_RECORDS
        assert db.updated_at == EXISTING_SYNC_AT
        assert session.commits == 0

    async def test_missing_database_still_reports_not_found(self, monkeypatch):
        """A more specific answer beats a blanket 501."""
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", False)
        fake = FakeSession(None)

        @asynccontextmanager
        async def _get_session():
            yield fake

        monkeypatch.setattr(svc_module, "get_session", _get_session)

        result = await DatabaseService().sync_database("missing")
        assert result["success"] is False
        assert "not found" in result["message"]


class TestSimulationModeIsLabelledAndStillWritesNothing:
    async def test_response_is_marked_simulated(self, session, monkeypatch):
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", True)

        result = await DatabaseService().sync_database("db_1")

        assert result["simulated"] is True
        assert "no data was transferred" in result["message"]
        assert "not implemented" in result["notice"]

    async def test_simulation_does_not_advance_the_counter(self, db, session, monkeypatch):
        """The flag re-enables a response, not the writes. 100 must not appear anywhere."""
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", True)

        result = await DatabaseService().sync_database("db_1")

        assert db.records_synced == EXISTING_RECORDS
        assert result["records_synced"] == EXISTING_RECORDS
        assert db.last_sync_at == EXISTING_SYNC_AT
        assert result["last_sync_at"] == EXISTING_SYNC_AT.isoformat()
        assert session.commits == 0

    async def test_repeated_calls_do_not_accumulate(self, db, session, monkeypatch):
        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", True)
        service = DatabaseService()

        for _ in range(5):
            await service.sync_database("db_1")

        assert db.records_synced == EXISTING_RECORDS


class TestFlagDefault:
    def test_simulation_is_off_unless_opted_into(self, monkeypatch):
        monkeypatch.delenv("EDGE_ALLOW_SIMULATED_SYNC", raising=False)
        reloaded = importlib.reload(svc_module)
        try:
            assert reloaded.ALLOW_SIMULATED_SYNC is False
        finally:
            importlib.reload(svc_module)

    def test_flag_reads_the_env_var(self, monkeypatch):
        monkeypatch.setenv("EDGE_ALLOW_SIMULATED_SYNC", "true")
        reloaded = importlib.reload(svc_module)
        try:
            assert reloaded.ALLOW_SIMULATED_SYNC is True
        finally:
            monkeypatch.delenv("EDGE_ALLOW_SIMULATED_SYNC", raising=False)
            importlib.reload(svc_module)


class TestRouteReturns501:
    def test_sync_route_answers_501_not_200(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from aitbc_edge.routers import database as database_router

        monkeypatch.setattr(svc_module, "ALLOW_SIMULATED_SYNC", False)

        fake = FakeSession(FakeDb())

        @asynccontextmanager
        async def _get_session():
            yield fake

        monkeypatch.setattr(svc_module, "get_session", _get_session)

        app = FastAPI()
        app.include_router(database_router.router)
        client = TestClient(app)

        response = client.post("/db_1/sync")

        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"]
