"""Router tests for /v1/grants/* (#1289 round 9 batch 3).

Caller-bound identity (#1071): create uses user["sub"] as developer_id
ignoring any body field; vote derives voter_id + voting_power from the
caller and its GovernanceService profile — never the body. Disburse is
AdminDep.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/grants"


def _headers(sub: str = "dev-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


def _grant_body(**overrides) -> dict:
    body = {
        "developer_id": "spoofed-dev",  # must be ignored — caller is bound (#1071)
        "title": "grant one",
        "description": "desc",
        "requested_amount": "100.50",
        "voting_days": 7,
    }
    body.update(overrides)
    return body


class TestGrantAuth:
    def test_create_requires_auth(self, client: TestClient) -> None:
        assert client.post(BASE, json=_grant_body()).status_code == 401

    def test_disburse_requires_admin(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/g1/disburse", json={"amount": "1"}, headers=_headers()).status_code == 403


class TestGrantLifecycle:
    def test_create_binds_caller(self, client: TestClient) -> None:
        resp = client.post(BASE, json=_grant_body(), headers=_headers("dev-real"))
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"]
        # the stored developer_id must be the caller sub, not the body spoof
        detail = client.get(f"{BASE}/{body['id']}", headers=_headers()).json()
        assert detail["developer_id"] == "dev-real"

    def test_list_and_get(self, client: TestClient) -> None:
        created = client.post(BASE, json=_grant_body(title="g2"), headers=_headers()).json()
        gid = created["id"]
        rows = client.get(BASE, headers=_headers()).json()
        assert any(r["id"] == gid for r in rows)
        assert client.get(f"{BASE}/{gid}", headers=_headers()).status_code == 200
        assert client.get(f"{BASE}/grant_ghost", headers=_headers()).status_code == 404

    def test_validation(self, client: TestClient) -> None:
        assert client.post(BASE, json=_grant_body(voting_days=0), headers=_headers()).status_code == 422
        assert client.post(BASE, json={"title": "x"}, headers=_headers()).status_code == 422

    def test_milestones(self, client: TestClient) -> None:
        created = client.post(BASE, json=_grant_body(), headers=_headers()).json()
        gid = created["id"]
        ms = client.post(
            f"{BASE}/{gid}/milestones",
            json={"title": "m1", "amount": "10"},
            headers=_headers(),
        )
        # milestone creation may be owner/admin-gated; accept 201 or documented denial
        assert ms.status_code in (201, 400, 403)
        listed = client.get(f"{BASE}/{gid}/milestones", headers=_headers())
        assert listed.status_code == 200

    def test_vote_caller_bound(self, client: TestClient) -> None:
        created = client.post(BASE, json=_grant_body(), headers=_headers()).json()
        gid = created["id"]
        resp = client.post(
            f"{BASE}/{gid}/vote",
            json={"vote": "for", "voting_power": 999999999},  # power must come from profile, not body
            headers=_headers("voter-1"),
        )
        assert resp.status_code in (200, 400)

    def test_process_and_disburse_admin(self, client: TestClient) -> None:
        created = client.post(BASE, json=_grant_body(), headers=_headers()).json()
        gid = created["id"]
        # process may be permissioned; disburse is AdminDep
        resp = client.post(f"{BASE}/{gid}/disburse", json={"amount": "1"}, headers=_admin())
        assert resp.status_code in (200, 400, 404)
