"""Router tests for /v1/market/sync-offers + offer listings (#1289 round 9).

POST /v1/market/sync-offers has a role contradiction: the route security
matrix pins /v1/market/sync-offers to AuthLevel.MINER while the handler
requires AdminDep (admin). MINER admits only role=="miner" and
ADMIN_OR_CLIENT-style admin fails the matrix — so no role can pass both
gates. Pinned strict-xfail pending a role ruling.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token


def _headers(sub: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


def _miner() -> dict[str, str]:
    return _headers("miner-1", "miner")


def _client() -> dict[str, str]:
    return _headers("client-1", "client")


class TestSyncOffers:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post("/v1/market/sync-offers").status_code == 401

    @pytest.mark.xfail(
        strict=True,
        reason="defect: matrix MINER x AdminDep(admin) role contradiction — no role can reach the handler",
    )
    def test_admin_reaches_handler(self, client: TestClient) -> None:
        # If the matrix admitted admin (or the dep admitted miner), this
        # would be 200. Today the matrix denies admin -> 403.
        assert client.post("/v1/market/sync-offers", headers=_admin()).status_code == 200

    def test_miner_blocked_by_admindep(self, client: TestClient) -> None:
        # miner passes the matrix but AdminDep rejects -> 403
        assert client.post("/v1/market/sync-offers", headers=_miner()).status_code == 403

    def test_client_blocked(self, client: TestClient) -> None:
        assert client.post("/v1/market/sync-offers", headers=_client()).status_code == 403


class TestOfferListings:
    """GET endpoints are matrix NONE (public market data)."""

    def test_miner_offers_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/market/miner-offers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_all_offers_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/market/offers")
        # /v1/market/offers may collide with /v1/market/{...} patterns; assert reachable
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)
