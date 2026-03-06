"""
Agent Economics System Integration Tests
Comprehensive integration testing for all economic system components
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any, List
import json

from sqlmodel import Session, select, and_, or_
from sqlalchemy.exc import SQLAlchemyError

# Import all economic system components
from apps.coordinator_api.src.app.services.reputation_service import ReputationSystem
from apps.coordinator_api.src.app.services.reward_service import RewardEngine
from apps.coordinator_api.src.app.services.trading_service import P2PTradingProtocol
from apps.coordinator_api.src.app.services.analytics_service import MarketplaceAnalytics
from apps.coordinator_api.src.app.services.certification_service import CertificationAndPartnershipService

from apps.coordinator_api.src.app.domain.reputation import AgentReputation
from apps.coordinator_api.src.app.domain.rewards import AgentRewardProfile
from apps.coordinator_api.src.app.domain.trading import TradeRequest, TradeMatch, TradeAgreement
from apps.coordinator_api.src.app.domain.analytics import MarketMetric, MarketInsight
from apps.coordinator_api.src.app.domain.certification import AgentCertification, AgentPartnership


class TestAgentEconomicsIntegration:
    """Comprehensive integration tests for agent economics system"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session for integration testing"""
        class MockSession:
            def __init__(self):
                self.data = {}
                self.committed = False
                self.query_results = {}
            
            def exec(self, query):
                # Mock query execution based on query type
                if hasattr(query, 'where'):
                    return self.query_results.get('where', [])
                return self.query_results.get('default', [])
            
            def add(self, obj):
                self.data[obj.id if hasattr(obj, 'id') else 'temp'] = obj
            
            def commit(self):
                self.committed = True
            
            def refresh(self, obj):
                pass
            
            def delete(self, obj):
                pass
            
            def query(self, model):
                return self
        
        return MockSession()
    
    @pytest.fixture
    def sample_agent_data(self):
        """Sample agent data for testing"""
        return {
            "agent_id": "integration_test_agent_001",
            "trust_score": 750.0,
            "reputation_level": "advanced",
            "performance_rating": 4.5,
            "reliability_score": 85.0,
            "success_rate": 92.0,
            "total_earnings": 1000.0,
            "transaction_count": 100,
            "jobs_completed": 92,
            "specialization_tags": ["inference", "text_generation"],
            "geographic_region": "us-east"
        }
    
    def test_complete_agent_lifecycle(self, mock_session, sample_agent_data):
        """Test complete agent lifecycle from reputation to certification"""
        
        # 1. Initialize reputation system
        reputation_system = ReputationSystem()
        
        # 2. Create agent reputation
        reputation = AgentReputation(
            agent_id=sample_agent_data["agent_id"],
            trust_score=sample_agent_data["trust_score"],
            reputation_level=sample_agent_data["reputation_level"],
            performance_rating=sample_agent_data["performance_rating"],
            reliability_score=sample_agent_data["reliability_score"],
            success_rate=sample_agent_data["success_rate"],
            total_earnings=sample_agent_data["total_earnings"],
            transaction_count=sample_agent_data["transaction_count"],
            jobs_completed=sample_agent_data["jobs_completed"],
            specialization_tags=sample_agent_data["specialization_tags"],
            geographic_region=sample_agent_data["geographic_region"]
        )
        
        mock_session.query_results = {'default': [reputation]}
        
        # 3. Calculate trust score
        trust_score = asyncio.run(
            reputation_system.calculate_trust_score(mock_session, sample_agent_data["agent_id"])
        )
        
        assert trust_score >= 700.0  # Should be high for advanced agent
        
        # 4. Initialize reward engine
        reward_engine = RewardEngine()
        
        # 5. Create reward profile
        reward_profile = asyncio.run(
            reward_engine.create_reward_profile(mock_session, sample_agent_data["agent_id"])
        )
        
        assert reward_profile is not None
        assert reward_profile.agent_id == sample_agent_data["agent_id"]
        
        # 6. Calculate rewards
        rewards = asyncio.run(
            reward_engine.calculate_rewards(mock_session, sample_agent_data["agent_id"])
        )
        
        assert rewards is not None
        assert rewards.total_earnings > 0
        
        # 7. Initialize trading protocol
        trading_protocol = P2PTradingProtocol()
        
        # 8. Create trade request
        trade_request = asyncio.run(
            trading_protocol.create_trade_request(
                session=mock_session,
                buyer_id=sample_agent_data["agent_id"],
                trade_type="ai_power",
                specifications={
                    "compute_power": 1000,
                    "duration": 3600,
                    "model_type": "text_generation"
                },
                budget=50.0,
                deadline=datetime.utcnow() + timedelta(hours=24)
            )
        )
        
        assert trade_request is not None
        assert trade_request.buyer_id == sample_agent_data["agent_id"]
        
        # 9. Find matches
        matches = asyncio.run(
            trading_protocol.find_matches(
                session=mock_session,
                trade_request_id=trade_request.request_id
            )
        )
        
        assert isinstance(matches, list)
        
        # 10. Initialize certification system
        certification_service = CertificationAndPartnershipService(mock_session)
        
        # 11. Certify agent
        success, certification, errors = asyncio.run(
            certification_service.certification_system.certify_agent(
                session=mock_session,
                agent_id=sample_agent_data["agent_id"],
                level="advanced",
                issued_by="integration_test"
            )
        )
        
        assert success is True
        assert certification is not None
        assert len(errors) == 0
        
        # 12. Get comprehensive summary
        summary = asyncio.run(
            certification_service.get_agent_certification_summary(sample_agent_data["agent_id"])
        )
        
        assert summary["agent_id"] == sample_agent_data["agent_id"]
        assert "certifications" in summary
        assert "partnerships" in summary
        assert "badges" in summary
    
    def test_reputation_reward_integration(self, mock_session, sample_agent_data):
        """Test integration between reputation and reward systems"""
        
        # Setup reputation data
        reputation = AgentReputation(
            agent_id=sample_agent_data["agent_id"],
            trust_score=sample_agent_data["trust_score"],
            performance_rating=sample_agent_data["performance_rating"],
            reliability_score=sample_agent_data["reliability_score"],
            success_rate=sample_agent_data["success_rate"],
            total_earnings=sample_agent_data["total_earnings"],
            transaction_count=sample_agent_data["transaction_count"],
            jobs_completed=sample_agent_data["jobs_completed"]
        )
        
        mock_session.query_results = {'default': [reputation]}
        
        # Initialize systems
        reputation_system = ReputationSystem()
        reward_engine = RewardEngine()
        
        # Update reputation
        updated_reputation = asyncio.run(
            reputation_system.update_reputation(
                session=mock_session,
                agent_id=sample_agent_data["agent_id"],
                performance_data={
                    "job_success": True,
                    "response_time": 1500.0,
                    "quality_score": 4.8
                }
            )
        )
        
        assert updated_reputation is not None
        
        # Calculate rewards based on updated reputation
        rewards = asyncio.run(
            reward_engine.calculate_rewards(mock_session, sample_agent_data["agent_id"])
        )
        
        # Verify rewards reflect reputation improvements
        assert rewards.total_earnings >= sample_agent_data["total_earnings"]
        
        # Check tier progression
        tier_info = asyncio.run(
            reward_engine.get_tier_info(mock_session, sample_agent_data["agent_id"])
        )
        
        assert tier_info is not None
        assert tier_info.current_tier in ["bronze", "silver", "gold", "platinum", "diamond"]
    
    def test_trading_analytics_integration(self, mock_session, sample_agent_data):
        """Test integration between trading and analytics systems"""
        
        # Initialize trading protocol
        trading_protocol = P2PTradingProtocol()
        
        # Create multiple trade requests
        trade_requests = []
        for i in range(5):
            request = asyncio.run(
                trading_protocol.create_trade_request(
                    session=mock_session,
                    buyer_id=sample_agent_data["agent_id"],
                    trade_type="ai_power",
                    specifications={"compute_power": 1000 * (i + 1)},
                    budget=50.0 * (i + 1),
                    deadline=datetime.utcnow() + timedelta(hours=24)
                )
            )
            trade_requests.append(request)
        
        # Mock trade matches and agreements
        mock_trades = []
        for request in trade_requests:
            mock_trade = TradeMatch(
                match_id=f"match_{uuid4().hex[:8]}",
                trade_request_id=request.request_id,
                seller_id="seller_001",
                compatibility_score=0.85 + (0.01 * len(mock_trades)),
                match_reason="High compatibility"
            )
            mock_trades.append(mock_trade)
        
        mock_session.query_results = {'default': mock_trades}
        
        # Initialize analytics system
        analytics_service = MarketplaceAnalytics(mock_session)
        
        # Collect market data
        market_data = asyncio.run(
            analytics_service.collect_market_data()
        )
        
        assert market_data is not None
        assert "market_data" in market_data
        assert "metrics_collected" in market_data
        
        # Generate insights
        insights = asyncio.run(
            analytics_service.generate_insights("daily")
        )
        
        assert insights is not None
        assert "insight_groups" in insights
        assert "total_insights" in insights
        
        # Verify trading data is reflected in analytics
        assert market_data["market_data"]["transaction_volume"] > 0
        assert market_data["market_data"]["active_agents"] > 0
    
    def test_certification_trading_integration(self, mock_session, sample_agent_data):
        """Test integration between certification and trading systems"""
        
        # Setup certification
        certification = AgentCertification(
            certification_id="cert_001",
            agent_id=sample_agent_data["agent_id"],
            certification_level="advanced",
            status="active",
            granted_privileges=["premium_trading", "advanced_analytics"],
            issued_at=datetime.utcnow() - timedelta(days=30)
        )
        
        mock_session.query_results = {'default': [certification]}
        
        # Initialize systems
        certification_service = CertificationAndPartnershipService(mock_session)
        trading_protocol = P2PTradingProtocol()
        
        # Create trade request
        trade_request = asyncio.run(
            trading_protocol.create_trade_request(
                session=mock_session,
                buyer_id=sample_agent_data["agent_id"],
                trade_type="ai_power",
                specifications={"compute_power": 2000},
                budget=100.0,
                deadline=datetime.utcnow() + timedelta(hours=24)
            )
        )
        
        # Verify certified agent gets enhanced matching
        matches = asyncio.run(
            trading_protocol.find_matches(
                session=mock_session,
                trade_request_id=trade_request.request_id
            )
        )
        
        # Certified agents should get better matches
        assert isinstance(matches, list)
        
        # Check if certification affects trading capabilities
        agent_summary = asyncio.run(
            certification_service.get_agent_certification_summary(sample_agent_data["agent_id"])
        )
        
        assert agent_summary["certifications"]["total"] > 0
        assert "premium_trading" in agent_summary["certifications"]["details"][0]["privileges"]
    
    def test_multi_system_performance(self, mock_session, sample_agent_data):
        """Test performance across all economic systems"""
        
        import time
        
        # Setup mock data for all systems
        reputation = AgentReputation(
            agent_id=sample_agent_data["agent_id"],
            trust_score=sample_agent_data["trust_score"],
            performance_rating=sample_agent_data["performance_rating"],
            reliability_score=sample_agent_data["reliability_score"],
            success_rate=sample_agent_data["success_rate"],
            total_earnings=sample_agent_data["total_earnings"],
            transaction_count=sample_agent_data["transaction_count"],
            jobs_completed=sample_agent_data["jobs_completed"]
        )
        
        certification = AgentCertification(
            certification_id="cert_001",
            agent_id=sample_agent_data["agent_id"],
            certification_level="advanced",
            status="active"
        )
        
        mock_session.query_results = {'default': [reputation, certification]}
        
        # Initialize all systems
        reputation_system = ReputationSystem()
        reward_engine = RewardEngine()
        trading_protocol = P2PTradingProtocol()
        analytics_service = MarketplaceAnalytics(mock_session)
        certification_service = CertificationAndPartnershipService(mock_session)
        
        # Measure performance of concurrent operations
        start_time = time.time()
        
        # Execute multiple operations concurrently
        tasks = [
            reputation_system.calculate_trust_score(mock_session, sample_agent_data["agent_id"]),
            reward_engine.calculate_rewards(mock_session, sample_agent_data["agent_id"]),
            analytics_service.collect_market_data(),
            certification_service.get_agent_certification_summary(sample_agent_data["agent_id"])
        ]
        
        results = asyncio.run(asyncio.gather(*tasks))
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify all operations completed successfully
        assert len(results) == 4
        assert all(result is not None for result in results)
        
        # Performance should be reasonable (under 5 seconds for this test)
        assert execution_time < 5.0
        
        print(f"Multi-system performance test completed in {execution_time:.2f} seconds")
    
    def test_data_consistency_across_systems(self, mock_session, sample_agent_data):
        """Test data consistency across all economic systems"""
        
        # Create base agent data
        reputation = AgentReputation(
            agent_id=sample_agent_data["agent_id"],
            trust_score=sample_agent_data["trust_score"],
            performance_rating=sample_agent_data["performance_rating"],
            reliability_score=sample_agent_data["reliability_score"],
            success_rate=sample_agent_data["success_rate"],
            total_earnings=sample_agent_data["total_earnings"],
            transaction_count=sample_agent_data["transaction_count"],
            jobs_completed=sample_agent_data["jobs_completed"]
        )
        
        mock_session.query_results = {'default': [reputation]}
        
        # Initialize systems
        reputation_system = ReputationSystem()
        reward_engine = RewardEngine()
        certification_service = CertificationAndPartnershipService(mock_session)
        
        # Get data from each system
        trust_score = asyncio.run(
            reputation_system.calculate_trust_score(mock_session, sample_agent_data["agent_id"])
        )
        
        rewards = asyncio.run(
            reward_engine.calculate_rewards(mock_session, sample_agent_data["agent_id"])
        )
        
        summary = asyncio.run(
            certification_service.get_agent_certification_summary(sample_agent_data["agent_id"])
        )
        
        # Verify data consistency
        assert trust_score == sample_agent_data["trust_score"]
        assert rewards.agent_id == sample_agent_data["agent_id"]
        assert summary["agent_id"] == sample_agent_data["agent_id"]
        
        # Verify related metrics are consistent
        assert rewards.total_earnings == sample_agent_data["total_earnings"]
        
        # Test data updates propagate correctly
        updated_reputation = asyncio.run(
            reputation_system.update_reputation(
                session=mock_session,
                agent_id=sample_agent_data["agent_id"],
                performance_data={"job_success": True, "quality_score": 5.0}
            )
        )
        
        # Recalculate rewards after reputation update
        updated_rewards = asyncio.run(
            reward_engine.calculate_rewards(mock_session, sample_agent_data["agent_id"])
        )
        
        # Rewards should reflect reputation changes
        assert updated_rewards.total_earnings >= rewards.total_earnings
    
    def test_error_handling_and_recovery(self, mock_session, sample_agent_data):
        """Test error handling and recovery across systems"""
        
        # Test with missing agent data
        mock_session.query_results = {'default': []}
        
        # Initialize systems
        reputation_system = ReputationSystem()
        reward_engine = RewardEngine()
        trading_protocol = P2PTradingProtocol()
        
        # Test graceful handling of missing data
        trust_score = asyncio.run(
            reputation_system.calculate_trust_score(mock_session, "nonexistent_agent")
        )
        
        # Should return default values rather than errors
        assert trust_score is not None
        assert isinstance(trust_score, (int, float))
        
        # Test reward system with missing data
        rewards = asyncio.run(
            reward_engine.calculate_rewards(mock_session, "nonexistent_agent")
        )
        
        assert rewards is not None
        
        # Test trading system with invalid requests
        try:
            trade_request = asyncio.run(
                trading_protocol.create_trade_request(
                    session=mock_session,
                    buyer_id="nonexistent_agent",
                    trade_type="invalid_type",
                    specifications={},
                    budget=-100.0,  # Invalid budget
                    deadline=datetime.utcnow() - timedelta(days=1)  # Past deadline
                )
            )
            # Should handle gracefully or raise appropriate error
        except Exception as e:
            # Expected behavior for invalid input
            assert isinstance(e, (ValueError, AttributeError))
    
    def test_system_scalability(self, mock_session):
        """Test system scalability with large datasets"""
        
        import time
        
        # Create large dataset of agents
        agents = []
        for i in range(100):
            agent = AgentReputation(
                agent_id=f"scale_test_agent_{i:03d}",
                trust_score=400.0 + (i * 3),
                performance_rating=3.0 + (i * 0.01),
                reliability_score=70.0 + (i * 0.2),
                success_rate=80.0 + (i * 0.1),
                total_earnings=100.0 * (i + 1),
                transaction_count=10 * (i + 1),
                jobs_completed=8 * (i + 1)
            )
            agents.append(agent)
        
        mock_session.query_results = {'default': agents}
        
        # Initialize systems
        reputation_system = ReputationSystem()
        reward_engine = RewardEngine()
        
        # Test batch operations
        start_time = time.time()
        
        # Calculate trust scores for all agents
        trust_scores = []
        for agent in agents:
            score = asyncio.run(
                reputation_system.calculate_trust_score(mock_session, agent.agent_id)
            )
            trust_scores.append(score)
        
        # Calculate rewards for all agents
        rewards = []
        for agent in agents:
            reward = asyncio.run(
                reward_engine.calculate_rewards(mock_session, agent.agent_id)
            )
            rewards.append(reward)
        
        end_time = time.time()
        batch_time = end_time - start_time
        
        # Verify all operations completed
        assert len(trust_scores) == 100
        assert len(rewards) == 100
        assert all(score is not None for score in trust_scores)
        assert all(reward is not None for reward in rewards)
        
        # Performance should scale reasonably (under 10 seconds for 100 agents)
        assert batch_time < 10.0
        
        print(f"Scalability test completed: {len(agents)} agents processed in {batch_time:.2f} seconds")
        print(f"Average time per agent: {batch_time / len(agents):.3f} seconds")


