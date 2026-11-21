"""Router tests for /v1/reputation/* (#1289 round 9 batch 6).

reputation — mixed deps: reads mostly open, mutations AuthDep /
AdminOrClientDep, cross-chain admin paths AdminDep. Real
ReputationService + sqlite. Covers profile/feedback/trust-score/
leaderboard/metrics contracts, auth floors on gated endpoints, and
cross-chain surface honesty.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.reputation.domain.reputation import AgentReputation, ReputationLevel

BASE = "/v1/reputation"
AGENT = "agent-rep-1"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestReputationReads:
    def test_profile_unknown_agent(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/profile/{AGENT}")
        assert resp.status_code in (200, 404)

    def test_trust_score_unknown(self, client: TestClient) -> None:
        # #2406: no fabricated mid-scale composite — same honest 404 as profile.
        resp = client.get(f"{BASE}/trust-score/{AGENT}")
        assert resp.status_code == 404

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


def _seed_profile(db_session: Session, agent_id: str = AGENT, **overrides: object) -> AgentReputation:
    """Seed an AgentReputation row with deliberately stale headline columns.

    trust_score=111 / level=beginner are decoys: every reputation read must
    report the live composite from TrustScoreCalculator instead (#2406).
    """
    fields: dict[str, object] = {
        "agent_id": agent_id,
        "trust_score": 111.0,
        "reputation_level": ReputationLevel.BEGINNER,
        "performance_rating": 4.0,
        "reliability_score": 80.0,
        "community_rating": 4.5,
        "total_earnings": Decimal("5.0"),
        "transaction_count": 10,
        "success_rate": 90.0,
        "jobs_completed": 9,
        "jobs_failed": 1,
        "average_response_time": 1234.5,
        "uptime_percentage": 99.0,
        "dispute_count": 0,
        "certifications": ["cert-a"],
        "specialization_tags": ["tag-a"],
        "geographic_region": "EU",
    }
    fields.update(overrides)
    rep = AgentReputation(**fields)  # type: ignore[arg-type]
    db_session.add(rep)
    db_session.commit()
    return rep


class TestReputationConsistency:
    """#2406: profile / trust-score / leaderboard report ONE composite score."""

    def test_no_profile_agrees_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/profile/{AGENT}").status_code == 404
        assert client.get(f"{BASE}/trust-score/{AGENT}").status_code == 404
        board = client.get(f"{BASE}/leaderboard").json()
        assert all(entry["agent_id"] != AGENT for entry in board)

    def test_same_agent_same_score_across_reads(self, client: TestClient, db_session: Session) -> None:
        _seed_profile(db_session)
        profile = client.get(f"{BASE}/profile/{AGENT}").json()
        breakdown = client.get(f"{BASE}/trust-score/{AGENT}").json()
        board = client.get(f"{BASE}/leaderboard").json()
        entry = next(e for e in board if e["agent_id"] == AGENT)

        assert profile["trust_score"] == pytest.approx(breakdown["composite_score"])
        assert entry["trust_score"] == pytest.approx(breakdown["composite_score"])
        assert profile["reputation_level"] == breakdown["reputation_level"] == entry["reputation_level"]
        # The stale stored columns must not leak into any read: stored level
        # was the "beginner" decoy, the live composite lands "intermediate".
        assert profile["trust_score"] != pytest.approx(111.0)
        assert breakdown["reputation_level"] == "intermediate"

    def test_average_response_time_unit(self, client: TestClient, db_session: Session) -> None:
        _seed_profile(db_session)
        profile = client.get(f"{BASE}/profile/{AGENT}").json()
        assert profile["average_response_time"] == pytest.approx(1234.5)
        assert profile["average_response_time_unit"] == "ms"
