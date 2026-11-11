"""#1798: grant disburse + vote writes are atomic (CAS / SQL-side increment).

Before the fix, ``disburse`` read ``disbursed_amount``/``approved_amount``,
checked the balance in Python, then wrote — two concurrent disburses could
both pass and overdraw the approval (double-window). ``vote`` did
``votes_for += power`` as an ORM read-modify-write, so concurrent votes
lost counts. Now the balance predicate lives in the UPDATE's WHERE clause
and the counters are SQL-side ``col = col + power``.

Pins simulate the concurrent writer through a SECOND session on the same
engine. The interfering write must not go through ``db_session``: a commit
there expires the identity map, the "stale" object silently reloads fresh
values, and the pre-fix Python guards fire before the CAS is ever reached
— the pin then passes on unfixed code. With the write on ``db_engine``'s
other session, ``db_session`` keeps its warm, stale copy and only the SQL
predicate can stop the second writer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, col, select, update

from coordinator_api.contexts.developer.schemas.developer import DeveloperCreate
from coordinator_api.contexts.developer.services.developer_service import DeveloperService
from coordinator_api.contexts.governance.domain.grant import (
    GrantMilestone,
    GrantProposal,
    GrantStatus,
    MilestoneStatus,
)
from coordinator_api.contexts.governance.services.grant_service import GrantService


def _developer(session: Session) -> str:
    dev = DeveloperService(session).register(DeveloperCreate(wallet_address="0x" + "ab" * 20, name="CAS Dev"))
    return dev.id


def _approved_grant(session: Session, svc: GrantService, dev_id: str, amount: str = "100") -> GrantProposal:
    grant = svc.create_grant(dev_id, "CAS Grant", "desc", amount, voting_days=1)
    svc.vote(grant.id, "for", 10.0, voter_id="seed")
    grant.voting_ends = datetime.now(UTC) - timedelta(seconds=1)
    session.add(grant)
    session.commit()
    return svc.process_grant(grant.id)


def _interfere(db_engine, statement) -> None:
    """Commit ``statement`` through a second session so ``db_session``'s
    identity map keeps its stale copy — the concurrent-writer simulation."""
    with Session(db_engine) as other:
        other.execute(statement)
        other.commit()


def _fresh_status(session: Session, grant_id: str) -> tuple[str, Decimal]:
    session.expire_all()
    status, disbursed = session.execute(
        select(GrantProposal.status, GrantProposal.disbursed_amount).where(GrantProposal.id == grant_id)
    ).one()
    return status, Decimal(str(disbursed))


@pytest.mark.unit
def test_disburse_cas_rejects_overdraw_after_concurrent_claim(db_session, db_engine):
    """Stale reader thinks 100 is fully available; a concurrent disburse
    already took 90 — the second 50 must lose at the SQL predicate."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    # Warm the identity map (disbursed=0), then consume 90 via a second
    # session — db_session's copy stays stale.
    assert db_session.get(GrantProposal, grant.id).disbursed_amount == Decimal("0")
    _interfere(
        db_engine,
        update(GrantProposal).where(col(GrantProposal.id) == grant.id).values(disbursed_amount=Decimal("90")),
    )
    with pytest.raises(ValueError, match="approved balance"):
        svc.disburse(grant.id, amount="50")
    status, disbursed = _fresh_status(db_session, grant.id)
    assert disbursed == Decimal("90")
    assert status == GrantStatus.APPROVED.value


