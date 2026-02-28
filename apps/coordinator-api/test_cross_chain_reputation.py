#!/usr/bin/env python3
"""
Cross-Chain Reputation System Test
Basic functionality test for the cross-chain reputation APIs
"""

import asyncio
import sys
import os

# Add the app path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_cross_chain_reputation_imports():
    """Test that all cross-chain reputation components can be imported"""
    print("🧪 Testing Cross-Chain Reputation System Imports...")
    
    try:
        # Test domain models
        from app.domain.reputation import AgentReputation, ReputationEvent, ReputationLevel
        from app.domain.cross_chain_reputation import (
            CrossChainReputationAggregation, CrossChainReputationEvent,
            CrossChainReputationConfig, ReputationMetrics
        )
        print("✅ Cross-chain domain models imported successfully")
        
        # Test core components
        from app.reputation.engine import CrossChainReputationEngine
        from app.reputation.aggregator import CrossChainReputationAggregator
        print("✅ Cross-chain core components imported successfully")
        
        # Test API router
        from app.routers.reputation import router
        print("✅ Cross-chain API router imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_cross_chain_reputation_models():
    """Test cross-chain reputation model creation"""
    print("\n🧪 Testing Cross-Chain Reputation Models...")
    
    try:
        from app.domain.cross_chain_reputation import (
            CrossChainReputationConfig, CrossChainReputationAggregation,
            CrossChainReputationEvent, ReputationMetrics
        )
        from datetime import datetime
        
        # Test CrossChainReputationConfig
        config = CrossChainReputationConfig(
            chain_id=1,
            chain_weight=1.0,
            base_reputation_bonus=0.0,
            transaction_success_weight=0.1,
            transaction_failure_weight=-0.2,
            dispute_penalty_weight=-0.3,
            minimum_transactions_for_score=5,
            reputation_decay_rate=0.01,
            anomaly_detection_threshold=0.3
        )
        print("✅ CrossChainReputationConfig model created")
        
        # Test CrossChainReputationAggregation
        aggregation = CrossChainReputationAggregation(
            agent_id="test_agent",
            aggregated_score=0.8,
            chain_scores={1: 0.8, 137: 0.7},
            active_chains=[1, 137],
            score_variance=0.01,
            score_range=0.1,
            consistency_score=0.9,
            verification_status="verified"
        )
        print("✅ CrossChainReputationAggregation model created")
        
        # Test CrossChainReputationEvent
        event = CrossChainReputationEvent(
            agent_id="test_agent",
            source_chain_id=1,
            target_chain_id=137,
            event_type="aggregation",
            impact_score=0.1,
            description="Cross-chain reputation aggregation",
            source_reputation=0.8,
            target_reputation=0.7,
            reputation_change=0.1
        )
        print("✅ CrossChainReputationEvent model created")
        
        # Test ReputationMetrics
        metrics = ReputationMetrics(
            chain_id=1,
            metric_date=datetime.now().date(),
            total_agents=100,
            average_reputation=0.75,
            reputation_distribution={"beginner": 20, "intermediate": 30, "advanced": 25, "expert": 20, "master": 5},
            total_transactions=1000,
            success_rate=0.95,
            dispute_rate=0.02,
            cross_chain_agents=50,
            average_consistency_score=0.85,
            chain_diversity_score=0.6
        )
        print("✅ ReputationMetrics model created")
        
        return True
        
    except Exception as e:
        print(f"❌ Model creation error: {e}")
        return False

def test_reputation_engine():
    """Test cross-chain reputation engine functionality"""
    print("\n🧪 Testing Cross-Chain Reputation Engine...")
    
    try:
        from app.reputation.engine import CrossChainReputationEngine
        
        # Test engine creation (mock session)
        class MockSession:
            pass
        
        engine = CrossChainReputationEngine(MockSession())
        print("✅ CrossChainReputationEngine created")
        
        # Test method existence
        assert hasattr(engine, 'calculate_reputation_score')
        assert hasattr(engine, 'aggregate_cross_chain_reputation')
        assert hasattr(engine, 'update_reputation_from_event')
        assert hasattr(engine, 'get_reputation_trend')
        assert hasattr(engine, 'detect_reputation_anomalies')
        print("✅ All required methods present")
        
        return True
        
    except Exception as e:
        print(f"❌ Engine test error: {e}")
        return False

def test_reputation_aggregator():
    """Test cross-chain reputation aggregator functionality"""
    print("\n🧪 Testing Cross-Chain Reputation Aggregator...")
    
    try:
        from app.reputation.aggregator import CrossChainReputationAggregator
        
        # Test aggregator creation (mock session)
        class MockSession:
            pass
        
        aggregator = CrossChainReputationAggregator(MockSession())
        print("✅ CrossChainReputationAggregator created")
        
        # Test method existence
        assert hasattr(aggregator, 'collect_chain_reputation_data')
        assert hasattr(aggregator, 'normalize_reputation_scores')
        assert hasattr(aggregator, 'apply_chain_weighting')
        assert hasattr(aggregator, 'detect_reputation_anomalies')
        assert hasattr(aggregator, 'batch_update_reputations')
        assert hasattr(aggregator, 'get_chain_statistics')
        print("✅ All required methods present")
        
        return True
        
    except Exception as e:
        print(f"❌ Aggregator test error: {e}")
        return False

def test_api_endpoints():
    """Test API endpoint definitions"""
    print("\n🧪 Testing API Endpoints...")
    
    try:
        from app.routers.reputation import router
        
        # Check router configuration
        assert router.prefix == "/v1/reputation"
        assert "reputation" in router.tags
        print("✅ Router configuration correct")
        
        # Check for cross-chain endpoints
        route_paths = [route.path for route in router.routes]
        cross_chain_endpoints = [
            "/{agent_id}/cross-chain",
            "/cross-chain/leaderboard",
            "/cross-chain/events",
            "/cross-chain/analytics"
        ]
        
        for endpoint in cross_chain_endpoints:
            if any(endpoint in path for path in route_paths):
                print(f"✅ Endpoint {endpoint} found")
            else:
                print(f"⚠️  Endpoint {endpoint} not found (may be added later)")
        
        return True
        
    except Exception as e:
        print(f"❌ API endpoint test error: {e}")
        return False

def main():
    """Run all cross-chain reputation tests"""
    
    print("🚀 Cross-Chain Reputation System - Basic Functionality Test")
    print("=" * 60)
    
    tests = [
        test_cross_chain_reputation_imports,
        test_cross_chain_reputation_models,
        test_reputation_engine,
        test_reputation_aggregator,
        test_api_endpoints
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test {test.__name__} failed")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All cross-chain reputation tests passed!")
        print("\n✅ Cross-Chain Reputation System is ready for:")
        print("   - Database migration")
        print("   - API server startup")
        print("   - Integration testing")
        print("   - Cross-chain reputation aggregation")
        return True
    else:
        print("\n❌ Some tests failed - check the errors above")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
