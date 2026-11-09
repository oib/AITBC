"""Router tests for /v1/developers/* (#1289 round 9 batch 3).

Real DeveloperService + sqlite. The router carries NO auth dep — the
only gate is the matrix (/v1/developers* -> ADMIN_OR_CLIENT), disabled
under TEST_MODE; pinned via get_auth_level/check_role_match.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level

BASE = "/v1/developers"
WALLET = "0x" + "11" * 20
WALLET2 = "0x" + "22" * 20


def _headers(role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u-' + role, role)}"}


def _body(**overrides) -> dict:
    body = {"wallet_address": WALLET, "name": "dev-one", "github_handle": "dev1"}
    body.update(overrides)
    return body


class TestAuthBoundary:
    def test_matrix_admin_or_client(self) -> None:
        level = get_auth_level("/v1/developers")
        assert level == AuthLevel.ADMIN_OR_CLIENT
        assert check_role_match(level, "admin") and check_role_match(level, "client")
        assert not check_role_match(level, "miner")


class TestDeveloperLifecycle:
    def test_register_and_get(self, client: TestClient) -> None:
        resp = client.post(BASE, json=_body(), headers=_headers())
        assert resp.status_code == 201
        body = resp.json()
        assert body["wallet_address"].lower() == WALLET

        got = client.get(f"{BASE}/{WALLET}", headers=_headers())
        assert got.status_code == 200
        assert got.json()["name"] == "dev-one"

    def test_duplicate_register_400(self, client: TestClient) -> None:
        client.post(BASE, json=_body(), headers=_headers())
        assert client.post(BASE, json=_body(), headers=_headers()).status_code == 400

    def test_get_missing_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/{WALLET2}", headers=_headers()).status_code == 404

    def test_list_and_update(self, client: TestClient) -> None:
        client.post(BASE, json=_body(), headers=_headers())
        client.post(BASE, json=_body(wallet_address=WALLET2, name="dev-two"), headers=_headers())

        rows = client.get(BASE, headers=_headers()).json()
        assert {r["wallet_address"].lower() for r in rows} >= {WALLET, WALLET2}

        upd = client.put(f"{BASE}/{WALLET}", json={"name": "renamed"}, headers=_headers())
        assert upd.status_code == 200
        assert upd.json()["name"] == "renamed"

        # active_only filter path
        assert client.get(BASE, params={"active_only": "false"}, headers=_headers()).status_code == 200

    @pytest.mark.xfail(
        strict=True,
        reason="#1331: wallet_address has no format validation — register accepts 'not-an-address' with 201",
    )
    def test_validation_bad_wallet_422(self, client: TestClient) -> None:
        assert client.post(BASE, json=_body(wallet_address="not-an-address"), headers=_headers()).status_code == 422
