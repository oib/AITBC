"""Router tests for /v1/developers/* (#1289 round 9 batch 3, #2566 signature gate).

Real DeveloperService + sqlite. The router carries NO auth dep — the
only gate is the matrix (/v1/developers* -> ADMIN_OR_CLIENT), disabled
under TEST_MODE; pinned via get_auth_level/check_role_match.

#2566: POST /v1/developers now requires ``signature``/``timestamp`` proving
control of ``wallet_address`` — every register body below is signed with a
real secp256k1 key.
"""

from __future__ import annotations

import time

from eth_account import Account
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level
from aitbc.crypto.developer_registry import developer_register_claim, sign_developer_register

BASE = "/v1/developers"

_KEY = Account.from_key("0x" + "11" * 32)
WALLET = _KEY.address
_KEY2 = Account.from_key("0x" + "22" * 32)
WALLET2 = _KEY2.address


def _headers(role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u-' + role, role)}"}


def _sign(wallet_address: str, name: str | None, github_handle: str | None, key: Account) -> dict:
    timestamp = int(time.time())
    claim = developer_register_claim(
        wallet_address=wallet_address, name=name, email=None, github_handle=github_handle, timestamp=timestamp
    )
    return {"signature": sign_developer_register(claim, key.key.hex()), "timestamp": timestamp}


def _body(**overrides) -> dict:
    body = {"wallet_address": WALLET, "name": "dev-one", "github_handle": "dev1"}
    body.update(overrides)
    key = _KEY2 if body["wallet_address"] == WALLET2 else _KEY
    proof = _sign(body["wallet_address"], body.get("name"), body.get("github_handle"), key)
    body.update(proof)
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
        assert body["wallet_address"].lower() == WALLET.lower()

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
        assert {r["wallet_address"].lower() for r in rows} >= {WALLET.lower(), WALLET2.lower()}

        upd = client.put(f"{BASE}/{WALLET}", json={"name": "renamed"}, headers=_headers())
        assert upd.status_code == 200
        assert upd.json()["name"] == "renamed"

        # active_only filter path
        assert client.get(BASE, params={"active_only": "false"}, headers=_headers()).status_code == 200

    def test_validation_bad_wallet_422(self, client: TestClient) -> None:
        body = _body(wallet_address="not-an-address")
        # signature/timestamp must still be present for the schema; the wallet
        # validator fires first anyway.
        assert client.post(BASE, json=body, headers=_headers()).status_code == 422


class TestRegisterSignatureGate:
    """#2566: an unsigned or wrongly-signed registration must not land."""

    def test_missing_signature_fields_422(self, client: TestClient) -> None:
        body = {"wallet_address": WALLET, "name": "dev-one"}
        assert client.post(BASE, json=body, headers=_headers()).status_code == 422

    def test_garbage_signature_401(self, client: TestClient) -> None:
        body = _body()
        body["signature"] = "0x" + "00" * 64 + "01"
        assert client.post(BASE, json=body, headers=_headers()).status_code == 401

    def test_signature_for_other_wallet_401(self, client: TestClient) -> None:
        """A valid signature that recovers to a different address is refused."""
        body = {"wallet_address": WALLET, "name": "dev-one", "github_handle": "dev1"}
        proof = _sign(body["wallet_address"], body["name"], body["github_handle"], _KEY2)
        body.update(proof)
        assert client.post(BASE, json=body, headers=_headers()).status_code == 401

    def test_stale_timestamp_400(self, client: TestClient) -> None:
        body = _body()
        body["timestamp"] = int(time.time()) - 3600
        # re-sign over the stale timestamp so only freshness fails
        claim = developer_register_claim(
            wallet_address=body["wallet_address"],
            name=body.get("name"),
            email=None,
            github_handle=body.get("github_handle"),
            timestamp=body["timestamp"],
        )
        body["signature"] = sign_developer_register(claim, _KEY.key.hex())
        assert client.post(BASE, json=body, headers=_headers()).status_code == 400

    def test_unsigned_cannot_squat_victim_wallet(self, client: TestClient) -> None:
        """The audit case: posting a victim's wallet_address with no proof."""
        body = {"wallet_address": WALLET2, "name": "attacker", "github_handle": "evil"}
        proof = _sign(WALLET, "attacker", "evil", _KEY)  # signed by the wrong key AND wrong wallet fields
        body.update(proof)
        assert client.post(BASE, json=body, headers=_headers()).status_code == 401
