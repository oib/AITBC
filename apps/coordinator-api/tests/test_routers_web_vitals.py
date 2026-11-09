"""Router tests for /v1/web-vitals/* (#1289 round 9 batch 3).

Metric ingestion endpoint — logs and acknowledges; matrix floor ANY.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, get_auth_level

BASE = "/v1/web-vitals"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


def _metric(**overrides) -> dict:
    body = {
        "name": "LCP",
        "value": 1234.5,
        "id": "v1-123",
        "url": "https://hub.example/",
        "timestamp": "2026-11-09T00:00:00Z",
        "entries": [{"name": "LCP", "startTime": 100.0, "duration": 50.0}],
    }
    body.update(overrides)
    return body


class TestWebVitals:
    def test_matrix_any(self) -> None:
        assert get_auth_level("/v1/web-vitals") == AuthLevel.ANY

    def test_collect_ack(self, client: TestClient) -> None:
        resp = client.post(BASE, json=_metric(), headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "received"
        assert body["metric"] == "LCP"
        assert body["value"] == 1234.5

    def test_minimal_metric(self, client: TestClient) -> None:
        resp = client.post(BASE, json={"name": "CLS", "value": 0.01, "id": "v2"}, headers=_headers())
        assert resp.status_code == 200

    def test_validation_missing_fields(self, client: TestClient) -> None:
        assert client.post(BASE, json={"name": "LCP"}, headers=_headers()).status_code == 422
        assert client.post(BASE, json={}, headers=_headers()).status_code == 422

    def test_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
