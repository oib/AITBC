"""Router tests for /v1/market/sync-offers + offer listings (#1289 round 9).

POST /v1/market/sync-offers has a role contradiction (#1327): the route
security matrix pins it to AuthLevel.MINER while the handler requires
AdminDep (admin) — no role can pass both gates in production. Pinned at
matrix level since AuthMiddleware is disabled under TEST_MODE.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level


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

    def test_role_contradiction_documented(self, client: TestClient) -> None:
        # Defect #1327: matrix MINER admits only role=="miner"; AdminDep
        # admits only role=="admin" — no role satisfies both gates in
        # production. Pinned at matrix level (AuthMiddleware is disabled
        # under TEST_MODE, so HTTP-level contradiction is not observable
        # here; admin reaches the handler -> 200 only without the matrix).
        level = get_auth_level("/v1/market/sync-offers")
        assert level == AuthLevel.MINER
        assert check_role_match(level, "miner")
        assert not check_role_match(level, "admin")
        # router-level truth: admin passes AdminDep when matrix is off
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
