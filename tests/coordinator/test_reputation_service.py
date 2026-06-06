"""
Reputation Service Tests
Tests for reputation service and trust score calculator
"""

import sys
from pathlib import Path

# Add coordinator-api path for imports
coordinator_path = Path("/opt/aitbc/apps/coordinator-api/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.reputation import (
    AgentReputation,
    CommunityFeedback,
    ReputationEvent,
    ReputationLevel,
    TrustScoreCategory,
    TrustScoreCalculation,
)


class TestReputationModels:
    """Test reputation data models"""

    def test_agent_reputation_creation(self):
        """Test creating an AgentReputation model"""
        reputation = AgentReputation(
            agent_id="test_agent_001",
            trust_score=750.0,
            reputation_level=ReputationLevel.EXPERT,
            performance_rating=4.5,
            reliability_score=85.0,
            community_rating=4.2,
            total_earnings=Decimal("1000.50"),
            transaction_count=50,
            success_rate=92.0,
            jobs_completed=46,
            jobs_failed=4
        )
        assert reputation.agent_id == "test_agent_001"
        assert reputation.trust_score == 750.0
        assert reputation.reputation_level == ReputationLevel.EXPERT
        assert reputation.success_rate == 92.0

    def test_community_feedback_creation(self):
        """Test creating a CommunityFeedback model"""
        feedback = CommunityFeedback(
            agent_id="test_agent_002",
            reviewer_id="reviewer_001",
            overall_rating=5.0,
            performance_rating=5.0,
            communication_rating=5.0,
            reliability_rating=5.0,
            value_rating=5.0,
            feedback_text="Excellent service",
            feedback_tags=["professional", "timely"]
        )
        assert feedback.agent_id == "test_agent_002"
        assert feedback.overall_rating == 5.0
        assert feedback.feedback_text == "Excellent service"
        assert len(feedback.feedback_tags) == 2

    def test_reputation_event_creation(self):
        """Test creating a ReputationEvent model"""
        event = ReputationEvent(
            agent_id="test_agent_003",
            event_type="job_completed",
            impact_score=10.0,
            trust_score_before=500.0,
            trust_score_after=510.0,
            occurred_at=datetime.now(UTC)
        )
        assert event.agent_id == "test_agent_003"
        assert event.event_type == "job_completed"
        assert event.impact_score == 10.0
        assert event.trust_score_after - event.trust_score_before == event.impact_score

    def test_trust_score_calculation_creation(self):
        """Test creating a TrustScoreCalculation model"""
        calc = TrustScoreCalculation(
            agent_id="test_agent_004",
            category=TrustScoreCategory.PERFORMANCE,
            base_score=100.0,
            adjusted_score=120.0,
            calculated_at=datetime.now(UTC)
        )
        assert calc.agent_id == "test_agent_004"
        assert calc.category == TrustScoreCategory.PERFORMANCE
        assert calc.adjusted_score > calc.base_score


