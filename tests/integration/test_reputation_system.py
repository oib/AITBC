"""
Reputation System Integration Tests
Comprehensive testing for agent reputation and trust score calculations
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from apps.coordinator_api.src.app.services.reputation_service import (
    ReputationService,
    TrustScoreCalculator,
)
from apps.coordinator_api.src.app.domain.reputation import (
    AgentReputation,
    CommunityFeedback,
    ReputationEvent,
    ReputationLevel,
)


class TestTrustScoreCalculator:
    """Test trust score calculation algorithms"""
    
    @pytest.fixture
    def calculator(self):
        return TrustScoreCalculator()
    
    @pytest.fixture
    def sample_agent_reputation(self):
        return AgentReputation(
            agent_id="test_agent_001",
            trust_score=500.0,
            reputation_level=ReputationLevel.BEGINNER,
            performance_rating=3.0,
            reliability_score=50.0,
            community_rating=3.0,
            total_earnings=100.0,
            transaction_count=10,
            success_rate=80.0,
            jobs_completed=8,
            jobs_failed=2,
            average_response_time=2000.0,
            dispute_count=0,
            certifications=["basic_ai"],
            specialization_tags=["inference", "text_generation"],
            geographic_region="us-east"
        )
    
    def test_performance_score_calculation(self, calculator, sample_agent_reputation):
        """Test performance score calculation"""
        
        # Mock session behavior
        class MockSession:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [sample_agent_reputation]
                return []
        
        session = MockSession()
        
        # Calculate performance score
        score = calculator.calculate_performance_score(
            "test_agent_001", 
            session, 
            timedelta(days=30)
        )
        
        # Verify score is in valid range
        assert 0 <= score <= 1000
        assert isinstance(score, float)
        
        # Higher performance rating should result in higher score
        sample_agent_reputation.performance_rating = 5.0
        high_score = calculator.calculate_performance_score("test_agent_001", session)
        assert high_score > score
    
    def test_reliability_score_calculation(self, calculator, sample_agent_reputation):
        """Test reliability score calculation"""
        
        class MockSession:
            def exec(self, query):
                return [sample_agent_reputation]
        
        session = MockSession()
        
        # Calculate reliability score
        score = calculator.calculate_reliability_score(
            "test_agent_001", 
            session, 
            timedelta(days=30)
        )
        
        # Verify score is in valid range
        assert 0 <= score <= 1000
        
        # Higher reliability should result in higher score
        sample_agent_reputation.reliability_score = 90.0
        high_score = calculator.calculate_reliability_score("test_agent_001", session)
        assert high_score > score
    
    def test_community_score_calculation(self, calculator):
        """Test community score calculation"""
        
        # Mock feedback data
        feedback1 = CommunityFeedback(
            agent_id="test_agent_001",
            reviewer_id="reviewer_001",
            overall_rating=5.0,
            verification_weight=1.0,
            moderation_status="approved"
        )
        
        feedback2 = CommunityFeedback(
            agent_id="test_agent_001",
            reviewer_id="reviewer_002",
            overall_rating=4.0,
            verification_weight=2.0,
            moderation_status="approved"
        )
        
        class MockSession:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [feedback1, feedback2]
                return []
        
        session = MockSession()
        
        # Calculate community score
        score = calculator.calculate_community_score(
            "test_agent_001", 
            session, 
            timedelta(days=90)
        )
        
        # Verify score is in valid range
        assert 0 <= score <= 1000
        
        # Should be weighted average of feedback ratings
        expected_weighted_avg = (5.0 * 1.0 + 4.0 * 2.0) / (1.0 + 2.0)
        expected_score = (expected_weighted_avg / 5.0) * 1000
        
        assert abs(score - expected_score) < 50  # Allow some variance for volume modifier
    
    def test_composite_trust_score(self, calculator, sample_agent_reputation):
        """Test composite trust score calculation"""
        
        class MockSession:
            def exec(self, query):
                return [sample_agent_reputation]
        
        session = MockSession()
        
        # Calculate composite score
        composite_score = calculator.calculate_composite_trust_score(
            "test_agent_001", 
            session, 
            timedelta(days=30)
        )
        
        # Verify score is in valid range
        assert 0 <= composite_score <= 1000
        
        # Composite score should be weighted average of components
        assert isinstance(composite_score, float)
    
    def test_reputation_level_determination(self, calculator):
        """Test reputation level determination based on trust score"""
        
        # Test different score ranges
        assert calculator.determine_reputation_level(950) == ReputationLevel.MASTER
        assert calculator.determine_reputation_level(800) == ReputationLevel.EXPERT
        assert calculator.determine_reputation_level(650) == ReputationLevel.ADVANCED
        assert calculator.determine_reputation_level(500) == ReputationLevel.INTERMEDIATE
        assert calculator.determine_reputation_level(300) == ReputationLevel.BEGINNER


class TestReputationService:
    """Test reputation service functionality"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        class MockSession:
            def __init__(self):
                self.data = {}
                self.committed = False
            
            def exec(self, query):
                # Mock query execution
                if hasattr(query, 'where'):
                    return []
                return []
            
            def add(self, obj):
                self.data[obj.id if hasattr(obj, 'id') else 'temp'] = obj
            
            def commit(self):
                self.committed = True
            
            def refresh(self, obj):
                pass
        
        return MockSession()
    
    @pytest.fixture
    def reputation_service(self, mock_session):
        return ReputationService(mock_session)
    
    def test_create_reputation_profile(self, reputation_service, mock_session):
        """Test creating a new reputation profile"""
        
        agent_id = "test_agent_001"
        
        # Create profile
        profile = asyncio.run(
            reputation_service.create_reputation_profile(agent_id)
        )
        
        # Verify profile creation
        assert profile.agent_id == agent_id
        assert profile.trust_score == 500.0  # Neutral starting score
        assert profile.reputation_level == ReputationLevel.BEGINNER
        assert mock_session.committed
    
    def test_record_job_completion_success(self, reputation_service, mock_session):
        """Test recording successful job completion"""
        
        agent_id = "test_agent_001"
        job_id = "job_001"
        success = True
        response_time = 1500.0
        earnings = 0.05
        
        # Create initial profile
        initial_profile = asyncio.run(
            reputation_service.create_reputation_profile(agent_id)
        )
        
        # Record job completion
        updated_profile = asyncio.run(
            reputation_service.record_job_completion(
                agent_id, job_id, success, response_time, earnings
            )
        )
        
        # Verify updates
        assert updated_profile.jobs_completed == 1
        assert updated_profile.jobs_failed == 0
        assert updated_profile.total_earnings == earnings
        assert updated_profile.transaction_count == 1
        assert updated_profile.success_rate == 100.0
        assert updated_profile.average_response_time == response_time
    
    def test_record_job_completion_failure(self, reputation_service, mock_session):
        """Test recording failed job completion"""
        
        agent_id = "test_agent_001"
        job_id = "job_002"
        success = False
        response_time = 8000.0
        earnings = 0.0
        
        # Create initial profile
        initial_profile = asyncio.run(
            reputation_service.create_reputation_profile(agent_id)
        )
        
        # Record job completion
        updated_profile = asyncio.run(
            reputation_service.record_job_completion(
                agent_id, job_id, success, response_time, earnings
            )
        )
        
        # Verify updates
        assert updated_profile.jobs_completed == 0
        assert updated_profile.jobs_failed == 1
        assert updated_profile.total_earnings == 0.0
        assert updated_profile.transaction_count == 1
        assert updated_profile.success_rate == 0.0
        assert updated_profile.average_response_time == response_time
    
    def test_add_community_feedback(self, reputation_service, mock_session):
        """Test adding community feedback"""
        
        agent_id = "test_agent_001"
        reviewer_id = "reviewer_001"
        ratings = {
            "overall": 5.0,
            "performance": 4.5,
            "communication": 5.0,
            "reliability": 4.0,
            "value": 5.0
        }
        feedback_text = "Excellent work!"
        tags = ["professional", "fast", "quality"]
        
        # Add feedback
        feedback = asyncio.run(
            reputation_service.add_community_feedback(
                agent_id, reviewer_id, ratings, feedback_text, tags
            )
        )
        
        # Verify feedback creation
        assert feedback.agent_id == agent_id
        assert feedback.reviewer_id == reviewer_id
        assert feedback.overall_rating == ratings["overall"]
        assert feedback.feedback_text == feedback_text
        assert feedback.feedback_tags == tags
        assert mock_session.committed
    
    def test_get_reputation_summary(self, reputation_service, mock_session):
        """Test getting reputation summary"""
        
        agent_id = "test_agent_001"
        
        # Create profile
        profile = asyncio.run(
            reputation_service.create_reputation_profile(agent_id)
        )
        
        # Mock session to return the profile
        mock_session.exec = lambda query: [profile] if hasattr(query, 'where') else []
        
        # Get summary
        summary = asyncio.run(
            reputation_service.get_reputation_summary(agent_id)
        )
        
        # Verify summary structure
        assert "agent_id" in summary
        assert "trust_score" in summary
        assert "reputation_level" in summary
        assert "performance_rating" in summary
        assert "reliability_score" in summary
        assert "community_rating" in summary
        assert "total_earnings" in summary
        assert "transaction_count" in summary
        assert "success_rate" in summary
        assert "recent_events" in summary
        assert "recent_feedback" in summary
    
    def test_get_leaderboard(self, reputation_service, mock_session):
        """Test getting reputation leaderboard"""
        
        # Create multiple mock profiles
        profiles = []
        for i in range(10):
            profile = AgentReputation(
                agent_id=f"agent_{i:03d}",
                trust_score=500.0 + (i * 50),
                reputation_level=ReputationLevel.INTERMEDIATE,
                performance_rating=3.0 + (i * 0.1),
                reliability_score=50.0 + (i * 5),
                community_rating=3.0 + (i * 0.1),
                total_earnings=100.0 * (i + 1),
                transaction_count=10 * (i + 1),
                success_rate=80.0 + (i * 2),
                jobs_completed=8 * (i + 1),
                jobs_failed=2 * (i + 1),
                geographic_region=f"region_{i % 3}"
            )
            profiles.append(profile)
        
        # Mock session to return profiles
        mock_session.exec = lambda query: profiles if hasattr(query, 'order_by') else []
        
        # Get leaderboard
        leaderboard = asyncio.run(
            reputation_service.get_leaderboard(limit=5)
        )
        
        # Verify leaderboard structure
        assert len(leaderboard) == 5
        assert all("rank" in entry for entry in leaderboard)
        assert all("agent_id" in entry for entry in leaderboard)
        assert all("trust_score" in entry for entry in leaderboard)
        
        # Verify ranking (highest trust score first)
        assert leaderboard[0]["trust_score"] >= leaderboard[1]["trust_score"]
        assert leaderboard[0]["rank"] == 1


