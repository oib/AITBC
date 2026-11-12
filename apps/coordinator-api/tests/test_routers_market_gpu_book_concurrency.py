"""#1802: book_gpu must lock the GPU row (FOR UPDATE) like buy_gpu.

Pins: the booking path compiles and executes a row lock before the
availability check, and overlapping book attempts cannot leave two active
holds on one GPU (postgres; sqlite row locks are exercised when CI uses PG).
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aitbc.auth import create_access_token
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, select

from coordinator_api.contexts.market.domain.gpu_market import GPUBooking, GPURegistry
from coordinator_api.contexts.market.routers.market_gpu import get_pricing_engine
from coordinator_api.main import app
from coordinator_api.storage import get_session


@pytest.fixture
def per_request_client(db_engine):
    """TestClient that opens a fresh SQLModel session per request (like prod)."""
    from fastapi.testclient import TestClient

    def override_get_session() -> Generator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def client_token() -> str:
    return create_access_token("client1", "client")


@pytest.fixture
def miner_token() -> str:
    return create_access_token("gpu_miner", "miner")


@pytest.fixture
def available_gpu(client, miner_token, db_session) -> str:
    """Seed an available GPU via the register route."""
    payload = {
        "gpu": {
            "name": "NVIDIA Test",
            "memory_gb": 16,
            "compute_capability": "8.9",
            "price_per_hour": "0.05",
            "resource_id": "node2-test",
        }
    }
    resp = client.post(
        "/v1/market/gpu/register",
        headers={"Authorization": f"Bearer {miner_token}"},
        json=payload,
    )
    assert resp.status_code == 200
    return str(resp.json()["gpu_id"])


@pytest.fixture
def pricing_engine_override():
    engine = type("FakeEngine", (), {"calculate_dynamic_price": AsyncMock(side_effect=RuntimeError("skip"))})()
    app.dependency_overrides[get_pricing_engine] = lambda: engine
    yield engine
    app.dependency_overrides.pop(get_pricing_engine, None)


def _seed_gpu(db_session: Session) -> str:
    gpu = GPURegistry(
        id="gpu_conc_1",
        name="Test GPU",
        model="NVIDIA Test",
        memory_gb=16,
        compute_capability="8.9",
        price_per_hour=Decimal("0.05"),
        status="available",
        miner_id="gpu_miner",
        region="localhost",
        resource_id="node2-test",
    )
    db_session.add(gpu)
    db_session.commit()
    return gpu.id


@pytest.mark.unit
def test_book_gpu_select_compiles_with_for_update() -> None:
    stmt = select(GPURegistry).where(GPURegistry.id == "gpu_x").with_for_update()
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.mark.unit
def test_book_gpu_issues_for_update_exec_during_book(
    client,
    client_token,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
) -> None:
    """Mutation pin: a booking SELECT must carry FOR UPDATE (postgres dialect)."""
    original_exec = Session.exec
    lock_sql: list[str] = []

    def tracing_exec(self, statement, *args, **kwargs):
        if hasattr(statement, "compile"):
            lock_sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return original_exec(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "exec", tracing_exec)
    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"duration_hours": 1},
    )
    assert resp.status_code == 201, resp.text
    assert any("FOR UPDATE" in sql for sql in lock_sql), lock_sql


@pytest.mark.unit
def test_overlapping_book_requests_leave_one_active_hold(
    per_request_client,
    db_session,
    pricing_engine_override,
) -> None:
    """Serialized overlap: the second book attempt must conflict."""
    gpu_id = _seed_gpu(db_session)
    token = create_access_token("client1", "client")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"duration_hours": 1}
    first = per_request_client.post(f"/v1/market/gpu/{gpu_id}/book", headers=headers, json=body)
    second = per_request_client.post(f"/v1/market/gpu/{gpu_id}/book", headers=headers, json=body)
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.unit
def test_concurrent_book_gpu_one_active_hold(
    per_request_client,
    db_engine,
    db_session,
    pricing_engine_override,
) -> None:
    """Two simultaneous book POSTs; row locks serialize on postgres."""
    if db_engine.dialect.name != "postgresql":
        pytest.skip("sqlite ignores FOR UPDATE — concurrent oversell pin runs on postgres")

    gpu_id = _seed_gpu(db_session)
    token_a = create_access_token("client1", "client")
    token_b = create_access_token("client2", "client")
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def book(label: str, token: str) -> None:
        barrier.wait(timeout=10)
        resp = per_request_client.post(
            f"/v1/market/gpu/{gpu_id}/book",
            headers={"Authorization": f"Bearer {token}"},
            json={"duration_hours": 1},
        )
        results[label] = resp.status_code

    threads = [threading.Thread(target=book, args=(lbl, tok)) for lbl, tok in (("a", token_a), ("b", token_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert set(results.values()) == {201, 409}, results
    with Session(db_engine) as check:
        active = check.exec(select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")).all()
    assert len(active) == 1, f"expected one active booking, got {len(active)}"


@pytest.mark.unit
def test_cas_book_gpu_refuses_second_transition(db_session) -> None:
    """#1836: the available->booked CAS is the arbiter — a row already booked
    must lose the predicate even when the caller's snapshot is stale."""
    from coordinator_api.contexts.market.routers.market_gpu import _cas_book_gpu

    gpu_id = _seed_gpu(db_session)
    assert _cas_book_gpu(db_session, gpu_id) is True
    db_session.commit()
    db_session.expire_all()
    assert _cas_book_gpu(db_session, gpu_id) is False
    db_session.rollback()


@pytest.mark.unit
def test_book_gpu_issues_status_guarded_update(
    client,
    client_token,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
) -> None:
    """#1836: the book path must run a predicate-guarded UPDATE on the GPU row
    (status='available' in WHERE) — FOR UPDATE alone is a no-op on sqlite."""
    original_execute = Session.execute
    update_sql: list[str] = []

    def tracing_execute(self, statement, *args, **kwargs):
        if hasattr(statement, "compile"):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if "UPDATE" in sql.upper() and "gpu_registry" in sql:
                update_sql.append(sql)
        return original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", tracing_execute)
    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"duration_hours": 1},
    )
    assert resp.status_code == 201, resp.text
    assert any("gpu_registry.status" in sql for sql in update_sql), update_sql
