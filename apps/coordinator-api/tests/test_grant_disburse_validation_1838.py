"""#1838: grant disburse validation + process_grant state guard.

- ``disburse`` accepted non-positive amounts: a negative disburse_amount
  passed the balance check and CAS predicate, DECREASING disbursed_amount
  and growing headroom; zero stamped executed_at / flipped ACTIVE free.
- The milestone path let a caller-supplied ``amount`` override
  ``milestone.amount`` — one approved small milestone could drain the
  whole grant in a single call.
- ``process_grant`` accepted ACTIVE grants and ``_check_resolution``
  rewrote ``approved_amount``/regressed status on re-resolution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.developer.schemas.developer import DeveloperCreate
from coordinator_api.contexts.developer.services.developer_service import DeveloperService
from coordinator_api.contexts.governance.domain.grant import GrantProposal, GrantStatus, MilestoneStatus
from coordinator_api.contexts.governance.services.grant_service import GrantService


def _developer(session: Session) -> str:
    dev = DeveloperService(session).register(DeveloperCreate(wallet_address="0x" + "ef" * 20, name="Val Dev"))
    return dev.id


def _approved_grant(session: Session, svc: GrantService, dev_id: str, amount: str = "100") -> GrantProposal:
    grant = svc.create_grant(dev_id, "Val Grant", "desc", amount, voting_days=1)
    svc.vote(grant.id, "for", 10.0, voter_id="seed")
    grant.voting_ends = datetime.now(UTC) - timedelta(seconds=1)
    session.add(grant)
    session.commit()
    return svc.process_grant(grant.id)


def _fresh(session: Session, grant_id: str) -> GrantProposal:
    session.expire_all()
    return session.execute(select(GrantProposal).where(GrantProposal.id == grant_id)).scalar_one()


@pytest.mark.unit
def test_disburse_rejects_negative_amount(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    with pytest.raises(ValueError, match="positive"):
        svc.disburse(grant.id, amount="-50")
    assert _fresh(db_session, grant.id).disbursed_amount == Decimal("0")


@pytest.mark.unit
def test_disburse_rejects_zero_amount(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    with pytest.raises(ValueError, match="positive"):
        svc.disburse(grant.id, amount="0")
    fresh = _fresh(db_session, grant.id)
    assert fresh.disbursed_amount == Decimal("0")
    assert fresh.status == GrantStatus.APPROVED


@pytest.mark.unit
def test_milestone_disburse_rejects_amount_override(db_session):
    """Caller amount must match the milestone's approved amount — an
    override let one small milestone drain the whole grant."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    milestone = svc.create_milestone(grant.id, "M1", "first", "60")
    milestone.status = MilestoneStatus.APPROVED
    db_session.add(milestone)
    db_session.commit()
    with pytest.raises(ValueError, match="fixed by the milestone"):
        svc.disburse(grant.id, milestone_id=milestone.id, amount="100")
    assert _fresh(db_session, grant.id).disbursed_amount == Decimal("0")
    # The milestone itself stays payable at its own amount.
    final = svc.disburse(grant.id, milestone_id=milestone.id)
    assert Decimal(str(final.disbursed_amount)) == Decimal("60")


@pytest.mark.unit
def test_process_grant_rejects_active_grant(db_session):
    """An ACTIVE (resolved, disbursing) grant must not re-resolve — the old
    code regressed it to APPROVED and rewrote approved_amount."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    svc.disburse(grant.id, amount="40")  # partial → status ACTIVE
    active = _fresh(db_session, grant.id)
    assert active.status == GrantStatus.ACTIVE
    approved_before = active.approved_amount
    with pytest.raises(ValueError, match="not in a processable state"):
        svc.process_grant(grant.id)
    fresh = _fresh(db_session, grant.id)
    assert fresh.status == GrantStatus.ACTIVE
    assert fresh.approved_amount == approved_before


@pytest.mark.unit
def test_check_resolution_never_regresses_resolved_status(db_session):
    """_check_resolution must not rewrite status/approved_amount once the
    grant left SUBMITTED/UNDER_REVIEW — covers the vote()-path re-resolve."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    svc.disburse(grant.id, amount="40")
    active = _fresh(db_session, grant.id)
    assert active.status == GrantStatus.ACTIVE
    # Direct re-resolution with shifted votes must leave the row untouched.
    active.votes_for = 0
    active.votes_against = 100
    db_session.add(active)
    db_session.commit()
    svc._check_resolution(active, datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1))
    db_session.commit()
    fresh = _fresh(db_session, grant.id)
    assert fresh.status == GrantStatus.ACTIVE
