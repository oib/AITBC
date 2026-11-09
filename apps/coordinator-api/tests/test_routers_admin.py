"""Router tests for /v1/admin/* (#1289 round 9 batch 6).

AdminDep gates everything on an admin-role JWT. Covers debug-settings
key masking, stats/jobs/miners/status on the real DB, the
debug-create-test-miner lifecycle, and the dispute/payment admin paths'
404/409 contracts (full settlement needs chain mocks — out of scope).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/admin"


def _headers(sub: str = "admin-1", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestAdminAuth:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/stats").status_code == 401

    def test_non_admin_rejected(self, client: TestClient) -> None:
        for role in ("client", "miner"):
            resp = client.get(f"{BASE}/stats", headers=_headers("u", role))
            assert resp.status_code == 403, role


class TestAdminReads:
    def test_debug_settings_masks_keys(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/debug-settings", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        for key in ("admin_api_keys", "client_api_keys", "miner_api_keys"):
            for masked in body[key]:
                assert "..." in masked or masked == "***"

    @pytest.mark.xfail(
        strict=True,
        reason="#1342: func.count() .one() returns Row — int(Row) TypeError -> 500",
    )
    def test_stats_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/stats", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert {"total_jobs", "active_jobs", "online_miners", "avg_miner_job_duration_ms"} <= set(body)

    def test_jobs_list(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jobs", headers=_headers())
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_miners_list(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/miners", headers=_headers())
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.xfail(strict=True, reason="#1342: same Row bug — /status degrades to error shape")
    def test_system_status_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/status", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "jobs" in body and "miners" in body
        assert body["status"] in ("healthy", "degraded", "error")

    def test_sweepers_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/sweepers", headers=_headers())
        assert resp.status_code == 200


class TestDebugMiner:
    def test_create_test_miner(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/debug/create-test-miner", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["miner_id"] == "debug-test-miner"
        assert body["status"] in ("created", "updated")

    def test_create_test_miner_idempotent(self, client: TestClient) -> None:
        client.post(f"{BASE}/debug/create-test-miner", headers=_headers())
        resp = client.post(f"{BASE}/debug/create-test-miner", headers=_headers())
        assert resp.json()["status"] == "updated"


class TestAdminDisputes:
    def test_resolve_unknown_job_404(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/disputes/ghost-job/resolve",
            json={"outcome": "refund", "reason": "test"},
            headers=_headers(),
        )
        assert resp.status_code == 404

    def test_resolve_job_without_disputed_payment_409(self, client: TestClient, db_session) -> None:
        # seed a plain queued job with no payment
        from datetime import UTC, datetime, timedelta
        from coordinator_api.contexts.infrastructure.domain.job import Job

        job = Job(
            client_id="client-1",
            state="QUEUED",
            payload={"type": "text"},
            constraints={},
            ttl_seconds=300,
            requested_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )
        db_session.add(job)
        db_session.commit()
        resp = client.post(
            f"{BASE}/disputes/{job.id}/resolve",
            json={"outcome": "refund", "reason": "test"},
            headers=_headers(),
        )
        assert resp.status_code == 409

    def test_retry_release_unknown_job_404(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/payments/ghost-job/retry-release", headers=_headers())
        assert resp.status_code == 404

    def test_retry_release_without_blocked_payment_409(self, client: TestClient, db_session) -> None:
        from datetime import UTC, datetime, timedelta
        from coordinator_api.contexts.infrastructure.domain.job import Job

        job = Job(
            client_id="client-1",
            state="QUEUED",
            payload={"type": "text"},
            constraints={},
            ttl_seconds=300,
            requested_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )
        db_session.add(job)
        db_session.commit()
        resp = client.post(f"{BASE}/payments/{job.id}/retry-release", headers=_headers())
        assert resp.status_code == 409

    def test_auto_adjudicate_empty(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/disputes/auto-adjudicate", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_disputed"] == 0
        assert body["adjudicated"] == []
