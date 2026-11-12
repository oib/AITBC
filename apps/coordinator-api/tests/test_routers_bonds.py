"""Router tests for /v1/market/providers/{id}/bonds* and /v1/market/bonds/{id} (#1289 round 9 batch 6).

Real ProviderBond domain + sqlite. require_auth accepts any valid JWT.

#1915: create_bond no longer trusts caller-supplied amounts — it verifies
``bond_id`` against the chain's ``/rpc/bond/provider/{wallet}`` listing and
derives amount/status from the chain record. These tests stub
``BlockchainService.list_provider_bonds`` with a per-wallet registry.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError

from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

PROVIDER_WALLET = "0x1111111111111111111111111111111111111111"
OTHER_WALLET = "0x2222222222222222222222222222222222222222"
UNITS_PER_AIT = 36_000_000


@pytest.fixture(autouse=True)
def _chain_bonds(monkeypatch):
    """Stub the chain bond listing: registry maps provider wallet -> bond entries."""
    registry: dict[str, list[dict]] = {}

    def fake_list(self, provider_address: str) -> dict:
        return {"success": True, "provider": provider_address, "bonds": list(registry.get(provider_address, []))}

    monkeypatch.setattr(BlockchainService, "list_provider_bonds", fake_list)
    return registry


@pytest.fixture(autouse=True)
def _bound_providers(db_session):
    """#1881: bond mutations now require provider ownership — seed miners
    p1/p2/p3/ghost2 paying out to provider-1's wallet."""
    db_session.add(User(id="provider-1", email="provider-1@aitbc.local", username="provider-1"))
    db_session.add(Wallet(user_id="provider-1", address=PROVIDER_WALLET))
    for pid in ("p1", "p2", "p3", "ghost2"):
        db_session.add(Miner(id=pid, capabilities={"wallet_address": PROVIDER_WALLET}))
    db_session.add(Miner(id="nowallet", capabilities={}))
    db_session.commit()


def _chain_bond(bond_id: str, amount_ait: str, status: str = "active") -> dict:
    return {
        "bond_id": bond_id,
        "amount": int(Decimal(amount_ait) * UNITS_PER_AIT),
        "status": status,
        "locked_until": None,
    }


def _seed_chain_bond(registry: dict, wallet: str, bond_id: str, amount_ait: str, status: str = "active") -> None:
    registry.setdefault(wallet, []).append(_chain_bond(bond_id, amount_ait, status))


BASE = "/v1/market"


def _headers(sub: str = "provider-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestBondAuth:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/providers/p1/bonds", json={}).status_code == 401
        assert client.get(f"{BASE}/providers/p1/eligibility").status_code == 401
        assert client.get(f"{BASE}/bonds/b1").status_code == 401

    def test_any_role_accepted(self, client: TestClient) -> None:
        # require_auth is role-agnostic — miner/admin/client tokens all pass
        for role in ("client", "miner", "admin"):
            resp = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers("u", role))
            assert resp.status_code == 200, role


