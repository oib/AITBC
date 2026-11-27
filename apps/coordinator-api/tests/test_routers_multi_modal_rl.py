"""Router tests for /v1/multi-modal-rl/* (#1289 round 9 batch 3).

Thin proxy to the AI service (httpx) — no AI service runs in tests, so
the contract under test is the #2712 failure shape: upstream connection
failures answer 502 and local errors 500 — never a success-shaped
{"error": ...} payload — plus the health endpoint and matrix floor ANY.
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

    def test_submit_job_upstream_down_is_502(self, client: TestClient) -> None:
        # no AI service in tests -> connection failure -> 502, not a 200 {"error"}
        resp = client.post(f"{BASE}/jobs", json={"task_type": "inference", "task_data": {"prompt": "hi"}}, headers=_headers())
        assert resp.status_code == 502
        assert resp.json()["detail"] == "AI service unreachable"

    def test_get_job_upstream_down_is_502(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jobs/job_ghost", headers=_headers())
        assert resp.status_code == 502
        assert resp.json()["detail"] == "AI service unreachable"

    def test_list_jobs(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jobs", headers=_headers())
        assert resp.status_code == 502

    def test_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
