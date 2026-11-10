"""Auth coverage for the AI engine data endpoints (#1474).

/api/ai/trade was the only route behind verify_auth; analyze, predict and
dashboard served the same class of output with no credential. These tests
pin the dependency on all four.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import ai_service
from ai_service import app


@pytest.fixture
def auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force REQUIRE_AUTH on with a known key (conftest sets it false)."""
    monkeypatch.setattr(ai_service, "REQUIRE_AUTH", True)
    monkeypatch.setattr(ai_service, "API_KEY", "test-key")


@pytest.mark.integration
def test_analyze_requires_auth(auth_required: None) -> None:
    client = TestClient(app)
    body = {"symbol": "AITBC/ETH", "analysis_type": "full"}
    assert client.post("/api/ai/analyze", json=body).status_code == 401
    ok = client.post("/api/ai/analyze", json=body, headers={"Authorization": "Bearer test-key"})
    assert ok.status_code == 200


@pytest.mark.integration
def test_predict_requires_auth(auth_required: None) -> None:
    client = TestClient(app)
    assert client.get("/api/ai/predict/AITBC-ETH").status_code == 401
    ok = client.get("/api/ai/predict/AITBC-ETH", headers={"Authorization": "Bearer test-key"})
    assert ok.status_code == 200


@pytest.mark.integration
def test_dashboard_requires_auth(auth_required: None) -> None:
    client = TestClient(app)
    assert client.get("/api/ai/dashboard").status_code == 401
    ok = client.get("/api/ai/dashboard", headers={"Authorization": "Bearer test-key"})
    assert ok.status_code == 200


@pytest.mark.integration
def test_status_and_health_stay_public(auth_required: None) -> None:
    """Operational probes carry no analysis data and must not demand a key."""
    client = TestClient(app)
    assert client.get("/api/ai/status").status_code == 200
    assert client.get("/api/health").status_code == 200
