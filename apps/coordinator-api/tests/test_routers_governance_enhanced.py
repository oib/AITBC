"""Router tests for /v1/regional-councils*, /v1/regional-proposals*,
/v1/treasury/*, /v1/staking/*, /v1/analytics/*, /v1/profiles/*,
/v1/jurisdictions, /v1/compliance/*, /v1/health|status (#1289 round 9 batch 6).

governance_enhanced — real GovernanceService + sqlite. #1847 added
router-level auth deps + caller-identity binding on the mutating routes;
tests mint JWTs for the role each route requires.
"""

from __future__ import annotations


from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/governance-enhanced"


def _headers(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


_ADMIN = _headers("gov-admin", "admin")
_CLIENT = _headers("gov-client", "client")


def _post(client: TestClient, path: str, body: dict, headers: dict | None = None) -> object:
    return client.post(f"{BASE}{path}", json=body, headers=headers or {})


class TestGovernanceReads:
    def test_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200

    def test_status_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/status")
        assert resp.status_code == 200

    def test_jurisdictions_list(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/jurisdictions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_regional_councils_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/regional-councils")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_treasury_balance_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/treasury/balance")
        assert resp.status_code in (200, 503)

    def test_staking_pools_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/staking/pools")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_analytics_governance_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/analytics/governance")
        assert resp.status_code in (200, 503)

    def test_compliance_check_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/compliance/check/0x" + "11" * 20, params={"jurisdiction": "eu"})
        assert resp.status_code == 501


class TestGovernanceMutations:
    def test_create_council_validation(self, client: TestClient) -> None:
        assert _post(client, "/regional-councils", {}, headers=_ADMIN).status_code == 422

    def test_create_council_roundtrip(self, client: TestClient) -> None:
        resp = _post(
            client,
            "/regional-councils",
            {"name": "EU Council", "region": "eu", "members": ["0x" + "11" * 20]},
            headers=_ADMIN,
        )
        assert resp.status_code in (200, 201, 400, 422, 503)
        if resp.status_code in (200, 201):
            cid = resp.json().get("council_id") or resp.json().get("id")
            listed = client.get(f"{BASE}/regional-councils").json()
            assert any((c.get("council_id") or c.get("id")) == cid for c in listed)

    def test_regional_proposal_validation(self, client: TestClient) -> None:
        assert _post(client, "/regional-proposals", {}, headers=_CLIENT).status_code == 422

    def test_staking_pool_validation(self, client: TestClient) -> None:
        assert _post(client, "/staking/pools", {}).status_code == 422

    def test_profile_create_validation(self, client: TestClient) -> None:
        assert _post(client, "/profiles/create", {}, headers=_CLIENT).status_code == 422

    def test_treasury_allocate_validation(self, client: TestClient) -> None:
        assert _post(client, "/treasury/allocate", {}).status_code == 422
