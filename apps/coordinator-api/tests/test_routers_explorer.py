"""Router tests for /v1/explorer/* (#1289 round 9 batch 3).

Public read-only blockchain explorer (matrix NONE). Empty-state and
404/validation contracts on the real ExplorerService + sqlite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/v1/explorer"


def _rpc_ok(blocks: list[dict] | None = None, height: int = 0):
    """Fake AITBCHTTPClient returning a healthy head/blocks-range."""

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get(self, url, params=None):
            if url.endswith("/rpc/head"):
                return {"height": height}
            return {"blocks": blocks or []}

    return _Client


def _rpc_down(error: Exception):
    """Fake AITBCHTTPClient whose every call raises."""

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get(self, url, params=None):
            raise error

    return _Client


class TestExplorerPublic:
    def test_blocks_empty(self, client: TestClient, monkeypatch) -> None:
        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod

        monkeypatch.setattr(explorer_mod, "AITBCHTTPClient", _rpc_ok(height=0))
        resp = client.get(f"{BASE}/blocks")
        assert resp.status_code == 200
        body = resp.json()
        assert "blocks" in body or "items" in body or isinstance(body, list)

    def test_blocks_rpc_failure_is_502_not_fabricated(self, client: TestClient, monkeypatch, db_session) -> None:
        """#2716: an RPC outage must be an honest 502 — never job rows dressed
        up as blocks at invented heights."""
        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod
        from aitbc.exceptions import NetworkError

        # A job row exists that the old fallback would have turned into a fake block.
        from coordinator_api.contexts.infrastructure.domain import Job
        from coordinator_api.contexts.infrastructure.domain.user import User

        db_session.add(User(id="c1", email="c1@aitbc.local", username="c1"))
        db_session.add(Job(id="job-fake-block", client_id="c1", payload={}))
        db_session.commit()

        monkeypatch.setattr(explorer_mod, "AITBCHTTPClient", _rpc_down(NetworkError("connection refused")))
        resp = client.get(f"{BASE}/blocks")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "blockchain RPC unavailable"

    def test_blocks_rpc_error_text_not_leaked(self, client: TestClient, monkeypatch) -> None:
        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod
        from aitbc.exceptions import NetworkError

        monkeypatch.setattr(
            explorer_mod, "AITBCHTTPClient", _rpc_down(NetworkError("dial tcp 10.0.0.1:8545: secret-path-leak"))
        )
        resp = client.get(f"{BASE}/blocks")
        assert resp.status_code == 502
        assert "secret-path-leak" not in resp.text

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

    def test_missing_entities(self, client: TestClient, monkeypatch) -> None:
        # unknown tx/block lookups -> 404, never 500 and never exception text
        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod
        from aitbc.exceptions import NetworkError

        monkeypatch.setattr(explorer_mod, "AITBCHTTPClient", _rpc_down(NetworkError("404 not found")))
        for path in (
            "/transactions/0x" + "00" * 32,
            "/blocks/by-hash/0x" + "00" * 32,
            "/transactions/by-hash/0x" + "00" * 32,
        ):
            resp = client.get(f"{BASE}{path}")
            assert resp.status_code == 404, (path, resp.status_code, resp.text[:200])

    def test_transaction_rpc_failure_is_502_generic(self, client: TestClient, monkeypatch) -> None:
        """#2716: RPC failure -> 502 with a generic detail, no exception text."""
        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod
        from aitbc.exceptions import NetworkError

        monkeypatch.setattr(
            explorer_mod,
            "AITBCHTTPClient",
            _rpc_down(NetworkError("read tcp 10.1.2.3:54321->db.internal: connection reset by peer")),
        )
        resp = client.get(f"{BASE}/transactions/0x" + "11" * 32)
        assert resp.status_code == 502
        assert resp.json()["detail"] == "blockchain RPC unavailable"
        assert "db.internal" not in resp.text

    def test_block_lookup_store_error_is_503(self, client: TestClient, monkeypatch) -> None:
        """#2716: chain.db read failure -> 503 generic, not 200 + exception text."""
        import sqlite3

        import coordinator_api.contexts.infrastructure.services.explorer as explorer_mod

        class _FakePath:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def exists(self) -> bool:
                return True

        def _boom(_path):
            raise sqlite3.OperationalError("database disk image is malformed")

        monkeypatch.setattr(explorer_mod, "Path", _FakePath)
        monkeypatch.setattr(explorer_mod, "_connect_chain_db", _boom)
        for path in ("/blocks/by-hash/0x" + "22" * 32, "/transactions/by-hash/0x" + "22" * 32):
            resp = client.get(f"{BASE}{path}")
            assert resp.status_code == 503, (path, resp.status_code, resp.text[:200])
            assert "malformed" not in resp.text
