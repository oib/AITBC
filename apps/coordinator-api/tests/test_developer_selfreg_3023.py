"""#3023 AUTHZ-DEVELOPERS-SELFREG-JWT-FRICTION-1 pins.

Intent ruling: self-service public+signature — ``POST /v1/developers``
verifies the wallet signature + fresh timestamp itself (same model as
``/v1/register`` + ``/v1/login``), so requiring a client JWT first was a
chicken-and-egg dead end: no JWT exists before registering.

``POST /v1/developers/register`` is the public self-service path
(matrix NONE — the signature is the credential); ``POST /v1/developers``
stays ADMIN_OR_CLIENT for the admin-provisioned flow, and every read /
update route stays gated.
"""

from __future__ import annotations

import time

from eth_account import Account
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level
from aitbc.crypto.developer_registry import developer_register_claim, sign_developer_register

BASE = "/v1/developers"
PUBLIC_REGISTER = f"{BASE}/register"

_KEY = Account.from_key("0x" + "33" * 32)
WALLET = _KEY.address
_KEY2 = Account.from_key("0x" + "44" * 32)
WALLET2 = _KEY2.address


def _headers(role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u-' + role, role)}"}


def _sign(wallet_address: str, name: str | None, github_handle: str | None, key: Account) -> dict:
    timestamp = int(time.time())
    claim = developer_register_claim(
        wallet_address=wallet_address, name=name, email=None, github_handle=github_handle, timestamp=timestamp
    )
    return {"signature": sign_developer_register(claim, key.key.hex()), "timestamp": timestamp}


def _body(wallet: str = WALLET, key: Account = _KEY, **overrides) -> dict:
    body = {"wallet_address": wallet, "name": "dev-selfreg", "github_handle": "devself"}
    body.update(overrides)
    proof = _sign(body["wallet_address"], body.get("name"), body.get("github_handle"), key)
    body.update(proof)
    return body


class TestMatrixAlignment:
    def test_public_register_path_is_none(self) -> None:
        assert get_auth_level(PUBLIC_REGISTER, "POST") == AuthLevel.NONE

    def test_admin_path_still_gated(self) -> None:
        for method in ("POST", "GET"):
            level = get_auth_level(BASE, method)
            assert level == AuthLevel.ADMIN_OR_CLIENT
            assert check_role_match(level, "admin") and check_role_match(level, "client")
            assert not check_role_match(level, "miner")

    def test_item_routes_still_gated(self) -> None:
        for method in ("GET", "PUT"):
            assert get_auth_level(f"{BASE}/0x{'ab' * 20}", method) == AuthLevel.ADMIN_OR_CLIENT


class TestPublicSelfRegistration:
    def test_register_without_jwt_succeeds(self, client: TestClient) -> None:
        """The headline fix: no Authorization header at all."""
        resp = client.post(PUBLIC_REGISTER, json=_body())
        assert resp.status_code == 201
        assert resp.json()["wallet_address"].lower() == WALLET.lower()

    def test_registered_developer_is_readable(self, client: TestClient) -> None:
        client.post(PUBLIC_REGISTER, json=_body())
        got = client.get(f"{BASE}/{WALLET}", headers=_headers())
        assert got.status_code == 200
        assert got.json()["name"] == "dev-selfreg"

    def test_bad_signature_still_401(self, client: TestClient) -> None:
        body = _body()
        body["signature"] = "0x" + "00" * 64 + "01"
        assert client.post(PUBLIC_REGISTER, json=body).status_code == 401

    def test_signature_for_other_wallet_still_401(self, client: TestClient) -> None:
        body = {"wallet_address": WALLET, "name": "dev-selfreg", "github_handle": "devself"}
        body.update(_sign(body["wallet_address"], body["name"], body["github_handle"], _KEY2))
        assert client.post(PUBLIC_REGISTER, json=body).status_code == 401

    def test_stale_timestamp_still_400(self, client: TestClient) -> None:
        body = _body()
        body["timestamp"] = int(time.time()) - 3600
        claim = developer_register_claim(
            wallet_address=body["wallet_address"],
            name=body.get("name"),
            email=None,
            github_handle=body.get("github_handle"),
            timestamp=body["timestamp"],
        )
        body["signature"] = sign_developer_register(claim, _KEY.key.hex())
        assert client.post(PUBLIC_REGISTER, json=body).status_code == 400

    def test_missing_signature_fields_422(self, client: TestClient) -> None:
        body = {"wallet_address": WALLET, "name": "dev-selfreg"}
        assert client.post(PUBLIC_REGISTER, json=body).status_code == 422


class TestAdminPathPreserved:
    def test_post_base_still_registers_for_authed_caller(self, client: TestClient) -> None:
        """POST /v1/developers (admin/client matrix path) is unchanged."""
        resp = client.post(BASE, json=_body(wallet=WALLET2, key=_KEY2), headers=_headers())
        assert resp.status_code == 201
        assert resp.json()["wallet_address"].lower() == WALLET2.lower()