class TestReputationIntegration:
    """Integration tests for reputation system"""
    
    @pytest.mark.asyncio
    async def test_full_reputation_lifecycle(self):
        """Test complete reputation lifecycle"""
        
        # This would be a full integration test with actual database
        # For now, we'll outline the test structure
        
        # 1. Create agent profile
        # 2. Record multiple job completions (success and failure)
        # 3. Add community feedback
        # 4. Verify trust score updates
        # 5. Check reputation level changes
        # 6. Get reputation summary
        # 7. Get leaderboard position
        
        pass
    
    @pytest.mark.asyncio
    async def test_trust_score_consistency(self):
        """Test trust score calculation consistency"""
        
        # Test that trust scores are calculated consistently
        # across different time windows and conditions
        
        pass
    
    @pytest.mark.asyncio
    async def test_reputation_level_progression(self):
        """Test reputation level progression"""
        
        # Test that agents progress through reputation levels
        # as their trust scores increase
        
        pass


# Performance Tests
class TestReputationPerformance:
    """Performance tests for reputation system"""
    
    @pytest.mark.asyncio
    async def test_bulk_reputation_calculations(self):
        """Test performance of bulk trust score calculations"""
        
        # Test calculating trust scores for many agents
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.asyncio
    async def test_leaderboard_performance(self):
        """Test leaderboard query performance"""
        
        # Test that leaderboard queries are fast
        # Even with large numbers of agents
        
        pass


