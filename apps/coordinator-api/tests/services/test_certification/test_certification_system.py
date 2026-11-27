"""
Tests for certification system
"""

import pytest

# The certification context is dormant (no routers), so coordinator_api.main
# never imports these models — without this, SQLModel.metadata.create_all in
# the db_engine fixture does not create agent_certifications / agent_reputation.
from coordinator_api.contexts.certification.domain.certification import (  # noqa: E402
    AgentCertification,
)
from coordinator_api.contexts.reputation.domain.reputation import AgentReputation  # noqa: E402


@pytest.mark.unit
class TestCertificationSystem:
    """Test Certification System"""

    def test_certification_system_initialization(self):
        """Test certification system initialization"""
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        assert system.certification_levels is not None
        assert len(system.certification_levels) > 0
        assert system.verification_methods is not None

    def test_generate_verification_hash(self):
        """Test verification hash generation"""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        hash_value = system.generate_verification_hash(
            agent_id="agent123", level=CertificationLevel.BASIC, certification_id="cert_abc123"
        )

        assert hash_value is not None
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 produces 64 hex characters

    def test_get_special_capabilities(self):
        """Test getting special capabilities for certification level"""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        capabilities = system.get_special_capabilities(CertificationLevel.BASIC)

        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
        assert "standard_trading" in capabilities


@pytest.mark.unit
@pytest.mark.asyncio
class TestCertificationRenewal:
    """Renewal path pins for #3071 — renewal_requirements must resolve to real verifiers."""

    @staticmethod
    def _strong_reputation(agent_id: str):
        """Reputation row that passes every verifier at its highest tier."""
        return AgentReputation(
            agent_id=agent_id,
            trust_score=900.0,
            success_rate=99.0,
            jobs_completed=200,
            reliability_score=95.0,
            dispute_count=0,
            transaction_count=100,
            average_response_time=100.0,
            specialization_tags=["trading", "analytics"],
            certifications=["cert_basic"],
        )

    @staticmethod
    def _certification(agent_id: str, level, certification_id: str):
        from datetime import UTC, datetime

        from coordinator_api.contexts.certification.domain.certification import CertificationStatus

        return AgentCertification(
            certification_id=certification_id,
            agent_id=agent_id,
            certification_level=level,
            issued_by="tester",
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC),
            verification_hash="0" * 64,
            status=CertificationStatus.ACTIVE,
        )

    async def test_every_renewal_requirement_resolves_to_a_verifier(self, db_session):
        """Every renewal_requirements string across all levels must map to a
        real verifier — not fall through to 'Unknown requirement' (#3071)."""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        db_session.add(self._strong_reputation("agent-req"))
        # PREMIUM's compliance_current verifier needs an active certification.
        db_session.add(self._certification("agent-req", CertificationLevel.PREMIUM, "cert_premium_seed"))
        db_session.commit()

        for level, config in system.certification_levels.items():
            for requirement in config["renewal_requirements"]:
                result = await system.verify_requirement(db_session, "agent-req", requirement)
                assert "Unknown requirement" not in result["reason"], (
                    f"{level.value} renewal requirement '{requirement}' has no verifier"
                )
                assert result["passed"], f"{level.value} renewal requirement '{requirement}' failed: {result['reason']}"

    async def test_renew_certification_extends_expiry(self, db_session):
        """A valid ACTIVE certification renews: expiry extended, count bumped, new hash."""
        from datetime import UTC, datetime, timedelta

        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        agent_id = "agent-renew-ok"
        db_session.add(self._strong_reputation(agent_id))
        old_expiry = datetime.now(UTC) + timedelta(days=30)
        cert = self._certification(agent_id, CertificationLevel.BASIC, "cert_renew_ok")
        cert.expires_at = old_expiry
        cert.verification_hash = "a" * 64
        db_session.add(cert)
        db_session.commit()

        ok, message = await system.renew_certification(db_session, "cert_renew_ok", renewed_by="tester")

        assert ok, message
        db_session.refresh(cert)
        assert cert.renewal_count == 1
        assert cert.last_renewed_at is not None
        # SQLite round-trips datetimes as naive — normalize before comparing.
        expires_at = cert.expires_at
        assert expires_at is not None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        assert expires_at > old_expiry
        assert cert.verification_hash != "a" * 64
        # NB: audit_log JSON-append persistence is the #3055 fix's scope —
        # not asserted here (plain JSON columns don't track in-place mutation).

    async def test_renew_certification_fails_on_genuinely_unmet_requirements(self, db_session):
        """Without a reputation profile the renewal must fail on real verifier
        output — never on 'Unknown requirement' (#3071 mutation guard)."""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        db_session.add(self._certification("agent-no-rep", CertificationLevel.BASIC, "cert_renew_fail"))
        db_session.commit()

        ok, message = await system.renew_certification(db_session, "cert_renew_fail", renewed_by="tester")

        assert not ok
        assert "Unknown requirement" not in message
        assert "Renewal requirements not met" in message
        from sqlmodel import select

        # AgentCertification's PK is `id`, not `certification_id` — query by cert id.
        cert = (
            db_session.execute(select(AgentCertification).where(AgentCertification.certification_id == "cert_renew_fail"))
            .scalars()
            .one()
        )
        assert cert.renewal_count == 0
