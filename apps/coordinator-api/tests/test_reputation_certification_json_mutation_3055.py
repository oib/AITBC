"""Persistence pins for #3055 — reputation/certification JSON audit trails.

SQLAlchemy does not track in-place mutation of plain ``Column(JSON)``
attributes: ``obj.col.append(x)`` never dirties the attribute, so the
commit's UPDATE omits the column and the audit entry is silently dropped
(the #3014 trap; payments core and #3053 already use copy-mutate-reassign).
Two live sites: ``AgentReputation.reputation_history`` on the
job-completion money path (``record_job_completion`` ->
``update_trust_score`` runs on every miner job completion/failure) and
``AgentCertification.audit_log`` on certification renewal.

Each test mutates through the service, lets it commit, then re-reads via a
FRESH session on the same engine. Asserting on the in-memory object alone
cannot catch the silent drop — the object still shows the append after
the commit that never wrote it (and ``update_trust_score`` refreshes the
row, which would mask the loss entirely).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from coordinator_api.contexts.certification.domain.certification import (
    AgentCertification,
    CertificationLevel,
    CertificationStatus,
)
from coordinator_api.contexts.certification.services.certification.certification_system import (
    CertificationSystem,
)
from coordinator_api.contexts.reputation.domain.reputation import AgentReputation
from coordinator_api.contexts.reputation.services.reputation_service import ReputationService


def _fresh_reputation(db_engine: Engine, agent_id: str) -> AgentReputation | None:
    with Session(db_engine) as fresh:
        return fresh.exec(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()


def _fresh_certification(db_engine: Engine, certification_id: str) -> AgentCertification | None:
    with Session(db_engine) as fresh:
        return fresh.exec(select(AgentCertification).where(AgentCertification.certification_id == certification_id)).first()


@pytest.mark.unit
async def test_record_job_completion_persists_reputation_history(db_session: Session, db_engine: Engine) -> None:
    """Every trust-score event must accumulate a reputation_history entry.

    Two completions prove append semantics across commits: the first entry
    must survive the second commit's UPDATE, not just the in-session list.
    """
    agent_id = "agent-3055-jobs"
    service = ReputationService(db_session)

    await service.record_job_completion(agent_id, "job-1", success=True, response_time=1200.0, earnings=Decimal("1.5"))
    await service.record_job_completion(agent_id, "job-2", success=False, response_time=9000.0, earnings=Decimal("0"))

    reread = _fresh_reputation(db_engine, agent_id)
    assert reread is not None
    assert len(reread.reputation_history) == 2
    first, second = reread.reputation_history
    assert first["event_type"] == "job_completed"
    assert first["new_trust_score"] is not None
    assert second["event_type"] == "job_completed"
    # scalar columns on the same row still persist alongside the JSON append
    assert reread.jobs_completed == 1
    assert reread.jobs_failed == 1


@pytest.mark.unit
async def test_renew_certification_persists_audit_log(
    db_session: Session, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """renew_certification must persist the 'renewed' audit entry.

    The renewal_requirements names are not in ``verify_requirement``'s
    verification map, so the check is stubbed to pass — the pin is about
    the JSON append persisting, not requirement evaluation. The seeded
    audit_log is NON-EMPTY so the in-place-append path is the only one
    exercised.
    """
    certification_id = "cert-3055-renew"
    db_session.add(
        AgentCertification(
            certification_id=certification_id,
            agent_id="agent-3055-cert",
            certification_level=CertificationLevel.BASIC,
            issued_by="ops",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            verification_hash="0" * 64,
            status=CertificationStatus.ACTIVE,
            audit_log=[
                {
                    "action": "issued",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "performed_by": "ops",
                    "details": "Certification issued at basic level",
                }
            ],
        )
    )
    db_session.commit()

    system = CertificationSystem()

    async def _pass(session: Session, agent_id: str, requirement: str) -> dict:
        return {"passed": True, "reason": "stubbed", "score": 100.0, "details": {}}

    monkeypatch.setattr(system, "verify_requirement", _pass)

    ok, message = await system.renew_certification(db_session, certification_id, renewed_by="ops-renewer")
    assert ok is True, message

    reread = _fresh_certification(db_engine, certification_id)
    assert reread is not None
    assert reread.renewal_count == 1
    assert len(reread.audit_log) == 2
    assert reread.audit_log[0]["action"] == "issued"
    renewed = reread.audit_log[1]
    assert renewed["action"] == "renewed"
    assert renewed["performed_by"] == "ops-renewer"
    assert renewed["timestamp"]
    assert "renewed" in renewed["details"].lower() or "days" in renewed["details"]
