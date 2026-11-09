"""Router tests for /v1/multi-modal-rl/* (#1289 round 9 batch 3).

Thin proxy to the AI service (httpx) — no AI service runs in tests, so
the contract under test is the soft-fail shape ({"error": ...} dicts,
never 5xx) plus the health endpoint and matrix floor ANY.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, get_auth_level

BASE = "/v1/multi-modal-rl"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


class TestMultiModalRl:
    def test_matrix_any(self) -> None:
        assert get_auth_level("/v1/multi-modal-rl/jobs") == AuthLevel.ANY

    def test_submit_job_soft_fail(self, client: TestClient) -> None:
        # no AI service in tests -> connection failure -> {"error": ...} 200
        resp = client.post(f"{BASE}/jobs", json={"task": "x"}, headers=_headers())
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_get_job_soft_fail(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jobs/job_ghost", headers=_headers())
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_list_jobs(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jobs", headers=_headers())
        assert resp.status_code == 200

    def test_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
