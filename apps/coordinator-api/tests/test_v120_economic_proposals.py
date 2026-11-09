"""Integration tests for v0.12.0 economic proposal endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token


def _auth_headers(client: TestClient) -> None:
    """Attach a valid JWT to the test client for economic proposal routes."""
    token = create_access_token("test_user", "client")
    client.headers = {"Authorization": f"Bearer {token}"}


def test_create_and_get_economic_proposal(client) -> None:
    """Economic proposals can be created and retrieved through the API."""
    _auth_headers(client)
    create_resp = client.post(
        "/v1/economic-proposals",
        json={
            "proposer_id": "agent-1",
            "parameter_name": "network_fee",
            "current_value": "1.0",
            "proposed_value": "2.0",
            "unit": "AITBC",
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["parameter_name"] == "network_fee"
    assert data["status"] == "submitted"

    get_resp = client.get(f"/v1/economic-proposals/{data['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == data["id"]


def test_vote_and_execute_economic_proposal(client, db_session) -> None:
    """Votes are recorded and a proposal can be executed after reaching threshold."""
    _auth_headers(client)
    # #1071: weight comes from the caller's profile — body voting_power is ignored.
    from coordinator_api.contexts.governance.services.governance_service import GovernanceService

    profile = GovernanceService(db_session).get_or_create_profile("test_user", 10.0)
    assert profile.voting_power == 10.0
    create_resp = client.post(
        "/v1/economic-proposals",
        json={
            "proposer_id": "agent-1",
            "parameter_name": "storage_fee",
            "current_value": "0.1",
            "proposed_value": "0.2",
        },
    )
    proposal_id = create_resp.json()["id"]

    vote_resp = client.post(
        f"/v1/economic-proposals/{proposal_id}/votes",
        json={"vote": "for", "voting_power": 10.0},
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["votes_for"] == 10.0

    # #1360: execution requires the voting window to be closed.
    from datetime import UTC, datetime, timedelta

    from coordinator_api.contexts.governance.domain.economic_proposal import EconomicParameterProposal

    proposal = db_session.get(EconomicParameterProposal, proposal_id)
    proposal.voting_ends = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db_session.add(proposal)
    db_session.commit()

    exec_resp = client.post(f"/v1/economic-proposals/{proposal_id}/execute")
    assert exec_resp.status_code == 200
    result = exec_resp.json()
    assert result["status"] == "executed"
    # SQLite Numeric preserves binary float precision; assert within tolerance.
    assert abs(Decimal(result["current_value"]) - Decimal("0.2")) < Decimal("0.0000000001")


def test_list_economic_proposals(client) -> None:
    """Listing returns created proposals."""
    _auth_headers(client)
    client.post(
        "/v1/economic-proposals",
        json={
            "proposer_id": "agent-1",
            "parameter_name": "lease_fee",
            "current_value": "0.5",
            "proposed_value": "0.6",
        },
    )
    resp = client.get("/v1/economic-proposals?proposer_id=test_user")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
