"""
Tests for badge system
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.unit
class TestBadgeSystem:
    """Test Badge System"""

    def test_badge_system_initialization(self):
        """Test badge system initialization"""
        from app.services.certification.badge_system import BadgeSystem

        system = BadgeSystem()
        
        assert system.badge_categories is not None
        assert len(system.badge_categories) > 0
        assert "performance" in system.badge_categories
        assert "reliability" in system.badge_categories

    def test_get_metric_value(self):
        """Test getting metric value from reputation"""
        from app.services.certification.badge_system import BadgeSystem
        from app.domain.reputation import AgentReputation

        system = BadgeSystem()
        
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
            created_at=datetime.now(timezone.utc)
        )
        
        jobs_completed = system.get_metric_value(mock_reputation, "jobs_completed")
        trust_score = system.get_metric_value(mock_reputation, "trust_score")
        
        assert jobs_completed == 45.0
        assert trust_score == 750.0

    @patch('app.services.certification.badge_system.Session')
    async def test_create_badge(self, mock_session):
        """Test badge creation"""
        from app.services.certification.badge_system import BadgeSystem
        from app.domain.certification import AchievementBadge, BadgeType

        system = BadgeSystem()
        mock_session_instance = MagicMock()
        
        mock_badge = AchievementBadge(
            badge_id="badge_abc123",
            badge_name="Test Badge",
            badge_type=BadgeType.ACHIEVEMENT,
            description="Test description",
            achievement_criteria={"required_metrics": ["jobs_completed"], "threshold_values": {"jobs_completed": 10}},
            required_metrics=["jobs_completed"],
            threshold_values={"jobs_completed": 10},
            rarity="common",
            point_value=10,
            category="performance",
            color_scheme={},
            display_properties={},
            is_limited=False,
            max_awards=None,
            available_from=datetime.now(timezone.utc),
            available_until=None
        )
        
        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = mock_badge
        
        result = await system.create_badge(
            mock_session_instance,
            badge_name="Test Badge",
            badge_type=BadgeType.ACHIEVEMENT,
            description="Test description",
            criteria={"required_metrics": ["jobs_completed"], "threshold_values": {"jobs_completed": 10}},
            created_by="system"
        )
        
        assert result.badge_id is not None
        assert result.badge_name == "Test Badge"

    @patch('app.services.certification.badge_system.Session')
    async def test_verify_badge_eligibility(self, mock_session):
        """Test badge eligibility verification"""
        from app.services.certification.badge_system import BadgeSystem
        from app.domain.certification import AchievementBadge, BadgeType
        from app.domain.reputation import AgentReputation

        system = BadgeSystem()
        mock_session_instance = MagicMock()
        
        # Mock badge
        mock_badge = AchievementBadge(
            badge_id="badge_abc123",
            badge_name="Test Badge",
            badge_type=BadgeType.ACHIEVEMENT,
            description="Test description",
            achievement_criteria={"required_metrics": ["jobs_completed"], "threshold_values": {"jobs_completed": 10}},
            required_metrics=["jobs_completed"],
            threshold_values={"jobs_completed": 10},
            rarity="common",
            point_value=10,
            category="performance",
            color_scheme={},
            display_properties={},
            is_limited=False,
            max_awards=None,
            available_from=datetime.now(timezone.utc),
            available_until=None
        )
        
        # Mock reputation with enough jobs completed
        mock_reputation = AgentReputation(
            agent_id="agent123",
            trust_score=750.0,
            reliability_score=85.0,
            success_rate=90.0,
            performance_rating=4.5,
            total_earnings=1000.0,
            transaction_count=50,
            jobs_completed=45,  # Above threshold of 10
            dispute_count=1,
            average_response_time=2000.0,
            specialization_tags=["compute", "storage"],
            certifications=["basic"],
            geographic_region="us-west",
            community_contributions=10,
            created_at=datetime.now(timezone.utc)
        )
        
        mock_session_instance.execute.return_value.first.return_value = mock_reputation
        
        result = await system.verify_badge_eligibility(mock_session_instance, "agent123", mock_badge)
        
        assert result["eligible"] == True
        assert "metrics" in result
        assert "evidence" in result

    @patch('app.services.certification.badge_system.Session')
    async def test_award_badge(self, mock_session):
        """Test badge awarding"""
        from app.services.certification.badge_system import BadgeSystem
        from app.domain.certification import AchievementBadge, AgentBadge, BadgeType

        system = BadgeSystem()
        mock_session_instance = MagicMock()
        
        # Mock badge
        mock_badge = AchievementBadge(
            badge_id="badge_abc123",
            badge_name="Test Badge",
            badge_type=BadgeType.ACHIEVEMENT,
            description="Test description",
            achievement_criteria={"required_metrics": ["jobs_completed"], "threshold_values": {"jobs_completed": 10}},
            required_metrics=["jobs_completed"],
            threshold_values={"jobs_completed": 10},
            rarity="common",
            point_value=10,
            category="performance",
            color_scheme={},
            display_properties={},
            is_limited=True,
            max_awards=100,
            current_awards=50,
            available_from=datetime.now(timezone.utc),
            available_until=None
        )
        
        # Mock agent badge
        mock_agent_badge = AgentBadge(
            agent_id="agent123",
            badge_id="badge_abc123",
            awarded_by="system",
            award_reason="Test award",
            achievement_context={},
            metrics_at_award={},
            supporting_evidence=[]
        )
        
        mock_session_instance.execute.return_value.first.return_value = None  # No existing badge
        mock_session_instance.add.return_value = None
        mock_session_instance.commit.return_value = None
        mock_session_instance.refresh.return_value = mock_agent_badge
        
        result = await system.award_badge(
            mock_session_instance,
            agent_id="agent123",
            badge_id="badge_abc123",
            awarded_by="system"
        )
        
        assert result[0] == True  # Success
        assert result[1] is not None  # AgentBadge object
