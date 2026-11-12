"""#1878 pins: delegate_votes must move power, not copy it.

Pre-fix: delegate_votes set delegate_to and added voting_power to the new
delegatee's delegated_power without removing it from a previous delegatee
or neutralizing the delegator's own power — re-delegating multiplied
delegated_power without bound, and the delegator kept voting with their
own power too (effective = voting_power + delegated_power everywhere).
"""

from __future__ import annotations

from sqlmodel import select

from coordinator_api.contexts.governance.domain.governance import (
    GovernanceProfile,
    effective_voting_power,
)
from coordinator_api.contexts.governance.services.governance_service import GovernanceService


def _profile(db, pid: str, power: float) -> GovernanceProfile:
    p = GovernanceProfile(profile_id=pid, user_id=f"u-{pid}", voting_power=power)
    db.add(p)
    db.commit()
    return p


def _get(db, pid: str) -> GovernanceProfile:
    return db.exec(select(GovernanceProfile).where(GovernanceProfile.profile_id == pid)).one()


def test_delegate_moves_power_to_delegatee(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d1", 10.0)
    _profile(db_session, "e1", 1.0)

    svc.delegate_votes("d1", "e1")

    d = _get(db_session, "d1")
    e = _get(db_session, "e1")
    assert d.delegate_to == "e1"
    assert e.delegated_power == 10.0
    # delegator's own stake is parked — it must not also vote with it
    assert effective_voting_power(d) == 0.0
    assert effective_voting_power(e) == 11.0
    # conserved: stake 10 + delegatee own 1
    assert effective_voting_power(d) + effective_voting_power(e) == 11.0


def test_redelegate_moves_power_off_previous_delegatee(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d2", 10.0)
    _profile(db_session, "e2a", 0.0)
    _profile(db_session, "e2b", 0.0)

    svc.delegate_votes("d2", "e2a")
    svc.delegate_votes("d2", "e2b")

    a = _get(db_session, "e2a")
    b = _get(db_session, "e2b")
    d = _get(db_session, "d2")
    assert a.delegated_power == 0.0, "previous delegatee must lose the parked power"
    assert b.delegated_power == 10.0
    assert d.delegate_to == "e2b"
    # total parked power across the system is still exactly one copy
    assert a.delegated_power + b.delegated_power == 10.0


def test_redelegate_same_target_is_idempotent(db_session):
    svc = GovernanceService(db_session)
    _profile(db_session, "d3", 10.0)
    _profile(db_session, "e3", 0.0)

    svc.delegate_votes("d3", "e3")
    svc.delegate_votes("d3", "e3")

    e = _get(db_session, "e3")
    assert e.delegated_power == 10.0, "repeat delegation to same target must not stack"
