"""Pin for #1873: governance mutating routes require the service API key.

The wallet signature on each body binds WHO may act; ``X-Api-Key`` binds
WHETHER the caller may reach the write surface — the same perimeter the
api-gateway applies one hop up. Read routes stay open. The authenticator
is flipped per-test because the suite conftest runs with
``GOVERNANCE_AUTH_ENABLED=false``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from governance_service.main import app, require_governance_api_key

WRITE_PATHS = [
    "/v1/governance/profiles",
    "/v1/governance/proposals",
    "/v1/governance/votes",
    "/v1/transactions",
    "/v1/governance/stake",
    "/v1/governance/delegate",
    "/v1/governance/proposals/p1/close",
    "/v1/governance/proposals/p1/execute",
    "/v1/governance/proposals/p1/propagate",
    "/v1/governance/proposals/p1/aggregate-votes",
    "/v1/governance/proposals/p1/execute-cross-chain",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _auth_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(require_governance_api_key, "auth_enabled", True)
    monkeypatch.setattr(require_governance_api_key, "expected_key", "gov-test-key")


def test_write_routes_reject_missing_key(client: TestClient) -> None:
    for path in WRITE_PATHS:
        assert client.post(path, json={}).status_code == 401, path


def test_write_routes_reject_wrong_key(client: TestClient) -> None:
    for path in WRITE_PATHS:
        resp = client.post(path, json={}, headers={"X-Api-Key": "nope"})
        assert resp.status_code == 401, path


def test_valid_key_reaches_handler(client: TestClient) -> None:
    """401 is the auth boundary; anything past it (400/403/500) means the
    key was accepted — handlers need no DB fixture for that distinction."""
    resp = client.post("/v1/governance/proposals", json={}, headers={"X-Api-Key": "gov-test-key"})
    assert resp.status_code != 401


def test_reads_stay_open(client: TestClient) -> None:
    assert client.get("/v1/governance/profiles").status_code != 401
    assert client.get("/v1/governance/proposals").status_code != 401
    assert client.get("/v1/governance/status").status_code == 200


def test_unconfigured_key_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """auth_enabled with no expected key must not silently open the surface."""
    monkeypatch.setattr(require_governance_api_key, "expected_key", None)
    resp = client.post("/v1/governance/proposals", json={}, headers={"X-Api-Key": "anything"})
    assert resp.status_code == 501
