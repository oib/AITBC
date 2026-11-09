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

    def test_missing_entities(self, client: TestClient) -> None:
        # unknown tx/block lookups -> 404 or empty detail, never 500
        for path in (
            "/transactions/0x" + "00" * 32,
            "/blocks/by-hash/0x" + "00" * 32,
            "/transactions/by-hash/0x" + "00" * 32,
        ):
            resp = client.get(f"{BASE}{path}")
            assert resp.status_code in (200, 404), path