class TestBondLifecycle:
    def test_create_below_floor_pending(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-1", "0.5")
        resp = client.post(
            f"{BASE}/providers/p1/bonds",
            json={"bond_id": "cb-1", "required_amount": "0.1"},
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        # required_amount raised to the global floor (default 1)
        assert Decimal(body["required_amount"]) == Decimal("1")
        assert body["status"] == "pending"  # chain amount 0.5 < 1
        assert body["provider_id"] == "p1"
        assert body["bond_id"] == "cb-1"
        # chain provenance is recorded on the row
        assert body["meta"]["chain_bond_id"] == "cb-1"
        assert body["meta"]["chain_amount_units"] == int(Decimal("0.5") * UNITS_PER_AIT)

    def test_create_meeting_floor_active(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-2", "5")
        resp = client.post(
            f"{BASE}/providers/p1/bonds",
            json={"bond_id": "cb-2", "required_amount": "2"},
            headers=_headers(),
        )
        body = resp.json()
        assert body["status"] == "active"
        # amount comes from the CHAIN record, not the request body
        assert Decimal(body["amount"]) == Decimal("5")

    def test_caller_amount_is_ignored(self, client: TestClient, _chain_bonds) -> None:
        """#1915 core: a self-declared amount must not inflate the bond."""
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-3", "5")
        resp = client.post(
            f"{BASE}/providers/p1/bonds",
            json={"bond_id": "cb-3", "amount": "999"},
            headers=_headers(),
        )
        assert Decimal(resp.json()["amount"]) == Decimal("5")

    def test_create_is_upsert(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-a", "5")
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-b", "9")
        client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-a"}, headers=_headers())
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-b"}, headers=_headers())
        assert Decimal(resp.json()["amount"]) == Decimal("9")
        # still one record
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert elig["eligible"] is True

    def test_missing_bond_id_rejected(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"amount": "5"}, headers=_headers())
        assert resp.status_code == 400

    def test_unknown_onchain_bond_rejected(self, client: TestClient, _chain_bonds) -> None:
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-nope"}, headers=_headers())
        assert resp.status_code == 400
        assert "not an on-chain bond" in resp.json()["detail"]

    def test_other_providers_bond_rejected(self, client: TestClient, _chain_bonds) -> None:
        """A bond the chain attributes to a different wallet cannot be claimed."""
        _seed_chain_bond(_chain_bonds, OTHER_WALLET, "cb-other", "50")
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-other"}, headers=_headers())
        assert resp.status_code == 400

    def test_non_active_onchain_bond_rejected(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-rel", "5", status="released")
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-rel"}, headers=_headers())
        assert resp.status_code == 400
        assert "not active" in resp.json()["detail"]

    def test_provider_without_wallet_rejected(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-4", "5")
        resp = client.post(f"{BASE}/providers/nowallet/bonds", json={"bond_id": "cb-4"}, headers=_headers("admin", "admin"))
        assert resp.status_code == 400
        assert "no registered wallet" in resp.json()["detail"]

    def test_chain_unreachable_is_502(self, client: TestClient, monkeypatch) -> None:
        def boom(self, provider_address: str) -> dict:
            raise NetworkError("chain down")

        monkeypatch.setattr(BlockchainService, "list_provider_bonds", boom)
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": "cb-x"}, headers=_headers())
        assert resp.status_code == 502

    def test_eligibility_no_bond(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/providers/ghost/eligibility", headers=_headers())
        body = resp.json()
        assert body["eligible"] is False
        assert body["status"] == "pending"

    def test_get_bond_by_id_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/bonds/nope", headers=_headers()).status_code == 404

    def test_get_bond_by_id_roundtrip(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-5", "3")
        created = client.post(f"{BASE}/providers/p2/bonds", json={"bond_id": "cb-5"}, headers=_headers()).json()
        resp = client.get(f"{BASE}/bonds/{created['id']}", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["provider_id"] == "p2"

    def test_lock_release_slash(self, client: TestClient, _chain_bonds) -> None:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-6", "5")
        client.post(f"{BASE}/providers/p3/bonds", json={"bond_id": "cb-6"}, headers=_headers())
        locked = client.post(f"{BASE}/providers/p3/bonds/lock", headers=_headers()).json()
        assert locked["status"] == "locked"
        # amount preserved through transitions
        assert Decimal(locked["amount"]) == Decimal("5")
        released = client.post(f"{BASE}/providers/p3/bonds/release", headers=_headers()).json()
        assert released["status"] == "active"
        slashed = client.post(f"{BASE}/providers/p3/bonds/slash", json={"reason": "fraud"}, headers=_headers()).json()
        assert slashed["status"] == "liquidated"
        assert slashed["meta"]["slash_reason"] == "fraud"
        assert slashed["meta"]["slashed_by"] == "provider-1"

    def test_lock_without_bond_creates_pending_row(self, client: TestClient) -> None:
        # set_provider_bond_status upserts — locking a bondless provider yields a row
        resp = client.post(f"{BASE}/providers/ghost2/bonds/lock", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"


class TestEligibilityChainReverify:
    """#1926: eligibility reads re-verify the local projection against chain —
    a bond released/slashed on-chain post-activation must stop qualifying."""

    def _active_bond(self, client: TestClient, _chain_bonds, bond_id: str = "cb-r1") -> dict:
        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, bond_id, "5")
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"bond_id": bond_id}, headers=_headers())
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_chain_release_marks_ineligible(self, client: TestClient, _chain_bonds, monkeypatch) -> None:
        monkeypatch.setenv("COORDINATOR_BOND_CHAIN_REVERIFY_SECONDS", "0")
        self._active_bond(client, _chain_bonds)
        assert client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()["eligible"] is True
        # Bond released on-chain after local activation.
        _chain_bonds[PROVIDER_WALLET][0]["status"] = "released"
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert elig["eligible"] is False
        assert elig["status"] == "released"

    def test_chain_slash_marks_liquidated(self, client: TestClient, _chain_bonds, monkeypatch) -> None:
        monkeypatch.setenv("COORDINATOR_BOND_CHAIN_REVERIFY_SECONDS", "0")
        self._active_bond(client, _chain_bonds)
        _chain_bonds[PROVIDER_WALLET][0]["status"] = "slashed"
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert elig["eligible"] is False
        assert elig["status"] == "liquidated"

    def test_chain_amount_drift_reconciles(self, client: TestClient, _chain_bonds, monkeypatch) -> None:
        monkeypatch.setenv("COORDINATOR_BOND_CHAIN_REVERIFY_SECONDS", "0")
        self._active_bond(client, _chain_bonds)
        _chain_bonds[PROVIDER_WALLET][0]["amount"] = int(Decimal("2") * UNITS_PER_AIT)
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert Decimal(elig["amount"]) == Decimal("2")

    def test_rpc_failure_keeps_local_answer_on_read(self, client: TestClient, db_session, monkeypatch) -> None:
        """Read path is not money-moving: an RPC outage must not flip the
        reported eligibility — the local projection stands."""
        from coordinator_api.contexts.market.domain.provider_bond import (
            ProviderBondStatus,
            set_provider_bond_status,
        )

        set_provider_bond_status(
            db_session,
            "p1",
            ProviderBondStatus.ACTIVE,
            amount=Decimal("5"),
            required_amount=Decimal("1"),
            bond_id="cb-local",
        )

        def _raise(self, provider_address: str) -> dict:
            raise NetworkError("chain unreachable")

        monkeypatch.setattr(BlockchainService, "list_provider_bonds", _raise)
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert elig["eligible"] is True
        assert elig["status"] == "active"

    def test_reconcile_returns_none_on_rpc_error(self, db_session, monkeypatch) -> None:
        """Money-moving callers get None (fail closed) when chain can't be consulted."""
        from coordinator_api.contexts.market.domain.provider_bond import (
            ProviderBondStatus,
            reconcile_provider_bond,
            set_provider_bond_status,
        )

        set_provider_bond_status(
            db_session,
            "p1",
            ProviderBondStatus.ACTIVE,
            amount=Decimal("5"),
            required_amount=Decimal("1"),
            bond_id="cb-local",
        )

        def _raise(self, provider_address: str) -> dict:
            raise NetworkError("chain unreachable")

        monkeypatch.setattr(BlockchainService, "list_provider_bonds", _raise)
        assert reconcile_provider_bond(db_session, "p1") is None

    def test_reconcile_ttl_skips_repeat_rpc(self, db_session, _chain_bonds, monkeypatch) -> None:
        """A fresh chain_verified_at suppresses the next RPC within the TTL."""
        from coordinator_api.contexts.market.domain.provider_bond import (
            ProviderBondStatus,
            reconcile_provider_bond,
            set_provider_bond_status,
        )

        _seed_chain_bond(_chain_bonds, PROVIDER_WALLET, "cb-ttl", "5")
        set_provider_bond_status(
            db_session,
            "p1",
            ProviderBondStatus.ACTIVE,
            amount=Decimal("5"),
            required_amount=Decimal("1"),
            bond_id="cb-ttl",
        )
        calls = {"n": 0}
        real = BlockchainService.list_provider_bonds

        def counting(self, provider_address: str) -> dict:
            calls["n"] += 1
            return real(self, provider_address)

        monkeypatch.setattr(BlockchainService, "list_provider_bonds", counting)
        assert reconcile_provider_bond(db_session, "p1") is not None
        assert reconcile_provider_bond(db_session, "p1") is not None
        assert calls["n"] == 1