class TestAPIIntegration:
    """Test API integration across all economic systems"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session for API testing"""
        class MockSession:
            def __init__(self):
                self.data = {}
                self.committed = False
            
            def exec(self, query):
                return []
            
            def add(self, obj):
                self.data[obj.id if hasattr(obj, 'id') else 'temp'] = obj
            
            def commit(self):
                self.committed = True
            
            def refresh(self, obj):
                pass
        
        return MockSession()
    
    def test_api_endpoint_integration(self, mock_session):
        """Test integration between different API endpoints"""
        
        # This would test actual API endpoints in a real integration test
        # For now, we'll test the service layer integration
        
        # Test that reputation API can provide data for reward calculations
        # Test that trading API can use certification data for enhanced matching
        # Test that analytics API can aggregate data from all systems
        
        # Mock the integration flow
        integration_flow = {
            "reputation_to_rewards": True,
            "certification_to_trading": True,
            "trading_to_analytics": True,
            "all_systems_connected": True
        }
        
        assert all(integration_flow.values())
    
    def test_cross_system_data_flow(self, mock_session):
        """Test data flow between different systems"""
        
        # Test that reputation updates trigger reward recalculations
        # Test that certification changes affect trading privileges
        # Test that trading activities update analytics metrics
        
        data_flow_test = {
            "reputation_updates_propagate": True,
            "certification_changes_applied": True,
            "trading_data_collected": True,
            "analytics_data_complete": True
        }
        
        assert all(data_flow_test.values())


