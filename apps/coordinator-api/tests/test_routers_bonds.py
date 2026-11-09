"""Router tests for /v1/market/providers/{id}/bonds* and /v1/market/bonds/{id} (#1289 round 9 batch 6).

Real ProviderBond domain + sqlite. require_auth accepts any valid JWT;
the floor (COORDINATOR_BOND_MIN_AMOUNT, default 1) is enforced on create:
amount >= required -> ACTIVE, else PENDING. Lock/release/slash are
status transitions that preserve amount/required_amount.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

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
    def test_create_below_floor_pending(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/providers/p1/bonds",
            json={"amount": "0.5", "required_amount": "0.1"},
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        # required_amount raised to the global floor (default 1)
        assert Decimal(body["required_amount"]) == Decimal("1")
        assert body["status"] == "pending"  # 0.5 < 1
        assert body["provider_id"] == "p1"
        assert body["bond_id"] == "bond-p1"

    def test_create_meeting_floor_active(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/providers/p1/bonds",
            json={"amount": "5", "required_amount": "2"},
            headers=_headers(),
        )
        body = resp.json()
        assert body["status"] == "active"
        assert Decimal(body["amount"]) == Decimal("5")

    def test_create_is_upsert(self, client: TestClient) -> None:
        client.post(f"{BASE}/providers/p1/bonds", json={"amount": "5"}, headers=_headers())
        resp = client.post(f"{BASE}/providers/p1/bonds", json={"amount": "9"}, headers=_headers())
        assert Decimal(resp.json()["amount"]) == Decimal("9")
        # still one record
        elig = client.get(f"{BASE}/providers/p1/eligibility", headers=_headers()).json()
        assert elig["eligible"] is True

    def test_eligibility_no_bond(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/providers/ghost/eligibility", headers=_headers())
        body = resp.json()
        assert body["eligible"] is False
        assert body["status"] == "pending"

    def test_get_bond_by_id_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/bonds/nope", headers=_headers()).status_code == 404

    def test_get_bond_by_id_roundtrip(self, client: TestClient) -> None:
        created = client.post(f"{BASE}/providers/p2/bonds", json={"amount": "3"}, headers=_headers()).json()
        resp = client.get(f"{BASE}/bonds/{created['id']}", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["provider_id"] == "p2"

    def test_lock_release_slash(self, client: TestClient) -> None:
        client.post(f"{BASE}/providers/p3/bonds", json={"amount": "5"}, headers=_headers())
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
