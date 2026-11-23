"""#2722: cross-chain reputation endpoints must report real values.

GET /v1/reputation/{agent}/cross-chain used to answer hard-coded
chain_count 1 / consistency_score 1.0 / "verified" for every agent, and
POST .../cross-chain/sync answered "completed" without doing anything.
Both now run the real CrossChainReputationEngine aggregation and report
the stored CrossChainReputationAggregation row.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token
from fastapi.testclient import TestClient

from coordinator_api.contexts.reputation.domain.reputation import AgentReputation, ReputationLevel

pytestmark = pytest.mark.unit

AGENT = "rep-agent-2722"
BASE = "/v1/reputation"


@pytest.fixture
def _reputation(db_session):
    db_session.add(
        AgentReputation(
            agent_id=AGENT,
            trust_score=750.0,
            reputation_level=ReputationLevel.ADVANCED,
            transaction_count=12,
            success_rate=91.5,
        )
    )
    db_session.commit()


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin-2722', 'admin')}"}


def test_cross_chain_reputation_reports_real_aggregation(client: TestClient, _reputation) -> None:
    response = client.get(f"{BASE}/{AGENT}/cross-chain")
    assert response.status_code == 200
    body = response.json()
    cross_chain = body["cross_chain"]
    # One AgentReputation row aggregates to chain 1 with the trust score.
    assert cross_chain["chain_count"] == 1
    assert cross_chain["active_chains"] == [1]
    assert cross_chain["chain_scores"]["1"] == pytest.approx(0.75)
    assert cross_chain["aggregated_score"] == pytest.approx(0.75)
    # Stored status is "pending" until verification runs — never "verified".
    assert cross_chain["verification_status"] == "pending"
    assert body["chain_reputations"]["1"]["trust_score"] == 750.0


def test_cross_chain_reputation_unknown_agent_404(client: TestClient) -> None:
    response = client.get(f"{BASE}/no-such-agent/cross-chain")
    assert response.status_code == 404


def test_cross_chain_sync_recomputes(client: TestClient, _reputation) -> None:
    response = client.post(f"{BASE}/{AGENT}/cross-chain/sync", headers=_admin())
    assert response.status_code == 200
    body = response.json()
    assert body["sync_status"] == "completed"
    assert body["chains_synced"] == [1]
    assert body["chain_count"] == 1
    assert body["aggregated_score"] == pytest.approx(0.75)


def test_cross_chain_sync_requires_admin(client: TestClient, _reputation) -> None:
    response = client.post(
        f"{BASE}/{AGENT}/cross-chain/sync",
        headers={"Authorization": f"Bearer {create_access_token('client-1', 'client')}"},
    )
    assert response.status_code == 403


def test_cross_chain_leaderboard_uses_stored_aggregation(client: TestClient, _reputation) -> None:
    # Populate the aggregation the way the engine does, then read the board.
    client.get(f"{BASE}/{AGENT}/cross-chain")
    response = client.get(f"{BASE}/cross-chain/leaderboard")
    assert response.status_code == 200
    agents = {a["agent_id"]: a for a in response.json()["agents"]}
    row = agents[AGENT]
    assert row["chain_count"] == 1
    assert row["verification_status"] == "pending"
    assert row["consistency_score"] == pytest.approx(1.0)