@pytest.mark.unit
def test_disburse_cas_completes_on_full_amount(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    final = svc.disburse(grant.id, amount="100")
    assert final.status == GrantStatus.COMPLETED
    assert Decimal(str(final.disbursed_amount)) == Decimal("100")


@pytest.mark.unit
def test_disburse_persists_across_sessions(tmp_path):
    """Hotfix pin: disburse must COMMIT, not just execute the CAS UPDATE.

    Every other mutator in GrantService commits; disburse returned 200 with
    the payout rolled back when the request session closed. Uses a
    file-backed engine so the verifying session gets its own connection —
    the shared in-memory StaticPool connection would see uncommitted state
    and mask the missing commit."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/grant.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s1:
        dev_id = _developer(s1)
        svc = GrantService(s1)
        grant = _approved_grant(s1, svc, dev_id, "100")
        svc.disburse(grant.id, amount="40")
    with Session(engine) as s2:
        row = s2.get(GrantProposal, grant.id)
        assert Decimal(str(row.disbursed_amount)) == Decimal("40")
        assert row.status == GrantStatus.ACTIVE


@pytest.mark.unit
def test_disburse_partial_keeps_active(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    final = svc.disburse(grant.id, amount="40")
    assert final.status == GrantStatus.ACTIVE
    assert Decimal(str(final.disbursed_amount)) == Decimal("40")


@pytest.mark.unit
def test_milestone_double_claim_only_one_wins(db_session, db_engine):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    milestone = svc.create_milestone(grant.id, "M1", "first", "60")
    milestone.status = MilestoneStatus.APPROVED
    db_session.add(milestone)
    db_session.commit()
    # A concurrent disburse already paid this milestone via a second session;
    # our cached copy still says APPROVED.
    _interfere(
        db_engine,
        update(GrantMilestone).where(col(GrantMilestone.id) == milestone.id).values(status=MilestoneStatus.PAID),
    )
    with pytest.raises(ValueError, match="already paid"):
        svc.disburse(grant.id, milestone_id=milestone.id)
    _, disbursed = _fresh_status(db_session, grant.id)
    assert disbursed == Decimal("0")


@pytest.mark.unit
def test_milestone_disburse_happy_path(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = _approved_grant(db_session, svc, dev_id, "100")
    milestone = svc.create_milestone(grant.id, "M1", "first", "60")
    milestone.status = MilestoneStatus.APPROVED
    db_session.add(milestone)
    db_session.commit()
    final = svc.disburse(grant.id, milestone_id=milestone.id)
    assert Decimal(str(final.disbursed_amount)) == Decimal("60")
    db_session.expire_all()
    assert db_session.get(GrantMilestone, milestone.id).status == MilestoneStatus.PAID


@pytest.mark.unit
def test_vote_counters_accumulate_atomically(db_session, db_engine):
    """Lost-update pin: a concurrent voter's +7 lands via a second session;
    our stale copy still says 15 — only the SQL-side ``col = col + power``
    keeps both increments (15 + 7 + 10 = 32). An ORM read-modify-write would
    write 25 and silently drop the concurrent vote."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = svc.create_grant(dev_id, "Vote Grant", "desc", "100", voting_days=1)
    svc.vote(grant.id, "for", 10.0, voter_id="v1")
    svc.vote(grant.id, "for", 5.0, voter_id="v2")
    svc.vote(grant.id, "against", 3.0, voter_id="v3")
    assert db_session.get(GrantProposal, grant.id).votes_for == 15.0
    _interfere(
        db_engine,
        update(GrantProposal).where(col(GrantProposal.id) == grant.id).values(votes_for=col(GrantProposal.votes_for) + 7.0),
    )
    svc.vote(grant.id, "for", 10.0, voter_id="v4")
    db_session.expire_all()
    row = db_session.get(GrantProposal, grant.id)
    assert row.votes_for == 32.0
    assert row.votes_against == 3.0


@pytest.mark.unit
def test_vote_cas_rejects_grant_resolved_behind_read(db_session, db_engine):
    """Stale reader still sees SUBMITTED; the grant was resolved to APPROVED
    by a concurrent process_grant via a second session — the counter UPDATE
    must take rowcount 0. voting_ends stays in the future so the Python
    time check cannot fire first and mask the CAS."""
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = svc.create_grant(dev_id, "Race Grant", "desc", "100", voting_days=1)
    db_session.commit()
    # Warm identity map (status SUBMITTED, voting still open), then resolve
    # behind its back through the second session.
    assert db_session.get(GrantProposal, grant.id).status == GrantStatus.SUBMITTED
    _interfere(
        db_engine,
        update(GrantProposal).where(col(GrantProposal.id) == grant.id).values(status=GrantStatus.APPROVED),
    )
    with pytest.raises(ValueError, match="not open for voting"):
        svc.vote(grant.id, "for", 10.0, voter_id="late")
    db_session.expire_all()
    row = db_session.get(GrantProposal, grant.id)
    assert row.votes_for == 0.0
    assert row.status == GrantStatus.APPROVED


@pytest.mark.unit
def test_disburse_on_non_approved_grant_rejected(db_session):
    dev_id = _developer(db_session)
    svc = GrantService(db_session)
    grant = svc.create_grant(dev_id, "Draft Grant", "desc", "100", voting_days=1)
    with pytest.raises(ValueError, match="not approved"):
        svc.disburse(grant.id, amount="10")
