"""Router tests for /v1/agents/security/* (#1289 round 9 batch 2).

Router-level AdminDep on the policy/audit/trust-score endpoints; the
matrix floor is ANY. Two endpoints are unauthenticated-at-router-level
stubs reachable by any JWT: GET /scan (fabricates a clean scan) and
GET /policies (hardcoded []) — the latter silently drops real policies
created via POST /policies, pinned strict-xfail (#1328).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_coordination.services.security import SecurityLevel

BASE = "/v1/agents/security"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


class TestAuthBoundary:
    def test_admin_dep_endpoints_reject_non_admin(self, client: TestClient) -> None:
        # audit-logs + trust-scores carry AdminDep -> client role 403
        assert client.get(f"{BASE}/audit-logs", headers=_headers()).status_code == 403
        assert client.get(f"{BASE}/trust-scores", headers=_headers()).status_code == 403
        assert client.get(f"{BASE}/audit-logs", headers=_admin()).status_code == 200
        assert client.get(f"{BASE}/trust-scores", headers=_admin()).status_code == 200

    def test_admin_dep_rejects_missing_token(self, client: TestClient) -> None:
        # AdminDep raises 401 with no credentials even with matrix off
        assert client.get(f"{BASE}/audit-logs").status_code == 401
        assert client.post(f"{BASE}/policies", params={"name": "x"}).status_code == 401

    def test_policy_list_is_open_stub(self, client: TestClient) -> None:
        # GET /policies has NO AdminDep and returns hardcoded [] (#1328) —
        # reachable by any caller in test mode; documented, not pinned
        assert client.get(f"{BASE}/policies", headers=_headers()).status_code == 200
        assert client.get(f"{BASE}/policies").status_code == 200

    def test_scan_reachable_by_any_jwt(self, client: TestClient) -> None:
        # matrix floor ANY — documented contract, not a defect per se
        assert client.get(f"{BASE}/scan", headers=_headers()).status_code == 200


class TestPolicyLifecycle:
    def _create(self, client: TestClient, name: str = "pol-1") -> dict:
        # params arrive as query args; policy_rules is the JSON body
        resp = client.post(
            f"{BASE}/policies",
            params={
                "name": name,
                "description": "desc",
                "security_level": SecurityLevel.INTERNAL.value,
            },
            json={"rule": "x"},
            headers=_admin(),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_create_policy(self, client: TestClient) -> None:
        body = self._create(client)
        assert body["name"] == "pol-1"
        assert body["id"]

    @pytest.mark.xfail(
        strict=True,
        reason="defect #1328: GET /policies is a hardcoded `return []` stub — policies created via POST are invisible to the list endpoint",
    )
    def test_list_policies_returns_created(self, client: TestClient) -> None:
        self._create(client, "pol-list-1")
        resp = client.get(f"{BASE}/policies", headers=_admin())
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "pol-list-1" in names

    def test_get_policy_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/policies/pol_ghost", headers=_admin()).status_code == 404

    def test_get_policy_roundtrip(self, client: TestClient) -> None:
        created = self._create(client, "pol-get-1")
        resp = client.get(f"{BASE}/policies/{created['id']}", headers=_admin())
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]


class TestAuditAndTrust:
    def test_audit_logs_empty_and_404(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/audit-logs", headers=_admin())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert client.get(f"{BASE}/audit-logs/audit_ghost", headers=_admin()).status_code == 404

    def test_trust_scores_empty(self, client: TestClient, db_session: Session) -> None:
        # seed a trust score row via the domain model, then list must return it
        from coordinator_api.contexts.agent_coordination.services.security import AgentTrustScore

        db_session.add(
            AgentTrustScore(
                entity_type="agent",
                entity_id="ag-t1",
                trust_score=42.0,
            )
        )
        db_session.commit()
        resp = client.get(f"{BASE}/trust-scores", params={"entity_id": "ag-t1"}, headers=_admin())
        assert resp.status_code == 200
        rows = resp.json()
        assert any(r["entity_id"] == "ag-t1" for r in rows)
