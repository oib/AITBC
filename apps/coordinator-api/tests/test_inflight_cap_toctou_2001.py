"""#2001 INFLIGHT-CAP-TOCTOU-1 — per-client in-flight cap must be atomic.

Pins: create_job locks the client user row (FOR UPDATE on postgres,
BEGIN IMMEDIATE on sqlite) before counting non-terminal jobs, and concurrent
submits cannot overshoot the cap.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, select

from coordinator_api.contexts.infrastructure.domain.user import User
from coordinator_api.contexts.infrastructure.services import jobs as jobs_module
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.schemas import JobCreate


def _job_req(**kwargs) -> JobCreate:
    return JobCreate(payload={"type": "inference", "prompt": "x"}, **kwargs)


@pytest.mark.unit
def test_inflight_cap_select_compiles_with_for_update() -> None:
    stmt = select(User).where(User.id == "client1").with_for_update()
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.mark.unit
def test_create_job_issues_for_update_when_enforcing_cap(db_session, monkeypatch) -> None:
    """Mutation pin: enforce_inflight_cap=True must lock the client row."""
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 50)
    original_exec = Session.exec
    lock_sql: list[str] = []

    def tracing_exec(self, statement, *args, **kwargs):
        if hasattr(statement, "compile"):
            lock_sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return original_exec(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "exec", tracing_exec)
    JobService(db_session).create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    assert any("FOR UPDATE" in sql for sql in lock_sql), lock_sql


@pytest.mark.unit
def test_create_job_issues_begin_immediate_on_sqlite(db_session, db_engine, monkeypatch) -> None:
    """Mutation pin: sqlite takes BEGIN IMMEDIATE before cap check (#2001)."""
    if db_engine.dialect.name != "sqlite":
        pytest.skip("BEGIN IMMEDIATE pin is sqlite-specific")
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 50)
    original_exec_driver = db_engine.dialect.do_execute

    calls: list[str] = []

    def tracing_execute(cursor, statement, parameters, context):
        if isinstance(statement, str):
            calls.append(statement.strip().upper())
        else:
            calls.append(str(statement).strip().upper())
        return original_exec_driver(cursor, statement, parameters, context)

    monkeypatch.setattr(db_engine.dialect, "do_execute", tracing_execute)
    JobService(db_session).create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    assert any("BEGIN IMMEDIATE" in c for c in calls), calls


@pytest.mark.unit
def test_concurrent_create_job_cannot_overshoot_cap(db_engine, monkeypatch) -> None:
    """Two simultaneous create_job calls with cap=1: exactly one wins."""
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 1)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def submit() -> None:
        with Session(db_engine) as session:
            barrier.wait(timeout=10)
            try:
                JobService(session).create_job(
                    client_id="client1",
                    req=_job_req(),
                    enforce_inflight_cap=True,
                )
                results.append("ok")
            except HTTPException as exc:
                results.append(f"http-{exc.status_code}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(submit), pool.submit(submit)]
        for fut in futs:
            fut.result(timeout=30)

    assert results.count("ok") == 1
    assert results.count("http-429") == 1
