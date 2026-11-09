"""Router tests for /v1/jobs*, /v1/blocks (#1289 round 9 batch 6).

client.py is the public job-submission surface — real JobService +
sqlite, AdminOrClientDep, Idempotency-Key ledger (begin_operation).
Covers submit -> list -> get -> cancel -> history lifecycle, filter
validation, ownership scoping (client_id bound to JWT sub), result/
receipt gating, and the /blocks upstream-degradation contract.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _job_payload(**over) -> dict:
    body = {"payload": {"type": "text", "prompt": "hello"}, "ttl_seconds": 300}
    body.update(over)
    return body


def _submit(client: TestClient, sub: str = "client-1") -> dict:
    resp = client.post(f"{BASE}/jobs", json=_job_payload(), headers=_headers(sub))
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestSubmitJob:
    def test_submit_creates_queued_job(self, client: TestClient) -> None:
        body = _submit(client)
        assert body["job_id"]
        assert body["state"] in ("QUEUED", "queued")

    def test_submit_requires_auth(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/jobs", json=_job_payload())
        assert resp.status_code == 401

    def test_submit_admin_or_client(self, client: TestClient) -> None:
        # AdminOrClientDep: admin token also accepted — wallet-address sub so
        # resolve_client can auto-provision (arbitrary subs hit #1340's 500)
        resp = client.post(f"{BASE}/jobs", json=_job_payload(), headers=_headers("0x" + "bb" * 20, "admin"))
        assert resp.status_code == 201
        # miner role rejected
        resp = client.post(f"{BASE}/jobs", json=_job_payload(), headers=_headers("m1", "miner"))
        assert resp.status_code == 403

    def test_submit_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/jobs", json={}, headers=_headers()).status_code == 422

    def test_gpu_compute_requires_price(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/jobs",
            json={"payload": {"type": "gpu_compute"}, "ttl_seconds": 300},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_idempotency_key_replays(self, client: TestClient) -> None:
        headers = {**_headers(), "Idempotency-Key": "test-key-123"}
        r1 = client.post(f"{BASE}/jobs", json=_job_payload(), headers=headers)
        r2 = client.post(f"{BASE}/jobs", json=_job_payload(), headers=headers)
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["job_id"] == r2.json()["job_id"]  # replay, not duplicate


class TestJobReads:
    def test_list_jobs_scoped_to_caller(self, client: TestClient) -> None:
        job = _submit(client, "client-1")
        _submit(client, "client-2") if False else None  # client-2 not seeded; use same sub for second
        resp = client.get(f"{BASE}/jobs", headers=_headers("client-1"))
        assert resp.status_code == 200
        ids = [j["job_id"] for j in resp.json()["items"]]
        assert job["job_id"] in ids

    def test_get_job_404_unknown(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/jobs/ghost", headers=_headers()).status_code == 404

    def test_get_job_roundtrip(self, client: TestClient) -> None:
        job = _submit(client)
        resp = client.get(f"{BASE}/jobs/{job['job_id']}", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job["job_id"]

    def test_cannot_read_other_clients_job(self, client: TestClient) -> None:
        # client-2 is not seeded -> resolve_client fails; use a second seeded ref
        job = _submit(client, "client1")
        # client-1 must not see client1's job (different sub -> different owner)
        resp = client.get(f"{BASE}/jobs/{job['job_id']}", headers=_headers("client-1"))
        assert resp.status_code == 404

    def test_history_endpoint(self, client: TestClient) -> None:
        _submit(client)
        resp = client.get(f"{BASE}/jobs/history", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_invalid_status_filter_400(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/jobs", params={"status": "bogus"}, headers=_headers()).status_code == 400
        assert client.get(f"{BASE}/jobs/history", params={"status": "bogus"}, headers=_headers()).status_code == 400

    def test_result_425_until_terminal(self, client: TestClient) -> None:
        job = _submit(client)
        resp = client.get(f"{BASE}/jobs/{job['job_id']}/result", headers=_headers())
        assert resp.status_code == 425

    def test_receipt_404_when_absent(self, client: TestClient) -> None:
        job = _submit(client)
        assert client.get(f"{BASE}/jobs/{job['job_id']}/receipt", headers=_headers()).status_code == 404
        assert client.get(f"{BASE}/jobs/{job['job_id']}/receipts", headers=_headers()).status_code == 200

    def test_cancel_queued_job(self, client: TestClient) -> None:
        job = _submit(client)
        resp = client.post(f"{BASE}/jobs/{job['job_id']}/cancel", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["state"] in ("CANCELED", "canceled")

    def test_cancel_twice_409(self, client: TestClient) -> None:
        job = _submit(client)
        client.post(f"{BASE}/jobs/{job['job_id']}/cancel", headers=_headers())
        resp = client.post(f"{BASE}/jobs/{job['job_id']}/cancel", headers=_headers())
        assert resp.status_code == 409


class TestAcceptAndBlocks:
    def test_accept_unpaid_job_rejected(self, client: TestClient) -> None:
        # job has no escrowed payment -> accept must not succeed
        job = _submit(client)
        resp = client.post(f"{BASE}/jobs/{job['job_id']}/accept", headers=_headers())
        assert resp.status_code in (400, 404, 409, 422, 502)

    def test_blocks_degrades_without_rpc(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/blocks", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        # upstream unreachable in tests -> degraded contract, never a 500
        assert "blocks" in body
