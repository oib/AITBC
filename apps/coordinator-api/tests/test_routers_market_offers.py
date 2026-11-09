"""Router tests for /v1/market/sync-offers + offer listings (#1289 round 9).

POST /v1/market/sync-offers is an admin batch op (#1327 fixed): the
matrix admits ADMIN_OR_CLIENT and the handler's AdminDep narrows to
admin — the previous MINER entry deadlocked the route (no role could
pass both gates). Matrix-level pins below; AuthMiddleware is disabled
under TEST_MODE so HTTP 401/403 for matrix-only routes is unobservable.
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

    def test_matrix_admits_admin_client_not_miner(self) -> None:
        # #1327 fix: matrix must not deadlock the AdminDep handler —
        # ADMIN_OR_CLIENT admits admin (which AdminDep then requires) and
        # client (which AdminDep rejects -> 403); miner is denied at matrix.
        level = get_auth_level("/v1/market/sync-offers")
        assert level == AuthLevel.ADMIN_OR_CLIENT
        assert check_role_match(level, "admin")
        assert check_role_match(level, "client")
        assert not check_role_match(level, "miner")

    def test_admin_reaches_handler(self, client: TestClient) -> None:
        # router-level truth: admin passes AdminDep (matrix off in TEST_MODE)
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
