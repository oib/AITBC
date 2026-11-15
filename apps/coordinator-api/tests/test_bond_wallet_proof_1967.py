"""#1967 BOND-WALLET-PROOF-1 pins: bond creation requires a signed
wallet-ownership challenge, and a chain bond_id binds exactly one provider.

Pre-fix: ``miner.capabilities["wallet_address"]`` was self-declared at
registration, so any caller who could name a provider could bind the
provider's declared wallet — and its on-chain bonds — to their own miner
row. The challenge endpoint issues a single-use nonce bound to
(provider_id, wallet); create_bond verifies an EIP-191 signature over the
canonical message before touching chain state. Admin JWTs bypass, matching
``_require_provider_access``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

KEY_A = "0x" + "11" * 32
KEY_B = "0x" + "22" * 32
WALLET_A = Account.from_key(KEY_A).address
WALLET_B = Account.from_key(KEY_B).address
OTHER_KEY = "0x" + "33" * 32
UNITS_PER_AIT = 36_000_000

BASE = "/v1/market"


@pytest.fixture(autouse=True)
def _chain_bonds(monkeypatch):
    """Per-wallet chain bond registry, same shape as test_routers_bonds."""
    registry: dict[str, list[dict]] = {}

    def fake_list(self, provider_address: str) -> dict:
        return {"success": True, "provider": provider_address, "bonds": list(registry.get(provider_address, []))}

    monkeypatch.setattr(BlockchainService, "list_provider_bonds", fake_list)
    return registry


@pytest.fixture(autouse=True)
def _providers(db_session):
    db_session.add(User(id="user-a", email="a@x", username="user-a"))
    db_session.add(Wallet(user_id="user-a", address=WALLET_A))
    db_session.add(User(id="user-b", email="b@x", username="user-b"))
    db_session.add(Wallet(user_id="user-b", address=WALLET_B))
    db_session.add(Miner(id="prov-a", capabilities={"wallet_address": WALLET_A}))
    db_session.add(Miner(id="prov-b", capabilities={"wallet_address": WALLET_B}))
    db_session.commit()


def _headers(user_id: str = "user-a", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _challenge(client: TestClient, provider_id: str, headers: dict[str, str]) -> dict:
    resp = client.post(f"{BASE}/providers/{provider_id}/bonds/challenge", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _sign(key: str, message: str) -> str:
    return "0x" + Account.from_key(key).sign_message(encode_defunct(text=message)).signature.hex()


def _proof(client: TestClient, provider_id: str, key: str, headers: dict[str, str]) -> dict:
    challenge = _challenge(client, provider_id, headers)
    return {
        "challenge_nonce": challenge["nonce"],
        "wallet_signature": _sign(key, challenge["message"]),
    }


def _seed_bond(registry: dict, wallet: str, bond_id: str, amount_ait: str = "5") -> None:
    registry.setdefault(wallet, []).append(
        {
            "bond_id": bond_id,
            "amount": int(Decimal(amount_ait) * UNITS_PER_AIT),
            "status": "active",
            "locked_until": None,
        }
    )


class TestBondChallenge:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/providers/prov-a/bonds/challenge").status_code == 401

    def test_non_owner_forbidden(self, client: TestClient) -> None:
        # user-b owns prov-b's wallet, not prov-a's
        resp = client.post(f"{BASE}/providers/prov-a/bonds/challenge", headers=_headers("user-b"))
        assert resp.status_code == 403

    def test_returns_signable_message(self, client: TestClient) -> None:
        body = _challenge(client, "prov-a", _headers())
        assert body["nonce"]
        assert body["wallet_address"].lower() == WALLET_A.lower()
        assert body["expires_in"] == 300
        assert "Provider: prov-a" in body["message"]
        assert f"Wallet: {WALLET_A.lower()}" in body["message"]
        assert f"Nonce: {body['nonce']}" in body["message"]

    def test_provider_without_wallet_400(self, client: TestClient, db_session) -> None:
        db_session.add(Miner(id="prov-nowallet", capabilities={}))
        db_session.commit()
        resp = client.post(f"{BASE}/providers/prov-nowallet/bonds/challenge", headers=_headers("admin-x", "admin"))
        assert resp.status_code == 400


class TestBondWalletProof:
    def test_missing_proof_rejected(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-1")
        resp = client.post(f"{BASE}/providers/prov-a/bonds", json={"bond_id": "cb-1"}, headers=_headers())
        assert resp.status_code == 403
        assert "wallet proof" in resp.json()["detail"]

    def test_wrong_key_signature_rejected(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-2")
        proof = _proof(client, "prov-a", OTHER_KEY, _headers())
        resp = client.post(
            f"{BASE}/providers/prov-a/bonds",
            json={"bond_id": "cb-2", **proof},
            headers=_headers(),
        )
        assert resp.status_code == 403

    def test_valid_proof_accepted(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-3")
        proof = _proof(client, "prov-a", KEY_A, _headers())
        resp = client.post(
            f"{BASE}/providers/prov-a/bonds",
            json={"bond_id": "cb-3", **proof},
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "active"

    def test_nonce_is_single_use(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-4")
        _seed_bond(_chain_bonds, WALLET_A, "cb-5")
        proof = _proof(client, "prov-a", KEY_A, _headers())
        first = client.post(f"{BASE}/providers/prov-a/bonds", json={"bond_id": "cb-4", **proof}, headers=_headers())
        assert first.status_code == 200
        # Replaying the same nonce for a second bond must fail — the nonce
        # burned on first use.
        second = client.post(f"{BASE}/providers/prov-a/bonds", json={"bond_id": "cb-5", **proof}, headers=_headers())
        assert second.status_code == 403

    def test_nonce_bound_to_provider(self, client: TestClient, _chain_bonds) -> None:
        """A challenge issued for prov-a cannot create a bond for prov-b."""
        _seed_bond(_chain_bonds, WALLET_B, "cb-6")
        proof = _proof(client, "prov-a", KEY_A, _headers())
        resp = client.post(
            f"{BASE}/providers/prov-b/bonds",
            json={"bond_id": "cb-6", **proof},
            headers=_headers("user-b"),
        )
        assert resp.status_code == 403

    def test_admin_bypasses_proof(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-7")
        resp = client.post(
            f"{BASE}/providers/prov-a/bonds",
            json={"bond_id": "cb-7"},
            headers=_headers("admin-x", "admin"),
        )
        assert resp.status_code == 200, resp.text


class TestBondIdUniqueness:
    def test_bond_id_cannot_back_two_providers(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-shared")
        _seed_bond(_chain_bonds, WALLET_B, "cb-shared")
        proof_a = _proof(client, "prov-a", KEY_A, _headers())
        resp = client.post(f"{BASE}/providers/prov-a/bonds", json={"bond_id": "cb-shared", **proof_a}, headers=_headers())
        assert resp.status_code == 200, resp.text
        proof_b = _proof(client, "prov-b", KEY_B, _headers("user-b"))
        resp = client.post(
            f"{BASE}/providers/prov-b/bonds", json={"bond_id": "cb-shared", **proof_b}, headers=_headers("user-b")
        )
        assert resp.status_code == 409
        assert "already bound" in resp.json()["detail"]

    def test_same_provider_rebind_is_idempotent(self, client: TestClient, _chain_bonds) -> None:
        _seed_bond(_chain_bonds, WALLET_A, "cb-re")
        for _ in range(2):
            proof = _proof(client, "prov-a", KEY_A, _headers())
            resp = client.post(f"{BASE}/providers/prov-a/bonds", json={"bond_id": "cb-re", **proof}, headers=_headers())
            assert resp.status_code == 200, resp.text