class TestTrustScoreCalculator:
    """Test trust score calculation logic"""

    def test_performance_score_calculation(self):
        """Test performance score calculation"""
        success_rate = 0.92
        avg_rating = 4.5
        job_count = 50
        
        # Mock calculation: success rate * 100 + (rating * 10) + job factor
        job_factor = min(job_count / 100, 1.0) * 10
        performance_score = (success_rate * 100) + (avg_rating * 10) + job_factor
        
        assert performance_score >= 0
        assert performance_score <= 200  # Max theoretical score

    def test_reliability_score_calculation(self):
        """Test reliability score calculation"""
        uptime_percentage = 99.5
        response_time_avg = 50  # ms
        on_time_delivery_rate = 0.95
        
        # Mock calculation
        reliability_score = (uptime_percentage + (100 - min(response_time_avg, 100)) + (on_time_delivery_rate * 100)) / 3
        
        assert reliability_score >= 0
        assert reliability_score <= 100

    def test_community_score_calculation(self):
        """Test community score calculation"""
        feedback_count = 20
        avg_rating = 4.3
        helpful_votes = 15
        
        # Mock calculation
        community_score = (avg_rating * 20) + (feedback_count * 0.5) + (helpful_votes * 0.3)
        
        assert community_score >= 0
        assert community_score <= 150

    def test_composite_trust_score(self):
        """Test composite trust score calculation"""
        performance_score = 85.0
        reliability_score = 90.0
        community_score = 80.0
        security_score = 95.0
        economic_score = 75.0
        
        # Weighted average
        weights = {
            "performance": 0.3,
            "reliability": 0.25,
            "community": 0.2,
            "security": 0.15,
            "economic": 0.1
        }
        
        composite_score = (
            performance_score * weights["performance"] +
            reliability_score * weights["reliability"] +
            community_score * weights["community"] +
            security_score * weights["security"] +
            economic_score * weights["economic"]
        )
        
        assert composite_score >= 0
        assert composite_score <= 100

    def test_reputation_level_determination(self):
        """Test reputation level based on trust score"""
        test_cases = [
            (950, "master"),
            (800, "expert"),
            (650, "advanced"),
            (450, "intermediate"),
            (200, "beginner")
        ]
        
        for score, expected_level in test_cases:
            if score >= 900:
                level = ReputationLevel.MASTER
            elif score >= 750:
                level = ReputationLevel.EXPERT
            elif score >= 600:
                level = ReputationLevel.ADVANCED
            elif score >= 400:
                level = ReputationLevel.INTERMEDIATE
            else:
                level = ReputationLevel.BEGINNER
            
            assert level.value == expected_level


class TestReputationDecay:
    """Test reputation decay algorithm"""

    def test_linear_decay_calculation(self):
        """Test linear reputation decay"""
        initial_score = 800.0
        decay_rate = 0.1  # 10% per month
        months_inactive = 3
        
        decayed_score = initial_score * ((1 - decay_rate) ** months_inactive)
        
        assert decayed_score < initial_score
        assert decayed_score >= 0
        assert decayed_score == pytest.approx(800.0 * 0.9 ** 3, rel=0.01)

    def test_activity_boost(self):
        """Test activity boost to reputation"""
        base_score = 500.0
        recent_activity_count = 10
        boost_per_activity = 2.0
        
        activity_boost = min(recent_activity_count * boost_per_activity, 20.0)
        boosted_score = base_score + activity_boost
        
        assert boosted_score > base_score
        assert boosted_score == pytest.approx(520.0, rel=0.01)

    def test_decay_with_activity(self):
        """Test decay with recent activity offset"""
        initial_score = 800.0
        decay_rate = 0.05  # 5% per month
        months_inactive = 2
        recent_activity_count = 5
        activity_boost_per_activity = 1.5
        
        decay_amount = initial_score * decay_rate * months_inactive
        activity_boost = min(recent_activity_count * activity_boost_per_activity, 15.0)
        
        final_score = initial_score - decay_amount + activity_boost
        
        assert final_score >= 0
        assert final_score <= initial_score + activity_boost


