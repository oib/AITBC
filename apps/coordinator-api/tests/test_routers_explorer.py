"""Router tests for /v1/explorer/* (#1289 round 9 batch 3).

Public read-only blockchain explorer (matrix NONE). Empty-state and
404/validation contracts on the real ExplorerService + sqlite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/v1/explorer"


class TestExplorerPublic:
    def test_blocks_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/blocks")
        assert resp.status_code == 200
        body = resp.json()
        assert "blocks" in body or "items" in body or isinstance(body, list)

    def test_blocks_limit_validation(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/blocks", params={"limit": 0}).status_code == 422
        assert client.get(f"{BASE}/blocks", params={"limit": 9999}).status_code == 422

    def test_transactions_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/transactions")
        assert resp.status_code == 200

    def test_addresses_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/addresses")
        assert resp.status_code == 200

    def test_receipts_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/receipts")
        assert resp.status_code == 200

    def test_receipts_strip_private_metadata(self, client: TestClient, db_session) -> None:
        """#2675: the public listing must not leak job_payload/job_constraints/
        miner result — those belong to the owner-gated receipt route."""
        from coordinator_api.contexts.infrastructure.domain.job_receipt import JobReceipt

        stored = {
            "version": "1.0",
            "receipt_id": "r-public-1",
            "job_id": "job-public-1",
            "provider": "0xminer",
            "client": "0xbuyer",
            "status": "completed",
            "units": 12.0,
            "unit_type": "gpu_seconds",
            "unit_price": 0.02,
            "price": 0.24,
            "completed_at": 1700000000,
            "started_at": 1699999988,
            "metadata": {
                "job_payload": {"prompt": "secret client prompt"},
                "job_constraints": {"gpu": "h100", "internal": "spec"},
                "result": {"output": "miner raw result"},
                "metrics": {"duration_ms": 12000, "units": 12.0},
            },
        }
        db_session.add(JobReceipt(job_id="job-public-1", receipt_id="r-public-1", payload=dict(stored)))
        db_session.commit()

        resp = client.get(f"{BASE}/receipts")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["receiptId"] == "r-public-1"
        assert item["jobId"] == "job-public-1"
        assert item["miner"] == "0xminer"
        assert item["status"] == "completed"
        meta = item["payload"]["metadata"]
        assert "job_payload" not in meta
        assert "job_constraints" not in meta
        assert "result" not in meta
        assert meta["metrics"]["units"] == 12.0
        assert item["payload"]["price"] == 0.24
        # the stored row is untouched — only the served copy is sanitized
        from sqlmodel import select

        row = db_session.exec(select(JobReceipt).where(JobReceipt.receipt_id == "r-public-1")).one()
        assert row.payload["metadata"]["job_payload"] == {"prompt": "secret client prompt"}

    def test_missing_entities(self, client: TestClient) -> None:
        # unknown tx/block lookups -> 404 or empty detail, never 500
        for path in (
            "/transactions/0x" + "00" * 32,
            "/blocks/by-hash/0x" + "00" * 32,
            "/transactions/by-hash/0x" + "00" * 32,
        ):
            resp = client.get(f"{BASE}{path}")
            assert resp.status_code in (200, 404), path