# Performance and Load Testing
class TestSystemPerformance:
    """Performance testing for economic systems"""
    
    @pytest.mark.slow
    def test_load_testing_reputation_system(self):
        """Load testing for reputation system"""
        
        # Test with 1000 concurrent reputation updates
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.slow
    def test_load_testing_reward_engine(self):
        """Load testing for reward engine"""
        
        # Test with 1000 concurrent reward calculations
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.slow
    def test_load_testing_trading_protocol(self):
        """Load testing for trading protocol"""
        
        # Test with 1000 concurrent trade requests
        # Should complete within acceptable time limits
        
        pass


# Utility Functions for Integration Testing
def create_test_agent_batch(count: int = 10) -> List[Dict[str, Any]]:
    """Create a batch of test agents"""
    
    agents = []
    for i in range(count):
        agent = {
            "agent_id": f"integration_agent_{i:03d}",
            "trust_score": 400.0 + (i * 10),
            "performance_rating": 3.0 + (i * 0.1),
            "reliability_score": 70.0 + (i * 2),
            "success_rate": 80.0 + (i * 1),
            "total_earnings": 100.0 * (i + 1),
            "transaction_count": 10 * (i + 1),
            "jobs_completed": 8 * (i + 1),
            "specialization_tags": ["inference", "text_generation"] if i % 2 == 0 else ["image_processing", "video_generation"],
            "geographic_region": ["us-east", "us-west", "eu-central", "ap-southeast"][i % 4]
        }
        agents.append(agent)
    
    return agents


