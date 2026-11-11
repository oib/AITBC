"""#1810: sell_gpu relist writes are compare-and-swap."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aitbc.auth import create_access_token
from sqlmodel import Session, col, update

from coordinator_api.contexts.market.domain.gpu_market import GPUBooking, GPURegistry
from coordinator_api.main import app
from coordinator_api.storage import get_session


@pytest.fixture
def per_request_client(db_engine):
    from collections.abc import Generator

    from fastapi.testclient import TestClient

    def override_get_session() -> Generator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def miner_token() -> str:
    return create_access_token("gpu_miner", "miner")


def _sell_body(gpu_id: str, price: str = "0.07") -> dict:
    return {"seller_id": "gpu_miner", "gpu_id": gpu_id, "listing_price": price}


def _assert_race_row(db_engine, gpu_id: str, outcomes: dict[str, int]) -> None:
    with Session(db_engine) as session:
        row = session.get(GPURegistry, gpu_id)
        assert row is not None
        if outcomes["book_ok"] == 1:
            assert row.status == "booked"
        elif outcomes["sell_ok"] == 1:
            assert row.status == "available"
            assert row.price_per_hour == Decimal("0.12")
        else:
            assert outcomes["sell_409"] == 1 or outcomes["book_409"] == 1


@pytest.mark.unit
def test_sell_booked_gpu_returns_409(per_request_client, miner_token, db_session) -> None:
    gpu = GPURegistry(
        id="gpu_sell_booked",
        miner_id="gpu_miner",
        model="Test",
        memory_gb=8,
        cuda_version="12",
        region="localhost",
        price_per_hour=Decimal("0.05"),
        status="booked",
    )
    db_session.add(gpu)
    db_session.add(
        GPUBooking(
            gpu_id=gpu.id,
            client_id="client1",
            duration_hours=1.0,
            total_cost=Decimal("1"),
            start_time=datetime.now(UTC),
            status="active",
        )
    )
    db_session.commit()

    resp = per_request_client.post(
        "/v1/market/gpu/sell",
        headers={"Authorization": f"Bearer {miner_token}"},
        json=_sell_body(gpu.id),
    )
    assert resp.status_code == 409
    row = db_session.get(GPURegistry, gpu.id)
    assert row is not None and row.status == "booked"


@pytest.mark.unit
def test_sell_offline_relists_available(per_request_client, miner_token, db_session) -> None:
    gpu = GPURegistry(
        id="gpu_sell_offline",
        miner_id="gpu_miner",
        model="Test",
        memory_gb=8,
        cuda_version="12",
        region="localhost",
        price_per_hour=Decimal("0.05"),
        status="offline",
    )
    db_session.add(gpu)
    db_session.commit()

    resp = per_request_client.post(
        "/v1/market/gpu/sell",
        headers={"Authorization": f"Bearer {miner_token}"},
        json=_sell_body(gpu.id, "0.09"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "listed"
    db_session.expire_all()
    row = db_session.get(GPURegistry, gpu.id)
    assert row is not None
    assert row.status == "available"
    assert row.price_per_hour == Decimal("0.09")


@pytest.mark.unit
def test_blind_status_write_cannot_regress_booked(per_request_client, miner_token, db_session) -> None:
    """A stale sell path must not overwrite a row that flipped to booked."""
    gpu = GPURegistry(
        id="gpu_sell_regress",
        miner_id="gpu_miner",
        model="Test",
        memory_gb=8,
        cuda_version="12",
        region="localhost",
        price_per_hour=Decimal("0.05"),
        status="available",
    )
    db_session.add(gpu)
    db_session.commit()

    db_session.execute(
        update(GPURegistry)
        .where(col(GPURegistry.id) == gpu.id)
        .values(status="booked")
        .execution_options(synchronize_session=False)
    )
    db_session.commit()

    resp = per_request_client.post(
        "/v1/market/gpu/sell",
        headers={"Authorization": f"Bearer {miner_token}"},
        json=_sell_body(gpu.id, "0.11"),
    )
    assert resp.status_code == 409
    row = db_session.get(GPURegistry, gpu.id)
    assert row is not None and row.status == "booked"
    assert row.price_per_hour == Decimal("0.05")


@pytest.mark.unit
def test_concurrent_book_and_sell_exactly_one_wins(db_engine, miner_token) -> None:
    if db_engine.dialect.name != "postgresql":
        pytest.skip("sqlite serializes poorly — CAS overlap pin runs on postgres")
    from collections.abc import Generator

    from fastapi.testclient import TestClient

    from coordinator_api.contexts.market.routers.market_gpu import get_pricing_engine

    with Session(db_engine) as session:
        gpu = GPURegistry(
            id="gpu_sell_race",
            miner_id="gpu_miner",
            model="Test",
            memory_gb=8,
            cuda_version="12",
            region="localhost",
            price_per_hour=Decimal("0.05"),
            status="available",
        )
        session.add(gpu)
        session.commit()
        gpu_id = gpu.id

    engine = type("FakeEngine", (), {"calculate_dynamic_price": AsyncMock(side_effect=Exception("skip"))})()
    app.dependency_overrides[get_pricing_engine] = lambda: engine

    def override_get_session() -> Generator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client_token = create_access_token("client1", "client")

    outcomes: dict[str, int] = {"sell_ok": 0, "sell_409": 0, "book_ok": 0, "book_409": 0}
    barrier = threading.Barrier(2)

    def sell() -> None:
        with TestClient(app) as client:
            barrier.wait(timeout=5)
            resp = client.post(
                "/v1/market/gpu/sell",
                headers={"Authorization": f"Bearer {miner_token}"},
                json=_sell_body(gpu_id, "0.12"),
            )
            if resp.status_code == 200:
                outcomes["sell_ok"] += 1
            elif resp.status_code == 409:
                outcomes["sell_409"] += 1
            else:
                pytest.fail(f"unexpected sell status {resp.status_code}: {resp.text}")

    def book() -> None:
        with TestClient(app) as client:
            barrier.wait(timeout=5)
            resp = client.post(
                f"/v1/market/gpu/{gpu_id}/book",
                headers={"Authorization": f"Bearer {client_token}"},
                json={"duration_hours": 1, "job_id": None},
            )
            if resp.status_code == 201:
                outcomes["book_ok"] += 1
            elif resp.status_code == 409:
                outcomes["book_409"] += 1
            else:
                pytest.fail(f"unexpected book status {resp.status_code}: {resp.text}")

    t_sell = threading.Thread(target=sell)
    t_book = threading.Thread(target=book)
    t_sell.start()
    t_book.start()
    t_sell.join(timeout=10)
    t_book.join(timeout=10)

    app.dependency_overrides.pop(get_pricing_engine, None)
    app.dependency_overrides.pop(get_session, None)

    assert outcomes["sell_ok"] + outcomes["sell_409"] == 1
    assert outcomes["book_ok"] + outcomes["book_409"] == 1
    assert not (outcomes["sell_ok"] == 1 and outcomes["book_ok"] == 1)
    _assert_race_row(db_engine, gpu_id, outcomes)
