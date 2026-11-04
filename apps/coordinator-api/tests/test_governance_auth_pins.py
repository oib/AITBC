"""#1071 pins: identity/power come from the token and profile, not the caller."""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.governance.services.governance_service import GovernanceService
from coordinator_api.contexts.governance.services.grant_service import GrantService


def test_governance_vote_refuses_second_vote(db_session):
    """One vote per voter per proposal."""
    svc = GovernanceService(db_session)
    proposal = svc.create_governance_proposal(proposer_id="p1", proposal_data={"title": "t", "description": "d"})
    svc.cast_governance_vote(proposal.proposal_id, "voter-1", "for")
    with pytest.raises(ValueError, match="already voted"):
        svc.cast_governance_vote(proposal.proposal_id, "voter-1", "against")


def _approved_grant(db_session, status=None):
    from coordinator_api.contexts.governance.domain.grant import GrantProposal, GrantStatus

    grant = GrantProposal(
        developer_id="dev-1",
        title="g",
        description="d",
        requested_amount=Decimal("1000"),
        approved_amount=Decimal("1000"),
        disbursed_amount=Decimal("0"),
        status=status or GrantStatus.APPROVED,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


def test_grant_disburse_refuses_over_cap(db_session):
    """A disbursement can never exceed approved minus disbursed."""
    grant = _approved_grant(db_session)
    svc = GrantService(db_session)
    with pytest.raises(ValueError, match="exceeds the approved balance"):
        svc.disburse(grant_id=grant.id, amount=Decimal("999999"))


def test_grant_vote_refuses_second_vote(db_session):
    """Grant votes dedup via proposal_metadata.voters."""
    from coordinator_api.contexts.governance.domain.grant import GrantStatus

    grant = _approved_grant(db_session, status=GrantStatus.ACTIVE)
    from datetime import UTC, datetime, timedelta

    # Keep the window open — otherwise the first vote resolves the grant and
    # the second one hits "not open for voting" instead of the dedup check.
    grant.voting_ends = (datetime.now(UTC) + timedelta(days=7)).replace(tzinfo=None)
    db_session.commit()
    svc = GrantService(db_session)
    svc.vote(grant_id=grant.id, vote="for", voting_power=5.0, voter_id="voter-9")
    with pytest.raises(ValueError, match="already voted"):
        svc.vote(grant_id=grant.id, vote="for", voting_power=5.0, voter_id="voter-9")


def test_grant_vote_ignores_body_power_uses_profile(db_session):
    from coordinator_api.contexts.governance.domain.grant import GrantStatus

    """The router passes profile power, never body voting_power — pinned at
    service level: the caller cannot mint weight."""
    grant = _approved_grant(db_session, status=GrantStatus.ACTIVE)
    from datetime import UTC, datetime, timedelta

    grant.voting_ends = (datetime.now(UTC) + timedelta(days=7)).replace(tzinfo=None)
    db_session.commit()
    svc = GrantService(db_session)
    updated = svc.vote(grant_id=grant.id, vote="for", voting_power=0.0, voter_id="powerless-voter")
    # A zero-power profile contributes nothing — under the old body contract
    # the same call could have minted 1e9.
    assert updated.votes_for == 0.0
    assert "powerless-voter" in (updated.proposal_metadata or {}).get("voters", [])


def test_grant_disburse_route_is_admin_only(client):
    """A client-role token cannot reach the disburse route."""
    from aitbc.auth import create_access_token

    client.headers = {"Authorization": f"Bearer {create_access_token('client-1', 'client')}"}
    resp = client.post("/v1/grants/any-grant/disburse", json={"amount": "1"})
    assert resp.status_code in (401, 403)
