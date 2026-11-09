"""Router tests for /v1/disputes/* (#1289 round 9 batch 4; #1333/#1334/#1335 fixes).

Real DisputeResolutionService (in-memory). Caller identity is now
bound to the JWT subject on every mutating endpoint:
- file: filed_by = user["sub"] (was body-claimed req.client)
- evidence: submitted_by = user["sub"], service enforces party membership
- vote: arbitrator = user["sub"] — distinct callers get distinct votes,
  so MIN_ARBITRATORS quorum is reachable
- arbitrators/register: AuthDep + self-registration only (address must
  equal the caller's sub)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.governance.services.dispute_resolution as dr_mod
from coordinator_api.contexts.governance.services.dispute_resolution import init_dispute_service
from aitbc.auth import create_access_token

BASE = "/v1/disputes"
CLIENT_SUB = "client-sub-1"
PROVIDER_SUB = "provider-sub-1"
ARB1 = "arb-1"
ARB2 = "arb-2"
ARB3 = "arb-3"


def _headers(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


@pytest.fixture
def dispute_service():
    # app startup already ran _init_dispute_service(get_session); swap in a
    # fresh in-memory service per test and restore the app-level one after
    original = dr_mod._dispute_service
    svc = init_dispute_service(None)
    yield svc
    dr_mod._dispute_service = original


def _file(client: TestClient, sub: str = CLIENT_SUB, **over) -> dict:
    body = {
        "job_id": "job-1",
        "client": CLIENT_SUB,
        "provider": PROVIDER_SUB,
        "amount": 5000,
        "reason": "no delivery",
    }
    body.update(over)
    resp = client.post(f"{BASE}/file", json=body, headers=_headers(sub))
    assert resp.status_code == 200
    return resp.json()


class TestDisputeLifecycle:
    def test_health(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/health").json()["service"] == "disputes"

    def test_list_empty_service(self, client: TestClient, dispute_service) -> None:
        resp = client.get(f"{BASE}/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_file_and_get(self, client: TestClient, dispute_service) -> None:
        dispute = _file(client)
        did = dispute["dispute_id"]
        got = client.get(f"{BASE}/{did}")
        assert got.status_code == 200
        assert got.json()["job_id"] == "job-1"

    def test_list_filters(self, client: TestClient, dispute_service) -> None:
        _file(client)
        resp = client.get(f"{BASE}/", params={"party": CLIENT_SUB})
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_get_missing_404(self, client: TestClient, dispute_service) -> None:
        assert client.get(f"{BASE}/0xghost").status_code == 404

    def test_validation(self, client: TestClient, dispute_service) -> None:
        assert client.post(f"{BASE}/file", json={}, headers=_headers(CLIENT_SUB)).status_code == 422

    def test_file_requires_auth(self, client: TestClient, dispute_service) -> None:
        body = {"job_id": "j", "client": CLIENT_SUB, "provider": PROVIDER_SUB, "amount": 1, "reason": "r"}
        assert client.post(f"{BASE}/file", json=body).status_code == 401


class TestEvidenceBinding:
    def test_submit_evidence_as_client_party(self, client: TestClient, dispute_service) -> None:
        dispute = _file(client)
        resp = client.post(
            f"{BASE}/evidence",
            json={
                "dispute_id": dispute["dispute_id"],
                "evidence_type": "log",
                "description": "proof",
                "ipfs_hash": "Qm...",
            },
            headers=_headers(CLIENT_SUB),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_submit_evidence_non_party_rejected(self, client: TestClient, dispute_service) -> None:
        dispute = _file(client)
        resp = client.post(
            f"{BASE}/evidence",
            json={"dispute_id": dispute["dispute_id"], "evidence_type": "log", "description": "x"},
            headers=_headers("random-sub"),
        )
        assert resp.status_code == 400

    def test_evidence_requires_auth(self, client: TestClient, dispute_service) -> None:
        resp = client.post(
            f"{BASE}/evidence",
            json={"dispute_id": "d", "evidence_type": "log", "description": "x"},
        )
        assert resp.status_code == 401


class TestArbitration:
    def _open_dispute(self, client: TestClient) -> str:
        return _file(client)["dispute_id"]

    def _register(self, client: TestClient, sub: str, address: str | None = None) -> int:
        return client.post(
            f"{BASE}/arbitrators/register", params={"address": address or sub}, headers=_headers(sub)
        ).status_code

    def _vote(self, client: TestClient, sub: str, did: str, outcome: str = "client_wins") -> int:
        return client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": outcome, "reasoning": "r", "stake_amount": 5000},
            headers=_headers(sub),
        ).status_code

    def test_distinct_arbitrators_reach_quorum(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        for arb in (ARB1, ARB2, ARB3):
            assert self._register(client, arb) == 200
        assert self._vote(client, ARB1, did) == 200
        assert self._vote(client, ARB2, did, "provider_wins") == 200
        assert self._vote(client, ARB3, did, "split") == 200
        # 3 votes = MIN_ARBITRATORS -> dispute resolves
        got = client.get(f"{BASE}/{did}").json()
        assert got["status"] == "resolved"

    def test_same_arbitrator_cannot_vote_twice(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        self._register(client, ARB1)
        assert self._vote(client, ARB1, did) == 200
        assert self._vote(client, ARB1, did, "provider_wins") == 400

    def test_arbitrator_registration_requires_auth(self, client: TestClient, dispute_service) -> None:
        resp = client.post(f"{BASE}/arbitrators/register", params={"address": "attacker"})
        assert resp.status_code == 401

    def test_arbitrator_cannot_register_other_identity(self, client: TestClient, dispute_service) -> None:
        resp = client.post(f"{BASE}/arbitrators/register", params={"address": "victim"}, headers=_headers("attacker"))
        assert resp.status_code == 403

    def test_vote_requires_registered_arbitrator(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        assert self._vote(client, "unregistered", did) in (400, 403)

    def test_min_stake_enforced(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        self._register(client, ARB1)
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "split", "reasoning": "r", "stake_amount": 1},
            headers=_headers(ARB1),
        )
        assert resp.status_code == 400

    def test_vote_requires_auth(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "client_wins", "reasoning": "r", "stake_amount": 5000},
        )
        assert resp.status_code == 401
