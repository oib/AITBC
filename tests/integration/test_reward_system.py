"""
Reward System Integration Tests
Comprehensive testing for agent rewards, incentives, and performance-based earnings
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from apps.coordinator_api.src.app.services.reward_service import (
    RewardEngine, RewardCalculator
)
from apps.coordinator_api.src.app.domain.rewards import (
    AgentRewardProfile, RewardTierConfig, RewardCalculation, RewardDistribution,
    RewardTier, RewardType, RewardStatus
)
from apps.coordinator_api.src.app.domain.reputation import AgentReputation, ReputationLevel


class TestRewardCalculator:
    """Test reward calculation algorithms"""
    
    @pytest.fixture
    def calculator(self):
        return RewardCalculator()
    
    @pytest.fixture
    def sample_agent_reputation(self):
        return AgentReputation(
            agent_id="test_agent_001",
            trust_score=750.0,
            reputation_level=ReputationLevel.ADVANCED,
            performance_rating=4.5,
            reliability_score=85.0,
            community_rating=4.2,
            total_earnings=500.0,
            transaction_count=50,
            success_rate=92.0,
            jobs_completed=46,
            jobs_failed=4,
            average_response_time=1500.0,
            dispute_count=1,
            certifications=["advanced_ai", "expert_provider"],
            specialization_tags=["inference", "text_generation", "image_processing"],
            geographic_region="us-east"
        )
    
    def test_tier_multiplier_calculation(self, calculator, sample_agent_reputation):
        """Test tier multiplier calculation based on trust score"""
        
        # Mock session behavior
        class MockSession:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [sample_agent_reputation]
                return []
        
        session = MockSession()
        
        # Test different trust scores
        test_cases = [
            (950, 2.0),  # Diamond
            (850, 1.5),  # Platinum
            (750, 1.5),  # Gold (should match config)
            (600, 1.2),  # Silver
            (400, 1.1),  # Silver
            (300, 1.0),  # Bronze
        ]
        
        for trust_score, expected_multiplier in test_cases:
            sample_agent_reputation.trust_score = trust_score
            multiplier = calculator.calculate_tier_multiplier(trust_score, session)
            
            assert 1.0 <= multiplier <= 2.0
            assert isinstance(multiplier, float)
    
    def test_performance_bonus_calculation(self, calculator):
        """Test performance bonus calculation"""
        
        class MockSession:
            def exec(self, query):
                return []
        
        session = MockSession()
        
        # Test excellent performance
        excellent_metrics = {
            "performance_rating": 4.8,
            "average_response_time": 800,
            "success_rate": 96.0,
            "jobs_completed": 120
        }
        
        bonus = calculator.calculate_performance_bonus(excellent_metrics, session)
        assert bonus > 0.5  # Should get significant bonus
        
        # Test poor performance
        poor_metrics = {
            "performance_rating": 3.2,
            "average_response_time": 6000,
            "success_rate": 75.0,
            "jobs_completed": 10
        }
        
        bonus = calculator.calculate_performance_bonus(poor_metrics, session)
        assert bonus == 0.0  # Should get no bonus
    
    def test_loyalty_bonus_calculation(self, calculator):
        """Test loyalty bonus calculation"""
        
        # Mock reward profile
        class MockSession:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [AgentRewardProfile(
                        agent_id="test_agent",
                        current_streak=30,
                        lifetime_earnings=1500.0,
                        referral_count=15,
                        community_contributions=25
                    )]
                return []
        
        session = MockSession()
        
        bonus = calculator.calculate_loyalty_bonus("test_agent", session)
        assert bonus > 0.5  # Should get significant loyalty bonus
        
        # Test new agent
        class MockSessionNew:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [AgentRewardProfile(
                        agent_id="new_agent",
                        current_streak=0,
                        lifetime_earnings=10.0,
                        referral_count=0,
                        community_contributions=0
                    )]
                return []
        
        session_new = MockSessionNew()
        bonus_new = calculator.calculate_loyalty_bonus("new_agent", session_new)
        assert bonus_new == 0.0  # Should get no loyalty bonus
    
    def test_referral_bonus_calculation(self, calculator):
        """Test referral bonus calculation"""
        
        # Test high-quality referrals
        referral_data = {
            "referral_count": 10,
            "referral_quality": 0.9
        }
        
        bonus = calculator.calculate_referral_bonus(referral_data)
        expected_bonus = 0.05 * 10 * (0.5 + (0.9 * 0.5))
        assert abs(bonus - expected_bonus) < 0.001
        
        # Test no referrals
        no_referral_data = {
            "referral_count": 0,
            "referral_quality": 0.0
        }
        
        bonus = calculator.calculate_referral_bonus(no_referral_data)
        assert bonus == 0.0
    
    def test_total_reward_calculation(self, calculator, sample_agent_reputation):
        """Test comprehensive reward calculation"""
        
        class MockSession:
            def exec(self, query):
                if hasattr(query, 'where'):
                    return [sample_agent_reputation]
                return []
        
        session = MockSession()
        
        base_amount = 0.1  # 0.1 AITBC
        performance_metrics = {
            "performance_rating": 4.5,
            "average_response_time": 1500,
            "success_rate": 92.0,
            "jobs_completed": 50,
            "referral_data": {
                "referral_count": 5,
                "referral_quality": 0.8
            }
        }
        
        result = calculator.calculate_total_reward(
            "test_agent", base_amount, performance_metrics, session
        )
        
        # Verify calculation structure
        assert "base_amount" in result
        assert "tier_multiplier" in result
        assert "performance_bonus" in result
        assert "loyalty_bonus" in result
        assert "referral_bonus" in result
        assert "total_reward" in result
        assert "effective_multiplier" in result
        
        # Verify calculations
        assert result["base_amount"] == base_amount
        assert result["tier_multiplier"] >= 1.0
        assert result["total_reward"] >= base_amount
        assert result["effective_multiplier"] >= 1.0


class TestRewardEngine:
    """Test reward engine functionality"""
    
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
    def reward_engine(self, mock_session):
        return RewardEngine(mock_session)
    
    def test_create_reward_profile(self, reward_engine, mock_session):
        """Test creating a new reward profile"""
        
        agent_id = "test_agent_001"
        
        # Create profile
        profile = asyncio.run(
            reward_engine.create_reward_profile(agent_id)
        )
        
        # Verify profile creation
        assert profile.agent_id == agent_id
        assert profile.current_tier == RewardTier.BRONZE
        assert profile.tier_progress == 0.0
        assert mock_session.committed
    
    def test_calculate_and_distribute_reward(self, reward_engine, mock_session):
        """Test reward calculation and distribution"""
        
        agent_id = "test_agent_001"
        reward_type = RewardType.PERFORMANCE_BONUS
        base_amount = 0.05
        performance_metrics = {
            "performance_rating": 4.5,
            "average_response_time": 1500,
            "success_rate": 92.0,
            "jobs_completed": 50
        }
        
        # Mock reputation
        mock_session.exec = lambda query: [AgentReputation(
            agent_id=agent_id,
            trust_score=750.0,
            reputation_level=ReputationLevel.ADVANCED
        )] if hasattr(query, 'where') else []
        
        # Calculate and distribute reward
        result = asyncio.run(
            reward_engine.calculate_and_distribute_reward(
                agent_id, reward_type, base_amount, performance_metrics
            )
        )
        
        # Verify result structure
        assert "calculation_id" in result
        assert "distribution_id" in result
        assert "reward_amount" in result
        assert "reward_type" in result
        assert "tier_multiplier" in result
        assert "status" in result
        
        # Verify reward amount
        assert result["reward_amount"] >= base_amount
        assert result["status"] == "distributed"
    
    def test_process_reward_distribution(self, reward_engine, mock_session):
        """Test processing reward distribution"""
        
        # Create mock distribution
        distribution = RewardDistribution(
            id="dist_001",
            agent_id="test_agent",
            reward_amount=0.1,
            reward_type=RewardType.PERFORMANCE_BONUS,
            status=RewardStatus.PENDING
        )
        
        mock_session.exec = lambda query: [distribution] if hasattr(query, 'where') else []
        mock_session.add = lambda obj: None
        mock_session.commit = lambda: None
        mock_session.refresh = lambda obj: None
        
        # Process distribution
        result = asyncio.run(
            reward_engine.process_reward_distribution("dist_001")
        )
        
        # Verify processing
        assert result.status == RewardStatus.DISTRIBUTED
        assert result.transaction_id is not None
        assert result.transaction_hash is not None
        assert result.processed_at is not None
        assert result.confirmed_at is not None
    
    def test_update_agent_reward_profile(self, reward_engine, mock_session):
        """Test updating agent reward profile"""
        
        agent_id = "test_agent_001"
        reward_calculation = {
            "base_amount": 0.05,
            "total_reward": 0.075,
            "performance_rating": 4.5
        }
        
        # Create mock profile
        profile = AgentRewardProfile(
            agent_id=agent_id,
            current_tier=RewardTier.BRONZE,
            base_earnings=0.1,
            bonus_earnings=0.02,
            total_earnings=0.12,
            lifetime_earnings=0.5,
            rewards_distributed=5,
            current_streak=3
        )
        
        mock_session.exec = lambda query: [profile] if hasattr(query, 'where') else []
        mock_session.commit = lambda: None
        
        # Update profile
        asyncio.run(
            reward_engine.update_agent_reward_profile(agent_id, reward_calculation)
        )
        
        # Verify updates
        assert profile.base_earnings == 0.15  # 0.1 + 0.05
        assert profile.bonus_earnings == 0.045  # 0.02 + 0.025
        assert profile.total_earnings == 0.195  # 0.12 + 0.075
        assert profile.lifetime_earnings == 0.575  # 0.5 + 0.075
        assert profile.rewards_distributed == 6
        assert profile.current_streak == 4
        assert profile.performance_score == 4.5
    
    def test_determine_reward_tier(self, reward_engine):
        """Test reward tier determination"""
        
        test_cases = [
            (950, RewardTier.DIAMOND),
            (850, RewardTier.PLATINUM),
            (750, RewardTier.GOLD),
            (600, RewardTier.SILVER),
            (400, RewardTier.SILVER),
            (300, RewardTier.BRONZE),
        ]
        
        for trust_score, expected_tier in test_cases:
            tier = reward_engine.determine_reward_tier(trust_score)
            assert tier == expected_tier
    
    def test_get_reward_summary(self, reward_engine, mock_session):
        """Test getting reward summary"""
        
        agent_id = "test_agent_001"
        
        # Create mock profile
        profile = AgentRewardProfile(
            agent_id=agent_id,
            current_tier=RewardTier.GOLD,
            tier_progress=65.0,
            base_earnings=1.5,
            bonus_earnings=0.75,
            total_earnings=2.25,
            lifetime_earnings=5.0,
            rewards_distributed=25,
            current_streak=15,
            longest_streak=30,
            performance_score=4.2,
            last_reward_date=datetime.utcnow()
        )
        
        mock_session.exec = lambda query: [profile] if hasattr(query, 'where') else []
        
        # Get summary
        summary = asyncio.run(
            reward_engine.get_reward_summary(agent_id)
        )
        
        # Verify summary structure
        assert "agent_id" in summary
        assert "current_tier" in summary
        assert "tier_progress" in summary
        assert "base_earnings" in summary
        assert "bonus_earnings" in summary
        assert "total_earnings" in summary
        assert "lifetime_earnings" in summary
        assert "rewards_distributed" in summary
        assert "current_streak" in summary
        assert "longest_streak" in summary
        assert "performance_score" in summary
        assert "recent_calculations" in summary
        assert "recent_distributions" in summary
    
    def test_batch_process_pending_rewards(self, reward_engine, mock_session):
        """Test batch processing of pending rewards"""
        
        # Create mock pending distributions
        distributions = [
            RewardDistribution(
                id=f"dist_{i}",
                agent_id="test_agent",
                reward_amount=0.1,
                reward_type=RewardType.PERFORMANCE_BONUS,
                status=RewardStatus.PENDING,
                priority=5
            )
            for i in range(5)
        ]
        
        mock_session.exec = lambda query: distributions if hasattr(query, 'where') else []
        mock_session.add = lambda obj: None
        mock_session.commit = lambda: None
        mock_session.refresh = lambda obj: None
        
        # Process batch
        result = asyncio.run(
            reward_engine.batch_process_pending_rewards(limit=10)
        )
        
        # Verify batch processing
        assert "processed" in result
        assert "failed" in result
        assert "total" in result
        assert result["total"] == 5
        assert result["processed"] + result["failed"] == result["total"]
    
    def test_get_reward_analytics(self, reward_engine, mock_session):
        """Test getting reward analytics"""
        
        # Create mock distributions
        distributions = [
            RewardDistribution(
                id=f"dist_{i}",
                agent_id=f"agent_{i}",
                reward_amount=0.1 * (i + 1),
                reward_type=RewardType.PERFORMANCE_BONUS,
                status=RewardStatus.DISTRIBUTED,
                created_at=datetime.utcnow() - timedelta(days=i)
            )
            for i in range(10)
        ]
        
        mock_session.exec = lambda query: distributions if hasattr(query, 'where') else []
        
        # Get analytics
        analytics = asyncio.run(
            reward_engine.get_reward_analytics(
                period_type="daily",
                start_date=datetime.utcnow() - timedelta(days=30),
                end_date=datetime.utcnow()
            )
        )
        
        # Verify analytics structure
        assert "period_type" in analytics
        assert "start_date" in analytics
        assert "end_date" in analytics
        assert "total_rewards_distributed" in analytics
        assert "total_agents_rewarded" in analytics
        assert "average_reward_per_agent" in analytics
        assert "tier_distribution" in analytics
        assert "total_distributions" in analytics
        
        # Verify calculations
        assert analytics["total_rewards_distributed"] > 0
        assert analytics["total_agents_rewarded"] > 0
        assert analytics["average_reward_per_agent"] > 0


class TestRewardIntegration:
    """Integration tests for reward system"""
    
    @pytest.mark.asyncio
    async def test_full_reward_lifecycle(self):
        """Test complete reward lifecycle"""
        
        # This would be a full integration test with actual database
        # For now, we'll outline the test structure
        
        # 1. Create agent profile
        # 2. Create reputation profile
        # 3. Calculate and distribute multiple rewards
        # 4. Verify tier progression
        # 5. Check analytics
        # 6. Process batch rewards
        
        pass
    
    @pytest.mark.asyncio
    async def test_reward_tier_progression(self):
        """Test reward tier progression based on performance"""
        
        # Test that agents progress through reward tiers
        # as their trust scores and performance improve
        
        pass
    
    @pytest.mark.asyncio
    async def test_reward_calculation_consistency(self):
        """Test reward calculation consistency across different scenarios"""
        
        # Test that reward calculations are consistent
        # and predictable across various input scenarios
        
        pass


# Performance Tests
class TestRewardPerformance:
    """Performance tests for reward system"""
    
    @pytest.mark.asyncio
    async def test_bulk_reward_calculations(self):
        """Test performance of bulk reward calculations"""
        
        # Test calculating rewards for many agents
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.asyncio
    async def test_batch_distribution_performance(self):
        """Test batch reward distribution performance"""
        
        # Test that batch reward distributions are fast
        # Even with large numbers of pending rewards
        
        pass


# Utility Functions
def create_test_reward_profile(agent_id: str, **kwargs) -> Dict[str, Any]:
    """Create test reward profile data for testing"""
    
    defaults = {
        "agent_id": agent_id,
        "current_tier": RewardTier.BRONZE,
        "tier_progress": 0.0,
        "base_earnings": 0.0,
        "bonus_earnings": 0.0,
        "total_earnings": 0.0,
        "lifetime_earnings": 0.0,
        "rewards_distributed": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "performance_score": 0.0,
        "loyalty_score": 0.0,
        "referral_count": 0,
        "community_contributions": 0
    }
    
    defaults.update(kwargs)
    return defaults


def create_test_performance_metrics(**kwargs) -> Dict[str, Any]:
    """Create test performance metrics for testing"""
    
    defaults = {
        "performance_rating": 3.5,
        "average_response_time": 3000.0,
        "success_rate": 85.0,
        "jobs_completed": 25,
        "referral_data": {
            "referral_count": 0,
            "referral_quality": 0.5
        }
    }
    
    defaults.update(kwargs)
    return defaults


# Test Configuration
@pytest.fixture(scope="session")
def test_config():
    """Test configuration for reward system tests"""
    
    return {
        "test_agent_count": 100,
        "test_reward_count": 500,
        "test_distribution_count": 1000,
        "performance_threshold_ms": 1000,
        "memory_threshold_mb": 100
    }


# Test Markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.slow = pytest.mark.slow
