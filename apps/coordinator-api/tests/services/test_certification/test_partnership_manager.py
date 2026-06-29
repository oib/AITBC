"""
Tests for partnership manager
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestPartnershipManager:
    """Test Partnership Manager"""

    def test_partnership_manager_initialization(self):
        """Test partnership manager initialization"""
        from app.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()

        assert manager.partnership_types is not None
        assert len(manager.partnership_types) > 0

    @patch("app.contexts.certification.services.certification.partnership_manager.Session")
    async def test_check_technical_capability(self, mock_session):
        """Test technical capability check"""
        from app.contexts.reputation.domain.reputation import AgentReputation
        from app.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()
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

        result = await manager.check_technical_capability(mock_session_instance, "agent123")

        assert "eligible" in result
        assert "score" in result
        assert "details" in result

    @patch("app.contexts.certification.services.certification.partnership_manager.Session")
    async def test_check_service_quality(self, mock_session):
        """Test service quality check"""
        from app.contexts.reputation.domain.reputation import AgentReputation
        from app.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()
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

        result = await manager.check_service_quality(mock_session_instance, "agent123")

        assert "eligible" in result
        assert "score" in result

    @patch("app.contexts.certification.services.certification.partnership_manager.Session")
    async def test_create_partnership_program(self, mock_session):
        """Test partnership program creation"""
        from app.contexts.certification.domain.certification import PartnershipProgram
        from app.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()
        mock_session_instance = MagicMock()

        mock_program = PartnershipProgram(
            program_id="prog_abc123",
            program_name="Test Program",
            program_type="technology",
            description="Test description",
            tier_levels=["basic", "premium"],
            benefits_by_tier={"basic": ["api_access"], "premium": ["api_access", "technical_support"]},
            requirements_by_tier={"basic": ["technical_capability"], "premium": ["technical_capability", "service_quality"]},
            eligibility_requirements=["technical_capability"],
            minimum_criteria={},
            exclusion_criteria=[],
            financial_benefits={"type": "revenue_share", "rate": 0.15},
            non_financial_benefits=["api_access", "technical_support"],
            exclusive_access=[],
            agreement_terms={},
            commission_structure={"type": "revenue_share", "rate": 0.15},
            performance_metrics=["sales_volume", "customer_satisfaction"],
            max_participants=100,
            launched_at=datetime.now(UTC),
        )

        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = mock_program

        result = await manager.create_partnership_program(
            mock_session_instance,
            program_name="Test Program",
            program_type="technology",
            description="Test description",
            created_by="system",
        )

        assert result.program_id is not None
        assert result.program_name == "Test Program"

    @patch("app.contexts.certification.services.certification.partnership_manager.Session")
    async def test_apply_for_partnership(self, mock_session):
        """Test partnership application"""
        from app.contexts.certification.domain.certification import AgentPartnership, PartnershipProgram
        from app.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()
        mock_session_instance = MagicMock()

        # Mock program
        mock_program = PartnershipProgram(
            program_id="prog_abc123",
            program_name="Test Program",
            program_type="technology",
            description="Test description",
            tier_levels=["basic", "premium"],
            benefits_by_tier={"basic": ["api_access"]},
            requirements_by_tier={"basic": ["technical_capability"]},
            eligibility_requirements=["technical_capability"],
            minimum_criteria={},
            exclusion_criteria=[],
            financial_benefits={},
            non_financial_benefits=[],
            exclusive_access=[],
            agreement_terms={},
            commission_structure={},
            performance_metrics=[],
            max_participants=100,
            launched_at=datetime.now(UTC),
        )

        # Mock reputation (real ORM object so to_dto() produces a usable DTO)
        from app.contexts.reputation.domain.reputation import AgentReputation

        mock_reputation = AgentReputation(
            agent_id="agent123",
            trust_score=750.0,
            specialization_tags=["compute", "storage"],
            created_at=datetime.now(UTC),
        )

        # apply_for_partnership calls session.execute(...).first() twice:
        #   1. program lookup -> mock_program
        #   2. reputation lookup (via check_technical_capability -> get_reputation_dto) -> mock_reputation
        mock_session_instance.execute.return_value.first.side_effect = [mock_program, mock_reputation]

        # Mock partnership
        mock_partnership = AgentPartnership(
            partnership_id="agent_partner_abc123",
            agent_id="agent123",
            program_id="prog_abc123",
            partnership_type="technology",
            current_tier="basic",
            applied_at=datetime.now(UTC),
            status="pending_approval",
        )

        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = mock_partnership

        result = await manager.apply_for_partnership(
            mock_session_instance,
            agent_id="agent123",
            program_id="prog_abc123",
            application_data={"reason": "Test application"},
        )

        assert result[0]  # Success
        assert result[1] is not None  # Partnership object
