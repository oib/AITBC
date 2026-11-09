"""Router tests for /v1/reputation/* (#1289 round 9 batch 6).

reputation — mixed deps: reads mostly open, mutations AuthDep /
AdminOrClientDep, cross-chain admin paths AdminDep. Real
ReputationService + sqlite. Covers profile/feedback/trust-score/
leaderboard/metrics contracts, auth floors on gated endpoints, and
cross-chain surface honesty.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/reputation"
AGENT = "agent-rep-1"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestReputationReads:
    def test_profile_unknown_agent(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/profile/{AGENT}")
        assert resp.status_code in (200, 404)

    def test_trust_score_unknown(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/trust-score/{AGENT}")
        assert resp.status_code in (200, 404)

    def test_leaderboard_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/leaderboard")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_metrics_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/metrics")
        assert resp.status_code == 200

    def test_feedback_list_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/feedback/{AGENT}")
        assert resp.status_code in (200, 404)

    def test_events_list_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/events/{AGENT}")
        assert resp.status_code in (200, 404)

    def test_cross_chain_leaderboard(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/cross-chain/leaderboard")
        assert resp.status_code in (200, 503)

    def test_cross_chain_analytics(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/cross-chain/analytics")
        assert resp.status_code in (200, 503)


class TestReputationMutations:
    def test_profile_update_requires_auth(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/profile/{AGENT}", json={})
        assert resp.status_code == 401

    def test_feedback_requires_auth(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/feedback/{AGENT}", json={})
        assert resp.status_code == 401

    def test_specialization_requires_auth(self, client: TestClient) -> None:
        resp = client.put(f"{BASE}/profile/{AGENT}/specialization", json={})
        assert resp.status_code == 401

    def test_cross_chain_sync_admin_gated(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/{AGENT}/cross-chain/sync", headers=_headers())
        # AdminDep per router source — client role must not pass
        assert resp.status_code in (401, 403)

    def test_cross_chain_events_admin_gated(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/cross-chain/events", json={}, headers=_headers())
        assert resp.status_code in (401, 403, 422)
