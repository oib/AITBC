"""Router tests for /v1/disputes/* (#1289 round 9 batch 4).

Real DisputeResolutionService (in-memory). Three real defects pinned:
- arbitrator identity hardcoded "arbitrator_001" -> only one vote can
  ever exist per dispute -> MIN_ARBITRATORS quorum unreachable
- arbitrator registration is unauthenticated (matrix ANY, address is a
  bare query param) — anyone can register any address
- submit_evidence hardcodes submitted_by="client" -> service rejects
  unless dispute.client is literally "client" -> evidence path broken
for real parties.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.governance.services.dispute_resolution as dr_mod
from coordinator_api.contexts.governance.services.dispute_resolution import init_dispute_service

BASE = "/v1/disputes"
CLIENT = "0x" + "aa" * 20
PROVIDER = "0x" + "bb" * 20


@pytest.fixture
def dispute_service():
    svc = init_dispute_service(None)
    yield svc
    dr_mod._dispute_service = None


def _file(client: TestClient, **over) -> dict:
    body = {"job_id": "job-1", "client": CLIENT, "provider": PROVIDER, "amount": 5000, "reason": "no delivery"}
    body.update(over)
    resp = client.post(f"{BASE}/file", json=body)
    assert resp.status_code == 200
    return resp.json()


class TestDisputeLifecycle:
    def test_health(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/health").json()["service"] == "disputes"

    def test_service_unavailable_without_init(self, client: TestClient) -> None:
        # no init_dispute_service in this test -> global is None -> 503
        assert client.get(f"{BASE}/").status_code == 503

    def test_file_and_get(self, client: TestClient, dispute_service) -> None:
        dispute = _file(client)
        did = dispute["dispute_id"]
        got = client.get(f"{BASE}/{did}")
        assert got.status_code == 200
        assert got.json()["job_id"] == "job-1"

    def test_list_filters(self, client: TestClient, dispute_service) -> None:
        _file(client)
        resp = client.get(f"{BASE}/", params={"party": CLIENT})
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_get_missing_404(self, client: TestClient, dispute_service) -> None:
        assert client.get(f"{BASE}/0xghost").status_code == 404

    def test_validation(self, client: TestClient, dispute_service) -> None:
        assert client.post(f"{BASE}/file", json={}).status_code == 422


class TestEvidenceDefect:
    @pytest.mark.xfail(
        strict=True,
        reason="#1333: submit_evidence hardcodes submitted_by='client' — service rejects "
        "any real client/provider address -> evidence endpoint always 400",
    )
    def test_submit_evidence_for_real_party(self, client: TestClient, dispute_service) -> None:
        dispute = _file(client)
        resp = client.post(
            f"{BASE}/evidence",
            json={
                "dispute_id": dispute["dispute_id"],
                "evidence_type": "log",
                "description": "proof",
                "ipfs_hash": "Qm...",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestArbitrationDefects:
    def _open_dispute(self, client: TestClient) -> str:
        return _file(client)["dispute_id"]

    @pytest.mark.xfail(
        strict=True,
        reason="#1334: cast_vote hardcodes arbitrator='arbitrator_001' — every caller votes "
        "as the same arbitrator; one-vote-per-arbitrator rule caps votes at 1 < MIN_ARBITRATORS=3, "
        "so no dispute can ever reach quorum/resolve",
    )
    def test_two_distinct_arbitrators_can_vote(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        # register the hardcoded identity, then a second caller tries to vote —
        # both are recorded under 'arbitrator_001', so the second is rejected
        client.post(f"{BASE}/arbitrators/register", params={"address": "arbitrator_001"})
        v1 = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "client_wins", "reasoning": "r", "stake_amount": 5000},
        )
        assert v1.status_code == 200
        v2 = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "provider_wins", "reasoning": "r", "stake_amount": 5000},
        )
        # distinct arbitrators should both be recordable; with the hardcoded
        # identity the second vote is a duplicate -> 400 -> quorum impossible
        assert v2.status_code == 200

    @pytest.mark.xfail(
        strict=True,
        reason="#1335: POST /arbitrators/register takes a bare address query param with no auth "
        "dep (matrix ANY) — anyone can register any address, incl. 'arbitrator_001'",
    )
    def test_arbitrator_registration_requires_identity(self, client: TestClient, dispute_service) -> None:
        # unauthenticated request must not be able to mint an arbitrator
        resp = client.post(f"{BASE}/arbitrators/register", params={"address": "attacker"})
        assert resp.status_code in (401, 403)

    def test_vote_requires_registered_arbitrator(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        # 'arbitrator_001' not registered -> service raises -> 400/403, never silent success
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "client_wins", "reasoning": "r", "stake_amount": 5000},
        )
        assert resp.status_code in (400, 403)

    def test_min_stake_enforced(self, client: TestClient, dispute_service) -> None:
        did = self._open_dispute(client)
        client.post(f"{BASE}/arbitrators/register", params={"address": "arbitrator_001"})
        resp = client.post(
            f"{BASE}/vote",
            json={"dispute_id": did, "outcome": "split", "reasoning": "r", "stake_amount": 1},
        )
        assert resp.status_code == 400
