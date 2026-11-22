"""#2495 pins: delegation is frozen while any vote is open.

Pre-fix: ``delegate_votes`` moved stake between profiles at any time, so
one stake could be counted once per sock-puppet profile on the same
contest — vote, delegate, the delegatee votes again, re-delegate, repeat.
Votes snapshot ``effective_voting_power`` at cast time, so the freeze is
the guard that keeps one stake to one count per open vote.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from coordinator_api.contexts.governance.domain.economic_proposal import EconomicParameterProposal, EconomicProposalStatus
from coordinator_api.contexts.governance.domain.governance import (
    GovernanceProfile,
    Proposal,
    ProposalStatus,
    effective_voting_power,
)
from coordinator_api.contexts.governance.domain.grant import GrantProposal, GrantStatus
from coordinator_api.contexts.governance.services.governance_service import GovernanceService


def _profile(db, pid: str, power: float = 10.0) -> GovernanceProfile:
    p = GovernanceProfile(profile_id=pid, user_id=f"u-{pid}", voting_power=power)
    db.add(p)
    db.commit()
    return p


def _get(db, pid: str) -> GovernanceProfile:
    return db.exec(select(GovernanceProfile).where(GovernanceProfile.profile_id == pid)).one()


def _open_proposal(db, *, voted: bool = False) -> Proposal:
    now = datetime.now(UTC).replace(tzinfo=None)
    prop = Proposal(
        proposer_id="p0",
        title="t",
        description="d",
        status=ProposalStatus.ACTIVE,
        voting_starts=now - timedelta(hours=1),
        voting_ends=now + timedelta(days=1),
        votes_for=5.0 if voted else 0.0,
    )
    db.add(prop)
    db.commit()
    return prop


def _closed_proposal(db) -> Proposal:
    now = datetime.now(UTC).replace(tzinfo=None)
    prop = Proposal(
        proposer_id="p0",
        title="t",
        description="d",
        status=ProposalStatus.ACTIVE,
        voting_starts=now - timedelta(days=2),
        voting_ends=now - timedelta(hours=1),
    )
    db.add(prop)
    db.commit()
    return prop


def _open_grant(db, *, voted: bool = False) -> GrantProposal:
    grant = GrantProposal(
        developer_id="dev-1",
        title="g",
        description="d",
        status=GrantStatus.VOTING,
        voting_ends=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        votes_for=5.0 if voted else 0.0,
    )
    db.add(grant)
    db.commit()
    return grant


def _open_econ(db, *, voted: bool = False) -> EconomicParameterProposal:
    now = datetime.now(UTC).replace(tzinfo=None)
    prop = EconomicParameterProposal(
        proposer_id="p0",
        parameter_name="param",
        status=EconomicProposalStatus.SUBMITTED,
        voting_starts=now,
        voting_ends=now + timedelta(days=1),
        votes_for=5.0 if voted else 0.0,
    )
    db.add(prop)
    db.commit()
    return prop


def test_delegate_blocked_while_governance_vote_open(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d1")
    _profile(db_session, "e1")
    _open_proposal(db_session, voted=True)

    with pytest.raises(ValueError, match="delegation is locked"):
        svc.delegate_votes("d1", "e1")
    # nothing moved
    assert _get(db_session, "d1").delegate_to is None
    assert _get(db_session, "e1").delegated_power == 0.0


def test_delegate_blocked_while_grant_vote_open(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d2")
    _profile(db_session, "e2")
    _open_grant(db_session, voted=True)

    with pytest.raises(ValueError, match="delegation is locked"):
        svc.delegate_votes("d2", "e2")


def test_delegate_blocked_while_economic_vote_open(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d3")
    _profile(db_session, "e3")
    _open_econ(db_session, voted=True)

    with pytest.raises(ValueError, match="delegation is locked"):
        svc.delegate_votes("d3", "e3")


def test_delegate_allowed_when_votes_closed_or_absent(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d4")
    _profile(db_session, "e4")
    _closed_proposal(db_session)

    svc.delegate_votes("d4", "e4")
    assert _get(db_session, "d4").delegate_to == "e4"
    assert effective_voting_power(_get(db_session, "e4")) == 20.0


def test_redelegate_same_target_allowed_during_open_vote(db_session):
    """Re-affirming the current delegatee moves no stake — the freeze only
    blocks an actual move."""
    svc = GovernanceService(db_session)
    _profile(db_session, "d5")
    _profile(db_session, "e5")
    svc.delegate_votes("d5", "e5")
    _open_proposal(db_session, voted=True)

    svc.delegate_votes("d5", "e5")  # no-op path, must not raise
    assert _get(db_session, "d5").delegate_to == "e5"


def test_delegate_allowed_while_contests_unvoted(db_session):
    """#2512: an opened-but-unvoted contest freezes nothing — any user could
    otherwise lock delegation globally just by proposing. The freeze only
    engages once a contest's tally has counted stake."""
    svc = GovernanceService(db_session)
    _profile(db_session, "d6")
    _profile(db_session, "e6")
    _open_proposal(db_session)  # unvoted
    _open_grant(db_session)  # unvoted
    _open_econ(db_session)  # unvoted

    svc.delegate_votes("d6", "e6")
    assert _get(db_session, "d6").delegate_to == "e6"


def test_delegate_blocked_when_any_voted_contest_open(db_session):
    """#2512: one voted contest among several unvoted ones still freezes —
    counted stake must not move while its window is open."""
    svc = GovernanceService(db_session)
    _profile(db_session, "d7")
    _profile(db_session, "e7")
    _open_proposal(db_session)  # unvoted
    _open_grant(db_session, voted=True)
    _open_econ(db_session)  # unvoted

    with pytest.raises(ValueError, match="delegation is locked"):
        svc.delegate_votes("d7", "e7")
