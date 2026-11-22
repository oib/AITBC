"""AUDIT-WALLET-DEPOSITS-FILTER-1 (#2549): GET /v1/exchange/deposits (and its
/v1/bridge twin) applied the status filter only for 'pending' — every other
value, including unknown ones, returned all deposits. Any valid
_ETH_DEPOSIT_STATUSES value now filters via get_deposits_by_status; unknown
values are refused with 422.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wallet_app.bridge.bridge_db import (
    get_deposits_by_status,
    init_db,
    insert_deposit,
    update_deposit_status,
)


@pytest.fixture
def bridge_db(tmp_path: Path):
    db_path = tmp_path / "bridge.db"
    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        yield str(db_path)


def _seed(bridge_db):
    """One deposit per lifecycle status."""
    ids = {}
    for i, status in enumerate(("pending", "verified", "completed", "failed", "rejected")):
        dep_id = insert_deposit(
            tx_hash=f"0x{i:064x}",
            from_address="0x9999999999999999999999999999999999999999",
            amount_eth=Decimal("0.01"),
            amount_ait=Decimal("100"),
        )
        if status != "pending":
            assert update_deposit_status(dep_id, status)
        ids[status] = dep_id
    return ids


@pytest.fixture
def exchange_client(bridge_db):
    from wallet_app.bridge.bridge_routes import exchange_router

    app = FastAPI()
    app.include_router(exchange_router)
    return TestClient(app)


@pytest.fixture
def bridge_client(bridge_db):
    from wallet_app.bridge.bridge_routes_deposits import bridge_router

    app = FastAPI()
    app.include_router(bridge_router)
    return TestClient(app)


def test_exchange_deposits_status_filter(exchange_client, bridge_db):
    _seed(bridge_db)
    resp = exchange_client.get("/v1/exchange/deposits", params={"status": "verified"})
    assert resp.status_code == 200
    deposits = resp.json()["deposits"]
    assert len(deposits) == 1
    assert deposits[0]["status"] == "verified"


def test_exchange_deposits_completed_filter(exchange_client, bridge_db):
    _seed(bridge_db)
    resp = exchange_client.get("/v1/exchange/deposits", params={"status": "completed"})
    assert resp.status_code == 200
    assert [d["status"] for d in resp.json()["deposits"]] == ["completed"]


def test_exchange_deposits_unknown_status_422(exchange_client, bridge_db):
    _seed(bridge_db)
    resp = exchange_client.get("/v1/exchange/deposits", params={"status": "bogus"})
    assert resp.status_code == 422
    assert "unknown deposit status" in resp.json()["detail"]


def test_exchange_deposits_no_status_returns_all(exchange_client, bridge_db):
    _seed(bridge_db)
    resp = exchange_client.get("/v1/exchange/deposits")
    assert resp.status_code == 200
    assert len(resp.json()["deposits"]) == 5


def test_bridge_deposits_status_filter(bridge_client, bridge_db):
    _seed(bridge_db)
    resp = bridge_client.get("/v1/bridge/deposits", params={"status": "failed"})
    assert resp.status_code == 200
    deposits = resp.json()["deposits"]
    assert len(deposits) == 1
    assert deposits[0]["status"] == "failed"


def test_bridge_deposits_unknown_status_422(bridge_client, bridge_db):
    _seed(bridge_db)
    resp = bridge_client.get("/v1/bridge/deposits", params={"status": "bogus"})
    assert resp.status_code == 422


def test_get_deposits_by_status_db(bridge_db):
    ids = _seed(bridge_db)
    rows = get_deposits_by_status("pending")
    assert [r["id"] for r in rows] == [ids["pending"]]
    assert get_deposits_by_status("exchange_prepay") == []
