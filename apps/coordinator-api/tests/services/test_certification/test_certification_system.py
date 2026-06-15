"""
Tests for certification system
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestCertificationSystem:
    """Test Certification System"""

    def test_certification_system_initialization(self):
        """Test certification system initialization"""
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        assert system.certification_levels is not None
        assert len(system.certification_levels) > 0
        assert system.verification_methods is not None

    def test_generate_verification_hash(self):
        """Test verification hash generation"""
        from app.domain.certification import CertificationLevel
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        hash_value = system.generate_verification_hash(
            agent_id="agent123", level=CertificationLevel.BASIC, certification_id="cert_abc123"
        )

        assert hash_value is not None
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 produces 64 hex characters

    def test_get_special_capabilities(self):
        """Test getting special capabilities for certification level"""
        from app.domain.certification import CertificationLevel
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        capabilities = system.get_special_capabilities(CertificationLevel.BASIC)

        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
        assert "standard_trading" in capabilities

    @patch("app.services.certification.certification_system.Session")
    async def test_verify_identity(self, mock_session):
        """Test identity verification"""
        from app.domain.reputation import AgentReputation
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        mock_session_instance = MagicMock()

        # Mock reputation data
        mock_reputation = AgentReputation(
            agent_id="agent123",
            trust_score=750.0,
            reliability_score=85.0,
            success_rate=90.0,
            performance_rating=4.5,
            total_earnings=1000.0,
            transaction_count=50,
            jobs_completed=45,
            dispute_count=1,
            average_response_time=2000.0,
            specialization_tags=["compute", "storage"],
            certifications=["basic"],
            geographic_region="us-west",
            community_contributions=10,
            created_at=datetime.now(UTC),
        )

        mock_session_instance.execute.return_value.first.return_value = mock_reputation

        result = await system.verify_identity(mock_session_instance, "agent123")

        assert result["passed"]
        assert "trust_score" in result["details"]

    @patch("app.services.certification.certification_system.Session")
    async def test_verify_performance(self, mock_session):
        """Test performance verification"""
        from app.domain.reputation import AgentReputation
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        mock_session_instance = MagicMock()

        # Mock reputation data with high performance
        mock_reputation = AgentReputation(
            agent_id="agent123",
            trust_score=850.0,
            reliability_score=90.0,
            success_rate=95.0,
            performance_rating=4.8,
            total_earnings=5000.0,
            transaction_count=100,
            jobs_completed=95,
            dispute_count=0,
            average_response_time=1500.0,
            specialization_tags=["compute", "storage"],
            certifications=["basic"],
            geographic_region="us-west",
            community_contributions=20,
            created_at=datetime.now(UTC),
        )

        mock_session_instance.execute.return_value.first.return_value = mock_reputation

        result = await system.verify_performance(mock_session_instance, "agent123")

        assert result["passed"]
        assert result["score"] > 80.0

    @patch("app.services.certification.certification_system.Session")
    async def test_certify_agent(self, mock_session):
        """Test agent certification"""
        from app.domain.certification import AgentCertification, CertificationLevel
        from app.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()
        mock_session_instance = MagicMock()

        # Mock reputation data
        mock_reputation = MagicMock()
        mock_reputation.trust_score = 850.0
        mock_reputation.success_rate = 95.0
        mock_reputation.jobs_completed = 100
        mock_reputation.reliability_score = 90.0
        mock_reputation.specialization_tags = ["compute", "storage"]

        mock_session_instance.execute.return_value.first.return_value = mock_reputation

        # Mock certification creation
        AgentCertification(
            certification_id="cert_abc123",
            agent_id="agent123",
            certification_level=CertificationLevel.BASIC,
            certification_type="standard",
            issued_by="system",
            status="active",
            requirements_met=["identity_verified", "basic_performance"],
            granted_privileges=["basic_trading", "standard_support"],
        )

        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = None

        result = await system.certify_agent(
            mock_session_instance, agent_id="agent123", level=CertificationLevel.BASIC, issued_by="system"
        )

        assert result[0]  # Success
        assert result[1] is not None  # Certification object
        assert len(result[2]) == 0  # No errors
