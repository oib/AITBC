"""#1710 pins: a quarantined chain.db must surface as a structured 503, not a
bare 500 or a stale 200, while liveness/readiness stay reachable.

Drill evidence (v12/v14 disk-full): ``/v1/height`` answered bare
``500 Internal server error`` and ``/health`` stayed ``ok`` while the node
had silently exited consensus. Now the request middleware refuses
chain-state endpoints with ``503 {"status": "quarantined", ...}`` and
``/health``/``/ready`` carry the quarantined chain ids (#1740/#1772 made the
quarantine visible across processes via the marker file).
"""

import pytest
from fastapi.testclient import TestClient

from aitbc_chain.app import create_app

QUARANTINED = "test-chain"


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def quarantined(monkeypatch):
    monkeypatch.setattr(
        "aitbc_chain.database.is_chain_db_quarantined",
        lambda cid="": cid == QUARANTINED,
    )


def test_chain_read_returns_structured_503_while_quarantined(client, quarantined):
    resp = client.get("/v1/height")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "quarantined"
    assert body["reason"] == "chain_db_quarantined"
    assert body["chain_id"] == QUARANTINED


def test_rpc_prefix_also_gated(client, quarantined):
    resp = client.get("/rpc/height")
    assert resp.status_code == 503
    assert resp.json()["status"] == "quarantined"


def test_health_stays_up_and_reports_quarantine(client, quarantined):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["quarantined_chains"] == [QUARANTINED]


def test_ready_fails_and_names_quarantined_chains(client, quarantined):
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["quarantined_chains"] == [QUARANTINED]


def test_metrics_exempt(client, quarantined):
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_gate_lifts_when_quarantine_clears(client, monkeypatch):
    # First request quarantined, then the marker clears — the next request
    # must not see the stale 503.
    monkeypatch.setattr(
        "aitbc_chain.database.is_chain_db_quarantined",
        lambda cid="": cid == QUARANTINED,
    )
    assert client.get("/v1/height").status_code == 503
    monkeypatch.setattr("aitbc_chain.database.is_chain_db_quarantined", lambda cid="": False)
    resp = client.get("/v1/height")
    assert resp.status_code != 503 or resp.json().get("status") != "quarantined"
