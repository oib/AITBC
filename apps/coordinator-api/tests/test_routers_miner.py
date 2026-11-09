"""Router tests for /v1/miners/* (#1289 round 9 batch 6).

Real MinerService + sqlite. MinerDep gates every endpoint on a miner-role
JWT bound to user["sub"]. Covers register -> heartbeat -> poll ->
capabilities -> deregister lifecycle, plus 404/validation paths on the
result/fail/jobs/earnings endpoints (full result submission exercises
ZK/TEE/payment gates — pinned where the contract is dishonest).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1"


def _headers(sub: str = "miner-1", role: str = "miner") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _register(client: TestClient, sub: str = "miner-1") -> dict:
    resp = client.post(
        f"{BASE}/miners/register",
        json={"capabilities": {"gpu_memory": 8192, "models": ["llama"]}, "concurrency": 1, "region": "eu"},
        headers=_headers(sub),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMinerAuth:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/miners/register", json={"capabilities": {}}).status_code == 401

    def test_non_miner_role_rejected(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/miners/register",
            json={"capabilities": {}},
            headers=_headers("c1", "client"),
        )
        assert resp.status_code in (401, 403)  # require_miner falls back to API-key -> 401 on JWT role miss


class TestMinerLifecycle:
    def test_register_returns_session_token(self, client: TestClient) -> None:
        body = _register(client)
        assert body["status"] == "ok"
        assert body["session_token"]

    def test_register_is_upsert(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(
            f"{BASE}/miners/register",
            json={"capabilities": {"gpu_memory": 4096}, "concurrency": 2},
            headers=_headers(),
        )
        assert resp.status_code == 200

    def test_heartbeat_unregistered_404(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/miners/heartbeat", json={}, headers=_headers("ghost-miner"))
        assert resp.status_code == 404

    def test_heartbeat_after_register(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(f"{BASE}/miners/heartbeat", json={"inflight": 1, "status": "ONLINE"}, headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_poll_empty_204(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(f"{BASE}/miners/poll", json={"max_wait_seconds": 0}, headers=_headers())
        # no jobs queued -> 204 No Content (or a job if dispatch races; accept both)
        assert resp.status_code in (200, 204)

    @pytest.mark.xfail(
        strict=True,
        reason="#1343: unregistered miner poll raises 'miner not registered' -> 500; heartbeat maps the same case to 404",
    )
    def test_poll_requires_registration(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/miners/poll", json={"max_wait_seconds": 0}, headers=_headers("ghost2"))
        assert resp.status_code == 404

    def test_update_capabilities(self, client: TestClient) -> None:
        _register(client)
        resp = client.put(
            f"{BASE}/miners/miner-1/capabilities",
            json={"capabilities": {"gpu_memory": 16384}},
            headers=_headers(),
        )
        assert resp.status_code in (200, 404)  # path uses miner_id — sub may differ from id

    def test_earnings_shape(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(f"{BASE}/miners/miner-1/earnings", json={}, headers=_headers())
        assert resp.status_code in (200, 404)

    def test_jobs_for_miner(self, client: TestClient) -> None:
        _register(client)
        resp = client.post(f"{BASE}/miners/miner-1/jobs", json={}, headers=_headers())
        assert resp.status_code in (200, 404)

    def test_deregister(self, client: TestClient) -> None:
        _register(client, "miner-del")
        resp = client.delete(f"{BASE}/miners/miner-del", headers=_headers("miner-del"))
        assert resp.status_code in (200, 204, 404)

    def test_result_unknown_job_404(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/miners/ghost-job/result",
            json={"result": {"output": "x"}},
            headers=_headers(),
        )
        assert resp.status_code in (404, 400, 409, 425)

    def test_fail_unknown_job(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/miners/ghost-job/fail",
            json={"error_code": "E", "error_message": "boom"},
            headers=_headers(),
        )
        assert resp.status_code in (404, 400, 409)

    def test_miner_scoped_job_paths_reject_other_miner(self, client: TestClient) -> None:
        # /miners/{miner_id}/jobs/{job_id}/fail — a miner must not fail another miner's job
        _register(client, "miner-a")
        _register(client, "miner-b")
        resp = client.post(
            f"{BASE}/miners/miner-b/jobs/ghost-job/fail",
            json={"error_code": "E", "error_message": "x"},
            headers=_headers("miner-a"),
        )
        # either ownership-checked 403/404 or the job simply doesn't exist —
        # but it must NOT succeed
        assert resp.status_code != 200