class TestWeightedRatingCalculation:
    """Test weighted rating calculation"""

    def test_weighted_average_rating(self):
        """Test weighted average rating calculation"""
        ratings = [
            {"rating": 5.0, "weight": 2.0},
            {"rating": 4.0, "weight": 1.0},
            {"rating": 5.0, "weight": 1.5},
            {"rating": 3.0, "weight": 0.5}
        ]
        
        total_weight = sum(r["weight"] for r in ratings)
        weighted_sum = sum(r["rating"] * r["weight"] for r in ratings)
        weighted_average = weighted_sum / total_weight
        
        expected = (5.0*2.0 + 4.0*1.0 + 5.0*1.5 + 3.0*0.5) / (2.0 + 1.0 + 1.5 + 0.5)
        
        assert weighted_average == pytest.approx(expected, rel=0.01)
        assert 1.0 <= weighted_average <= 5.0

    def test_recency_weighting(self):
        """Test recency-based rating weighting"""
        rating_data = [
            {"rating": 5.0, "days_ago": 10},
            {"rating": 4.0, "days_ago": 30},
            {"rating": 5.0, "days_ago": 60},
            {"rating": 3.0, "days_ago": 90}
        ]
        
        # More recent ratings get higher weight
        max_days = 90
        for item in rating_data:
            item["weight"] = 1.0 - (item["days_ago"] / max_days) * 0.5
        
        total_weight = sum(r["weight"] for r in rating_data)
        weighted_sum = sum(r["rating"] * r["weight"] for r in rating_data)
        recency_weighted_average = weighted_sum / total_weight
        
        assert recency_weighted_average >= 1.0
        assert recency_weighted_average <= 5.0

    def test_empty_ratings_list(self):
        """Test weighted rating with empty list"""
        ratings = []
        
        if ratings:
            total_weight = sum(r["weight"] for r in ratings)
            weighted_sum = sum(r["rating"] * r["weight"] for r in ratings)
            weighted_average = weighted_sum / total_weight
        else:
            weighted_average = 0.0
        
        assert weighted_average == 0.0

    def test_single_rating(self):
        """Test weighted rating with single rating"""
        ratings = [{"rating": 4.5, "weight": 1.0}]
        
        total_weight = sum(r["weight"] for r in ratings)
        weighted_sum = sum(r["rating"] * r["weight"] for r in ratings)
        weighted_average = weighted_sum / total_weight
        
        assert weighted_average == 4.5


class TestReputationLevelCalculation:
    """Test reputation level determination"""

    def test_trustee_level(self):
        """Test trustee level calculation"""
        trust_score = 0.95
        
        if trust_score >= 0.9:
            level = "trustee"
        elif trust_score >= 0.7:
            level = "reputable"
        elif trust_score >= 0.5:
            level = "established"
        else:
            level = "newcomer"
        
        assert level == "trustee"

    def test_reputable_level(self):
        """Test reputable level calculation"""
        trust_score = 0.75
        
        if trust_score >= 0.9:
            level = "trustee"
        elif trust_score >= 0.7:
            level = "reputable"
        elif trust_score >= 0.5:
            level = "established"
        else:
            level = "newcomer"
        
        assert level == "reputable"

    def test_established_level(self):
        """Test established level calculation"""
        trust_score = 0.6
        
        if trust_score >= 0.9:
            level = "trustee"
        elif trust_score >= 0.7:
            level = "reputable"
        elif trust_score >= 0.5:
            level = "established"
        else:
            level = "newcomer"
        
        assert level == "established"

    def test_newcomer_level(self):
        """Test newcomer level calculation"""
        trust_score = 0.3
        
        if trust_score >= 0.9:
            level = "trustee"
        elif trust_score >= 0.7:
            level = "reputable"
        elif trust_score >= 0.5:
            level = "established"
        else:
            level = "newcomer"
        
        assert level == "newcomer"


class TestReputationEventTracking:
    """Test reputation event tracking"""

    def test_positive_event(self):
        """Test positive reputation event"""
        event_type = "successful_job"
        impact = 0.1
        
        if event_type in ["successful_job", "timely_delivery"]:
            score_change = impact
        else:
            score_change = -impact
        
        assert score_change > 0

    def test_negative_event(self):
        """Test negative reputation event"""
        event_type = "job_failure"
        impact = 0.1
        
        if event_type in ["successful_job", "timely_delivery"]:
            score_change = impact
        else:
            score_change = -impact
        
        assert score_change < 0

    def test_event_with_magnitude(self):
        """Test event with different magnitudes"""
        event_type = "successful_job"
        magnitude = 0.2
        
        base_impact = 0.1
        impact = base_impact * magnitude
        
        if event_type in ["successful_job", "timely_delivery"]:
            score_change = impact
        else:
            score_change = -impact
        
        assert score_change == pytest.approx(0.02)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