# Utility Functions
def create_test_agent_data(agent_id: str, **kwargs) -> Dict[str, Any]:
    """Create test agent data for testing"""
    
    defaults = {
        "agent_id": agent_id,
        "trust_score": 500.0,
        "reputation_level": ReputationLevel.BEGINNER,
        "performance_rating": 3.0,
        "reliability_score": 50.0,
        "community_rating": 3.0,
        "total_earnings": 100.0,
        "transaction_count": 10,
        "success_rate": 80.0,
        "jobs_completed": 8,
        "jobs_failed": 2,
        "average_response_time": 2000.0,
        "dispute_count": 0,
        "certifications": [],
        "specialization_tags": [],
        "geographic_region": "us-east"
    }
    
    defaults.update(kwargs)
    return defaults


def create_test_feedback_data(agent_id: str, reviewer_id: str, **kwargs) -> Dict[str, Any]:
    """Create test feedback data for testing"""
    
    defaults = {
        "agent_id": agent_id,
        "reviewer_id": reviewer_id,
        "overall_rating": 4.0,
        "performance_rating": 4.0,
        "communication_rating": 4.0,
        "reliability_rating": 4.0,
        "value_rating": 4.0,
        "feedback_text": "Good work",
        "feedback_tags": ["professional"],
        "verification_weight": 1.0,
        "moderation_status": "approved"
    }
    
    defaults.update(kwargs)
    return defaults


# Test Configuration
@pytest.fixture(scope="session")
def test_config():
    """Test configuration for reputation system tests"""
    
    return {
        "test_agent_count": 100,
        "test_feedback_count": 500,
        "test_job_count": 1000,
        "performance_threshold_ms": 1000,
        "memory_threshold_mb": 100
    }


# Test Markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.slow = pytest.mark.slow