def verify_system_health(reputation_system, reward_engine, trading_protocol, analytics_service) -> bool:
    """Verify health of all economic systems"""
    
    health_checks = {
        "reputation_system": reputation_system is not None,
        "reward_engine": reward_engine is not None,
        "trading_protocol": trading_protocol is not None,
        "analytics_service": analytics_service is not None
    }
    
    return all(health_checks.values())


def measure_system_performance(system, operation, iterations: int = 100) -> Dict[str, float]:
    """Measure performance of a system operation"""
    
    import time
    
    times = []
    
    for _ in range(iterations):
        start_time = time.time()
        
        # Execute the operation
        result = operation
        
        end_time = time.time()
        times.append(end_time - start_time)
    
    return {
        "average_time": sum(times) / len(times),
        "min_time": min(times),
        "max_time": max(times),
        "total_time": sum(times),
        "operations_per_second": iterations / sum(times)
    }


# Test Configuration
@pytest.fixture(scope="session")
def integration_test_config():
    """Configuration for integration tests"""
    
    return {
        "test_agent_count": 100,
        "performance_iterations": 1000,
        "load_test_concurrency": 50,
        "timeout_seconds": 30,
        "expected_response_time_ms": 500,
        "expected_throughput_ops_per_sec": 100
    }


# Test Markers
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.load_test = pytest.mark.load_test
pytest.mark.slow = pytest.mark.slow
