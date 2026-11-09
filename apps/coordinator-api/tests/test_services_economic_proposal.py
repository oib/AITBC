"""Coverage for EconomicProposalService (#1289 residual).

CRUD + vote tally + execute math on in-memory SQLite. #1360 lifecycle
guards are pinned as regression tests: votes only while the window is
open on votable statuses; execution only after the window closes on
executable statuses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session

from coordinator_api.contexts.governance.domain.economic_proposal import EconomicProposalStatus
from coordinator_api.contexts.governance.services.economic_proposal_service import EconomicProposalService


def _svc(db_session: Session) -> EconomicProposalService:
    return EconomicProposalService(db_session)


def _create(svc: EconomicProposalService, **kw):
    args = {
        "proposer_id": "proposer-1",
        "parameter_name": "block_reward",
        "current_value": Decimal("10"),
        "proposed_value": Decimal("12"),
        "voting_days": 7,
    }
    args.update(kw)
    return svc.create_proposal(**args)


def _close_window(db_session: Session, proposal) -> None:
    """Move voting_ends into the past so execute guards pass."""
    proposal.voting_ends = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db_session.add(proposal)
    db_session.commit()


# ---------------------------------------------------------------------------
# Passing pins
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_proposal_defaults(db_session: Session):
    p = _create(_svc(db_session))
    assert p.status == EconomicProposalStatus.SUBMITTED
    assert p.current_value == Decimal("10")
    assert p.proposed_value == Decimal("12")
    assert p.voting_ends > p.voting_starts
    assert p.quorum == 0.0
    assert p.passing_threshold == 0.5


@pytest.mark.unit
def test_get_and_list_proposals(db_session: Session):
    svc = _svc(db_session)
    p1 = _create(svc, parameter_name="alpha")
    _create(svc, parameter_name="beta", proposer_id="proposer-2")
    assert svc.get_proposal(p1.id).parameter_name == "alpha"
    assert svc.get_proposal("missing") is None
    assert len(svc.list_proposals()) == 2
    assert [p.parameter_name for p in svc.list_proposals(proposer_id="proposer-2")] == ["beta"]
    assert len(svc.list_proposals(parameter_name="alpha", limit=1)) == 1


@pytest.mark.unit
def test_vote_tallies(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "for", voting_power=3.0)
    svc.vote(p.id, "against", voting_power=1.0)
    svc.vote(p.id, "abstain", voting_power=0.5)
    refreshed = svc.get_proposal(p.id)
    assert refreshed.votes_for == 3.0
    assert refreshed.votes_against == 1.0
    assert refreshed.votes_abstain == 0.5


@pytest.mark.unit
def test_vote_normalizes_case_and_whitespace(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "  FOR  ", voting_power=1.0)
    assert svc.get_proposal(p.id).votes_for == 1.0


@pytest.mark.unit
def test_vote_unknown_proposal_raises(db_session: Session):
    with pytest.raises(ValueError, match="not found"):
        _svc(db_session).vote("missing", "for")


@pytest.mark.unit
def test_vote_invalid_value_raises(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    with pytest.raises(ValueError, match="invalid vote"):
        svc.vote(p.id, "maybe")


@pytest.mark.unit
def test_execute_moves_proposed_to_current(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "for", voting_power=10.0)
    svc.vote(p.id, "against", voting_power=2.0)
    _close_window(db_session, p)
    result = svc.execute_proposal(p.id)
    assert result.status == EconomicProposalStatus.EXECUTED
    assert result.current_value == Decimal("12")
    assert result.executed_at is not None


@pytest.mark.unit
def test_execute_rejected_below_threshold(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    p = svc.get_proposal(p.id)
    svc.vote(p.id, "for", voting_power=1.0)
    svc.vote(p.id, "against", voting_power=9.0)
    _close_window(db_session, p)
    result = svc.execute_proposal(p.id)
    assert result.status == EconomicProposalStatus.REJECTED
    assert result.current_value == Decimal("10")  # unchanged
    assert result.executed_at is None


@pytest.mark.unit
def test_execute_no_votes_raises(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    _close_window(db_session, p)
    with pytest.raises(ValueError, match="no votes"):
        svc.execute_proposal(p.id)


@pytest.mark.unit
def test_execute_below_quorum_raises(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    p.quorum = 100.0
    db_session.add(p)
    db_session.commit()
    svc.vote(p.id, "for", voting_power=10.0)
    _close_window(db_session, svc.get_proposal(p.id))
    with pytest.raises(ValueError, match="quorum"):
        svc.execute_proposal(p.id)


# ---------------------------------------------------------------------------
# Regression pins — #1360 lifecycle guards
# ---------------------------------------------------------------------------


def test_vote_rejected_on_executed_proposal(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "for", voting_power=10.0)
    _close_window(db_session, p)
    svc.execute_proposal(p.id)
    with pytest.raises(ValueError):
        svc.vote(p.id, "against", voting_power=100.0)


def test_vote_rejected_after_voting_window(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc, voting_days=1)
    p.voting_ends = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    db_session.add(p)
    db_session.commit()
    with pytest.raises(ValueError):
        svc.vote(p.id, "for", voting_power=1.0)


def test_execute_rejected_on_terminal_proposal(db_session: Session):
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "for", voting_power=10.0)
    _close_window(db_session, p)
    svc.execute_proposal(p.id)
    first_exec = svc.get_proposal(p.id).executed_at
    with pytest.raises(ValueError):
        svc.vote(p.id, "for", voting_power=1.0)  # tallies frozen post-execution
    with pytest.raises(ValueError):
        svc.execute_proposal(p.id)
    assert svc.get_proposal(p.id).executed_at == first_exec


def test_execute_rejected_while_voting_open(db_session: Session):
    # #1360 defect 3: execution must wait for the window to close.
    svc = _svc(db_session)
    p = _create(svc)
    svc.vote(p.id, "for", voting_power=10.0)
    with pytest.raises(ValueError, match="voting window"):
        svc.execute_proposal(p.id)
