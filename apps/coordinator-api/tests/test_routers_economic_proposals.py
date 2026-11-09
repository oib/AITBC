"""Tests for /v1/economic-proposals/* — auth, caller-bound proposer, vote/execute (#1289 round 4).

Real ``EconomicProposalService`` + ``GovernanceService`` on the in-memory
session. Pins the #1071 contract (proposer/voting power come from the JWT,
not the body) and the vote→execute lifecycle including the quorum guard.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.governance.domain.economic_proposal import (
    EconomicParameterProposal,
    EconomicProposalStatus,
)

BASE = "/v1/economic-proposals"


def _headers(sub: str = "user-a", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


def _client() -> dict[str, str]:
    return _headers("client-1", "client")


def _create_payload(**over: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "proposer_id": "spoofed-user",
        "parameter_name": "block_reward",
        "unit": "AIT",
        "current_value": "1.0",
        "proposed_value": "1.5",
        "voting_days": 7,
    }
    payload.update(over)
    return payload


def _seed_proposal(
    session: Session,
    proposer_id: str = "user-a",
    parameter_name: str = "fee",
    status: EconomicProposalStatus = EconomicProposalStatus.SUBMITTED,
    **kwargs: object,
) -> EconomicParameterProposal:
    p = EconomicParameterProposal(
        proposer_id=proposer_id,
        parameter_name=parameter_name,
        current_value=Decimal("1.0"),
        proposed_value=Decimal("2.0"),
        status=status,
        **kwargs,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


class TestAuth:
    def test_no_token_rejected(self, client: TestClient) -> None:
        assert client.get(BASE).status_code == 401
        assert client.post(BASE, json=_create_payload()).status_code == 401
        assert client.post(f"{BASE}/x/votes", json={"vote": "for"}).status_code == 401

    def test_client_token_accepted_for_reads(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(db_session)
        resp = client.get(f"{BASE}/{p.id}", headers=_client())
        assert resp.status_code == 200


class TestCreateProposal:
    def test_proposer_comes_from_jwt_not_body(self, client: TestClient, db_session: Session) -> None:
        resp = client.post(BASE, json=_create_payload(), headers=_client())
        assert resp.status_code == 201
        data = resp.json()
        # body said "spoofed-user"; the JWT sub must win (#1071)
        assert data["proposer_id"] == "client-1"
        row = db_session.get(EconomicParameterProposal, data["id"])
        assert row is not None and row.proposer_id == "client-1"
        assert row.status == EconomicProposalStatus.SUBMITTED

    def test_voting_window_set(self, client: TestClient) -> None:
        resp = client.post(BASE, json=_create_payload(voting_days=3), headers=_client())
        assert resp.status_code == 201
        data = resp.json()
        assert data["voting_starts"] is not None and data["voting_ends"] is not None


class TestGetAndList:
    def test_get_found(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(db_session)
        resp = client.get(f"{BASE}/{p.id}", headers=_admin())
        assert resp.status_code == 200
        assert resp.json()["id"] == p.id

    def test_get_missing_404(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/nope", headers=_admin())
        assert resp.status_code == 404

    def test_list_filters(self, client: TestClient, db_session: Session) -> None:
        _seed_proposal(db_session, proposer_id="user-a", parameter_name="alpha")
        _seed_proposal(db_session, proposer_id="user-b", parameter_name="beta")
        resp = client.get(BASE, params={"proposer_id": "user-a"}, headers=_admin())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1 and data[0]["parameter_name"] == "alpha"
        resp = client.get(BASE, params={"parameter_name": "beta"}, headers=_admin())
        assert [p["parameter_name"] for p in resp.json()] == ["beta"]

    def test_list_limit_bounds(self, client: TestClient) -> None:
        assert client.get(BASE, params={"limit": 0}, headers=_admin()).status_code == 422
        assert client.get(BASE, params={"limit": 5000}, headers=_admin()).status_code == 422


class TestVote:
    def test_invalid_vote_400(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(db_session)
        resp = client.post(f"{BASE}/{p.id}/votes", json={"vote": "maybe"}, headers=_client())
        assert resp.status_code == 400

    def test_vote_accumulates_power(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(db_session)
        # default profile voting_power is 0 -> vote accepted but adds nothing
        resp = client.post(f"{BASE}/{p.id}/votes", json={"vote": "for"}, headers=_client())
        assert resp.status_code == 200
        db_session.expire_all()
        row = db_session.get(EconomicParameterProposal, p.id)
        assert row is not None and row.votes_for == 0.0

    def test_vote_missing_proposal_400(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/nope/votes", json={"vote": "for"}, headers=_client())
        assert resp.status_code == 400


class TestExecute:
    def test_execute_marks_executed(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(
            db_session,
            votes_for=10.0,
            votes_against=2.0,
            quorum=1.0,
            passing_threshold=0.5,
        )
        resp = client.post(f"{BASE}/{p.id}/execute", headers=_admin())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "executed"
        # proposed_value becomes current_value
        assert Decimal(data["current_value"]) == Decimal("2.0")

    def test_execute_below_quorum_400(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(db_session, votes_for=1.0, quorum=100.0)
        resp = client.post(f"{BASE}/{p.id}/execute", headers=_admin())
        assert resp.status_code == 400
        assert "quorum" in resp.json()["detail"].lower()

    def test_execute_rejected_when_threshold_missed(self, client: TestClient, db_session: Session) -> None:
        p = _seed_proposal(
            db_session,
            votes_for=1.0,
            votes_against=9.0,
            quorum=1.0,
            passing_threshold=0.5,
        )
        resp = client.post(f"{BASE}/{p.id}/execute", headers=_admin())
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_execute_zero_votes_division_guard(self, client: TestClient, db_session: Session) -> None:
        """Zero-total-vote proposals must be rejected with 400, not 500 —
        previously votes_for/total_votes raised ZeroDivisionError (#1313)."""
        p = _seed_proposal(db_session, votes_for=0.0, votes_against=0.0, votes_abstain=0.0, quorum=0.0)
        resp = client.post(f"{BASE}/{p.id}/execute", headers=_admin())
        assert resp.status_code == 400
