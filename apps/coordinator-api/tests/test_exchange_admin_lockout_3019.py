"""Pin: /v1/exchange/* matrix admits admin AND client (#3019).

AUTHZ-EXCHANGE-ADMIN-LOCKOUT-1: ``create_payment`` and ``get_payment_status``
take ``AdminOrClientDep`` — operator admin wallets drive the same customer
exchange workflow as jobs/payments — but the matrix entry was
``AuthLevel.CLIENT``, so ``AuthMiddleware`` 403'd every admin JWT before the
handler ran. Same deadlock class as #2740/#1327/#3018.

The shared ``client`` fixture runs under ``TEST_MODE=true`` so the matrix
middleware is never installed; this module builds the same auth-enabled app
as ``test_authlevel_any_token_required.py`` and hits the real routes, so the
pins exercise middleware role-match AND the handler dep together.

Public surface is unchanged: ``/v1/exchange/rates`` and
``/v1/exchange/market-stats`` keep their exact ``AuthLevel.NONE`` entries —
``_lookup_level`` resolves exact matches before wildcards, so the widened
``/v1/exchange/*`` cannot shadow them.

Coder: A
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth.jwt import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """TestClient on a coordinator-api app built with AuthMiddleware enabled.

    Same construction as ``test_authlevel_any_token_required.py``: flip the
    two settings flags for one ``create_app()`` so the route security matrix
    is actually consulted.
    """
    from coordinator_api.config import settings
    from coordinator_api.main import create_app

    previous = (settings.test_mode, settings.auth_enabled)
    settings.test_mode = False
    settings.auth_enabled = True
    try:
        authed_app = create_app()
    finally:
        settings.test_mode, settings.auth_enabled = previous
    return TestClient(authed_app)


def _headers(sub: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


ADMIN = _headers("admin-1", "admin")
CLIENT = _headers("client-1", "client")
MINER = _headers("miner-1", "miner")


class TestExchangeMatrixLevels:
    def test_authed_exchange_paths_resolve_admin_or_client(self) -> None:
        for path in (
            "/v1/exchange/create-payment",
            "/v1/exchange/payment-status/some-id",
            "/v1/exchange/confirm-payment/some-id",
        ):
            level = get_auth_level(path)
            assert level is AuthLevel.ADMIN_OR_CLIENT, f"{path} resolved to {level}"
            assert check_role_match(level, "admin"), path
            assert check_role_match(level, "client"), path
            assert not check_role_match(level, "miner"), path
            assert not check_role_match(level, None), path

    def test_public_exchange_reads_stay_none(self) -> None:
        """Exact NONE entries must survive the wildcard widening."""
        for path in ("/v1/exchange/rates", "/v1/exchange/market-stats"):
            assert get_auth_level(path) is AuthLevel.NONE, f"{path} resolved to {get_auth_level(path)}"
            assert get_auth_level(path, "GET") is AuthLevel.NONE


class TestExchangeMiddlewareAdmission:
    """The defect: admin JWT passed AdminOrClientDep but middleware 403'd it."""

    @pytest.mark.parametrize("headers", [ADMIN, CLIENT], ids=["admin", "client"])
    def test_payment_status_admits_admin_and_client(self, auth_client: TestClient, headers: dict[str, str]) -> None:
        # 404 = middleware + AdminOrClientDep both passed; the payment id is
        # simply unknown. 401/403 would mean the matrix or dep rejected.
        resp = auth_client.get("/v1/exchange/payment-status/ghost", headers=headers)
        assert resp.status_code == 404, resp.text

    @pytest.mark.parametrize("headers", [ADMIN, CLIENT], ids=["admin", "client"])
    def test_create_payment_admits_admin_and_client(self, auth_client: TestClient, headers: dict[str, str]) -> None:
        # Empty body fails schema validation (422) AFTER auth — any
        # 401/403 would mean the request never reached authorization's
        # intended admission. (Deposit address may also be unset -> 501;
        # both prove the caller cleared the gates.)
        resp = auth_client.post("/v1/exchange/create-payment", json={}, headers=headers)
        assert resp.status_code in (422, 501), resp.text

    def test_miner_is_forbidden(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/v1/exchange/payment-status/ghost", headers=MINER)
        assert resp.status_code == 403
        resp = auth_client.post("/v1/exchange/create-payment", json={}, headers=MINER)
        assert resp.status_code == 403

    def test_anonymous_is_unauthorized(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/v1/exchange/payment-status/ghost")
        assert resp.status_code == 401
        resp = auth_client.post("/v1/exchange/create-payment", json={})
        assert resp.status_code == 401

    def test_public_reads_need_no_credentials(self, auth_client: TestClient) -> None:
        """rates/market-stats stay AuthLevel.NONE — anonymous GETs answer 200."""
        assert auth_client.get("/v1/exchange/rates").status_code == 200
        assert auth_client.get("/v1/exchange/market-stats").status_code == 200
