"""#2694 pins: POST /v1/governance/proposals/{id}/vote resolves the governance
profile by user_id (the JWT sub), keys the vote by profile_id, and only
accepts votes while the proposal is ACTIVE and inside its voting window.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from coordinator_api.contexts.governance.domain.governance import (
    GovernanceProfile,
    Proposal,
    ProposalStatus,
    Vote,
    effective_voting_power,
)
from coordinator_api.contexts.governance.services.governance_service import GovernanceService


def _svc(db_session) -> GovernanceService:
    return GovernanceService(db_session)


def _proposal(db_session, **overrides) -> Proposal:
    now = datetime.now(UTC).replace(tzinfo=None)
    fields = {
        "proposer_id": "gov_proposer",
        "title": "t",
        "description": "d",
        "status": ProposalStatus.ACTIVE,
        "voting_starts": now - timedelta(hours=1),
        "voting_ends": now + timedelta(days=7),
    }
    fields.update(overrides)
    p = Proposal(**fields)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def test_vote_uses_profile_power_and_profile_id(db_session) -> None:
    profile = GovernanceProfile(user_id="alice-2694", voting_power=5.0)
    db_session.add(profile)
    db_session.commit()
    proposal = _proposal(db_session, proposer_id=profile.profile_id)

    vote = _svc(db_session).cast_governance_vote(proposal.proposal_id, "alice-2694", "for")

    assert vote.voter_id == profile.profile_id
    assert vote.voting_power_used == effective_voting_power(profile) == 5.0
    db_session.refresh(proposal)
    assert proposal.votes_for == 5.0
    assert profile.total_votes_cast == 1


def test_repeat_vote_rejected_per_profile(db_session) -> None:
    profile = GovernanceProfile(user_id="alice-2694", voting_power=5.0)
    db_session.add(profile)
    db_session.commit()
    proposal = _proposal(db_session, proposer_id=profile.profile_id)
    svc = _svc(db_session)
    svc.cast_governance_vote(proposal.proposal_id, "alice-2694", "for")
    with pytest.raises(ValueError, match="already voted"):
        svc.cast_governance_vote(proposal.proposal_id, "alice-2694", "against")


def test_vote_without_profile_records_zero_power(db_session) -> None:
    proposal = _proposal(db_session, proposer_id="gov_proposer")
    vote = _svc(db_session).cast_governance_vote(proposal.proposal_id, "ghost-2694", "for")
    assert vote.voter_id == "ghost-2694"
    assert vote.voting_power_used == 0.0


def test_vote_rejected_when_not_active(db_session) -> None:
    profile = GovernanceProfile(user_id="alice-2694", voting_power=5.0)
    db_session.add(profile)
    db_session.commit()
    proposal = _proposal(db_session, proposer_id=profile.profile_id, status=ProposalStatus.DRAFT)
    with pytest.raises(ValueError, match="not open for voting"):
        _svc(db_session).cast_governance_vote(proposal.proposal_id, "alice-2694", "for")


def test_vote_rejected_outside_window(db_session) -> None:
    profile = GovernanceProfile(user_id="alice-2694", voting_power=5.0)
    db_session.add(profile)
    db_session.commit()
    now = datetime.now(UTC).replace(tzinfo=None)
    proposal = _proposal(
        db_session,
        proposer_id=profile.profile_id,
        voting_starts=now - timedelta(days=2),
        voting_ends=now - timedelta(days=1),
    )
    with pytest.raises(ValueError, match="outside its voting window"):
        _svc(db_session).cast_governance_vote(proposal.proposal_id, "alice-2694", "for")


def test_no_vote_row_written_on_rejection(db_session) -> None:
    profile = GovernanceProfile(user_id="alice-2694", voting_power=5.0)
    db_session.add(profile)
    db_session.commit()
    proposal = _proposal(db_session, proposer_id=profile.profile_id, status=ProposalStatus.SUCCEEDED)
    with pytest.raises(ValueError):
        _svc(db_session).cast_governance_vote(proposal.proposal_id, "alice-2694", "for")
    rows = db_session.execute(select(Vote)).scalars().all()
    assert rows == []
