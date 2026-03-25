"""
P2P Trading System Integration Tests
Comprehensive testing for agent-to-agent trading, matching, negotiation, and settlement
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from apps.coordinator_api.src.app.services.trading_service import (
    P2PTradingProtocol, MatchingEngine, NegotiationSystem, SettlementLayer
)
from apps.coordinator_api.src.app.domain.trading import (
    TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement,
    TradeStatus, TradeType, NegotiationStatus, SettlementType
)


class TestMatchingEngine:
    """Test matching engine algorithms"""
    
    @pytest.fixture
    def matching_engine(self):
        return MatchingEngine()
    
    @pytest.fixture
    def sample_buyer_request(self):
        return TradeRequest(
            request_id="req_001",
            buyer_agent_id="buyer_001",
            trade_type=TradeType.AI_POWER,
            title="AI Model Training Service",
            description="Need GPU resources for model training",
            requirements={
                "specifications": {
                    "cpu_cores": 8,
                    "memory_gb": 32,
                    "gpu_count": 2,
                    "gpu_memory_gb": 16
                },
                "timing": {
                    "start_time": datetime.utcnow() + timedelta(hours=2),
                    "duration_hours": 12
                }
            },
            specifications={
                "cpu_cores": 8,
                "memory_gb": 32,
                "gpu_count": 2,
                "gpu_memory_gb": 16
            },
            budget_range={"min": 0.1, "max": 0.2},
            preferred_regions=["us-east", "us-west"],
            service_level_required="premium"
        )
    
    def test_price_compatibility_calculation(self, matching_engine):
        """Test price compatibility calculation"""
        
        # Test perfect match
        buyer_budget = {"min": 0.1, "max": 0.2}
        seller_price = 0.15
        
        score = matching_engine.calculate_price_compatibility(buyer_budget, seller_price)
        assert 0 <= score <= 100
        assert score > 50  # Should be good match
        
        # Test below minimum
        seller_price_low = 0.05
        score_low = matching_engine.calculate_price_compatibility(buyer_budget, seller_price_low)
        assert score_low == 0.0
        
        # Test above maximum
        seller_price_high = 0.25
        score_high = matching_engine.calculate_price_compatibility(buyer_budget, seller_price_high)
        assert score_high == 0.0
        
        # Test infinite budget
        buyer_budget_inf = {"min": 0.1, "max": float('inf')}
        score_inf = matching_engine.calculate_price_compatibility(buyer_budget_inf, seller_price)
        assert score_inf == 100.0
    
    def test_specification_compatibility_calculation(self, matching_engine):
        """Test specification compatibility calculation"""
        
        # Test perfect match
        buyer_specs = {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2}
        seller_specs = {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2}
        
        score = matching_engine.calculate_specification_compatibility(buyer_specs, seller_specs)
        assert score == 100.0
        
        # Test partial match
        seller_partial = {"cpu_cores": 8, "memory_gb": 64, "gpu_count": 2}
        score_partial = matching_engine.calculate_specification_compatibility(buyer_specs, seller_partial)
        assert score_partial == 100.0  # Seller offers more
        
        # Test insufficient match
        seller_insufficient = {"cpu_cores": 4, "memory_gb": 16, "gpu_count": 1}
        score_insufficient = matching_engine.calculate_specification_compatibility(buyer_specs, seller_insufficient)
        assert score_insufficient < 100.0
        assert score_insufficient > 0.0
        
        # Test no overlap
        buyer_no_overlap = {"cpu_cores": 8}
        seller_no_overlap = {"memory_gb": 32}
        score_no_overlap = matching_engine.calculate_specification_compatibility(buyer_no_overlap, seller_no_overlap)
        assert score_no_overlap == 50.0  # Neutral score
    
    def test_timing_compatibility_calculation(self, matching_engine):
        """Test timing compatibility calculation"""
        
        # Test perfect overlap
        buyer_timing = {
            "start_time": datetime.utcnow() + timedelta(hours=2),
            "end_time": datetime.utcnow() + timedelta(hours=14)
        }
        seller_timing = {
            "start_time": datetime.utcnow() + timedelta(hours=2),
            "end_time": datetime.utcnow() + timedelta(hours=14)
        }
        
        score = matching_engine.calculate_timing_compatibility(buyer_timing, seller_timing)
        assert score == 100.0
        
        # Test partial overlap
        seller_partial = {
            "start_time": datetime.utcnow() + timedelta(hours=4),
            "end_time": datetime.utcnow() + timedelta(hours=10)
        }
        score_partial = matching_engine.calculate_timing_compatibility(buyer_timing, seller_partial)
        assert 0 < score_partial < 100
        
        # Test no overlap
        seller_no_overlap = {
            "start_time": datetime.utcnow() + timedelta(hours=20),
            "end_time": datetime.utcnow() + timedelta(hours=30)
        }
        score_no_overlap = matching_engine.calculate_timing_compatibility(buyer_timing, seller_no_overlap)
        assert score_no_overlap == 0.0
    
    def test_geographic_compatibility_calculation(self, matching_engine):
        """Test geographic compatibility calculation"""
        
        # Test perfect match
        buyer_regions = ["us-east", "us-west"]
        seller_regions = ["us-east", "us-west", "eu-central"]
        
        score = matching_engine.calculate_geographic_compatibility(buyer_regions, seller_regions)
        assert score == 100.0
        
        # Test partial match
        seller_partial = ["us-east", "eu-central"]
        score_partial = matching_engine.calculate_geographic_compatibility(buyer_regions, seller_partial)
        assert 0 < score_partial < 100
        
        # Test no match
        seller_no_match = ["eu-central", "ap-southeast"]
        score_no_match = matching_engine.calculate_geographic_compatibility(buyer_regions, seller_no_match)
        assert score_no_match == 20.0  # Low score
        
        # Test excluded regions
        buyer_excluded = ["eu-central"]
        seller_excluded = ["eu-central", "ap-southeast"]
        score_excluded = matching_engine.calculate_geographic_compatibility(
            buyer_regions, seller_regions, buyer_excluded, seller_excluded
        )
        assert score_excluded == 0.0
    
    def test_overall_match_score_calculation(self, matching_engine, sample_buyer_request):
        """Test overall match score calculation"""
        
        seller_offer = {
            "agent_id": "seller_001",
            "price": 0.15,
            "specifications": {
                "cpu_cores": 8,
                "memory_gb": 32,
                "gpu_count": 2,
                "gpu_memory_gb": 16
            },
            "timing": {
                "start_time": datetime.utcnow() + timedelta(hours=2),
                "duration_hours": 12
            },
            "regions": ["us-east", "us-west"],
            "service_level": "premium"
        }
        
        seller_reputation = 750.0
        
        result = matching_engine.calculate_overall_match_score(
            sample_buyer_request, seller_offer, seller_reputation
        )
        
        # Verify result structure
        assert "overall_score" in result
        assert "price_compatibility" in result
        assert "specification_compatibility" in result
        assert "timing_compatibility" in result
        assert "reputation_compatibility" in result
        assert "geographic_compatibility" in result
        assert "confidence_level" in result
        
        # Verify score ranges
        assert 0 <= result["overall_score"] <= 100
        assert 0 <= result["confidence_level"] <= 1
        
        # Should be a good match
        assert result["overall_score"] > 60  # Above minimum threshold
    
    def test_find_matches(self, matching_engine, sample_buyer_request):
        """Test finding matches for a trade request"""
        
        seller_offers = [
            {
                "agent_id": "seller_001",
                "price": 0.15,
                "specifications": {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2},
                "timing": {"start_time": datetime.utcnow() + timedelta(hours=2), "duration_hours": 12},
                "regions": ["us-east", "us-west"],
                "service_level": "premium"
            },
            {
                "agent_id": "seller_002",
                "price": 0.25,
                "specifications": {"cpu_cores": 4, "memory_gb": 16, "gpu_count": 1},
                "timing": {"start_time": datetime.utcnow() + timedelta(hours=4), "duration_hours": 8},
                "regions": ["eu-central"],
                "service_level": "standard"
            },
            {
                "agent_id": "seller_003",
                "price": 0.12,
                "specifications": {"cpu_cores": 16, "memory_gb": 64, "gpu_count": 4},
                "timing": {"start_time": datetime.utcnow() + timedelta(hours=1), "duration_hours": 24},
                "regions": ["us-east", "us-west", "ap-southeast"],
                "service_level": "premium"
            }
        ]
        
        seller_reputations = {
            "seller_001": 750.0,
            "seller_002": 600.0,
            "seller_003": 850.0
        }
        
        matches = matching_engine.find_matches(
            sample_buyer_request, seller_offers, seller_reputations
        )
        
        # Should find matches above threshold
        assert len(matches) > 0
        assert len(matches) <= matching_engine.max_matches_per_request
        
        # Should be sorted by score (descending)
        for i in range(len(matches) - 1):
            assert matches[i]["match_score"] >= matches[i + 1]["match_score"]
        
        # All matches should be above minimum threshold
        for match in matches:
            assert match["match_score"] >= matching_engine.min_match_score


class TestNegotiationSystem:
    """Test negotiation system functionality"""
    
    @pytest.fixture
    def negotiation_system(self):
        return NegotiationSystem()
    
    @pytest.fixture
    def sample_buyer_request(self):
        return TradeRequest(
            request_id="req_001",
            buyer_agent_id="buyer_001",
            trade_type=TradeType.AI_POWER,
            title="AI Model Training Service",
            budget_range={"min": 0.1, "max": 0.2},
            specifications={"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2},
            start_time=datetime.utcnow() + timedelta(hours=2),
            duration_hours=12,
            service_level_required="premium"
        )
    
    @pytest.fixture
    def sample_seller_offer(self):
        return {
            "agent_id": "seller_001",
            "price": 0.15,
            "specifications": {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2},
            "timing": {"start_time": datetime.utcnow() + timedelta(hours=2), "duration_hours": 12},
            "regions": ["us-east", "us-west"],
            "service_level": "premium",
            "terms": {"settlement_type": "escrow", "delivery_guarantee": True}
        }
    
    def test_generate_initial_offer(self, negotiation_system, sample_buyer_request, sample_seller_offer):
        """Test initial offer generation"""
        
        initial_offer = negotiation_system.generate_initial_offer(
            sample_buyer_request, sample_seller_offer
        )
        
        # Verify offer structure
        assert "price" in initial_offer
        assert "specifications" in initial_offer
        assert "timing" in initial_offer
        assert "service_level" in initial_offer
        assert "payment_terms" in initial_offer
        assert "delivery_terms" in initial_offer
        
        # Price should be between buyer budget and seller price
        assert sample_buyer_request.budget_range["min"] <= initial_offer["price"] <= sample_seller_offer["price"]
        
        # Service level should be appropriate
        assert initial_offer["service_level"] in ["basic", "standard", "premium"]
        
        # Payment terms should include escrow
        assert initial_offer["payment_terms"]["settlement_type"] == "escrow"
    
    def test_merge_specifications(self, negotiation_system):
        """Test specification merging"""
        
        buyer_specs = {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2, "storage_gb": 100}
        seller_specs = {"cpu_cores": 8, "memory_gb": 64, "gpu_count": 2, "gpu_memory_gb": 16}
        
        merged = negotiation_system.merge_specifications(buyer_specs, seller_specs)
        
        # Should include all buyer requirements
        assert merged["cpu_cores"] == 8
        assert merged["memory_gb"] == 32
        assert merged["gpu_count"] == 2
        assert merged["storage_gb"] == 100
        
        # Should include additional seller capabilities
        assert merged["gpu_memory_gb"] == 16
        assert merged["memory_gb"] >= 32  # Should keep higher value
    
    def test_negotiate_timing(self, negotiation_system):
        """Test timing negotiation"""
        
        buyer_timing = {
            "start_time": datetime.utcnow() + timedelta(hours=2),
            "end_time": datetime.utcnow() + timedelta(hours=14),
            "duration_hours": 12
        }
        
        seller_timing = {
            "start_time": datetime.utcnow() + timedelta(hours=3),
            "end_time": datetime.utcnow() + timedelta(hours=15),
            "duration_hours": 10
        }
        
        negotiated = negotiation_system.negotiate_timing(buyer_timing, seller_timing)
        
        # Should use later start time
        assert negotiated["start_time"] == seller_timing["start_time"]
        
        # Should use shorter duration
        assert negotiated["duration_hours"] == seller_timing["duration_hours"]
    
    def test_calculate_concession(self, negotiation_system):
        """Test concession calculation"""
        
        current_offer = {"price": 0.15, "specifications": {"cpu_cores": 8}}
        previous_offer = {"price": 0.18, "specifications": {"cpu_cores": 8}}
        
        # Test balanced strategy
        concession = negotiation_system.calculate_concession(
            current_offer, previous_offer, "balanced", 1
        )
        
        # Should move price towards buyer preference
        assert concession["price"] < current_offer["price"]
        assert concession["specifications"] == current_offer["specifications"]
    
    def test_evaluate_offer(self, negotiation_system):
        """Test offer evaluation"""
        
        requirements = {
            "budget_range": {"min": 0.1, "max": 0.2},
            "specifications": {"cpu_cores": 8, "memory_gb": 32}
        }
        
        # Test acceptable offer
        acceptable_offer = {
            "price": 0.15,
            "specifications": {"cpu_cores": 8, "memory_gb": 32}
        }
        
        result = negotiation_system.evaluate_offer(acceptable_offer, requirements, "balanced")
        assert result["should_accept"] is True
        
        # Test unacceptable offer (too expensive)
        expensive_offer = {
            "price": 0.25,
            "specifications": {"cpu_cores": 8, "memory_gb": 32}
        }
        
        result_expensive = negotiation_system.evaluate_offer(expensive_offer, requirements, "balanced")
        assert result_expensive["should_accept"] is False
        assert result_expensive["reason"] == "price_above_maximum"


class TestSettlementLayer:
    """Test settlement layer functionality"""
    
    @pytest.fixture
    def settlement_layer(self):
        return SettlementLayer()
    
    @pytest.fixture
    def sample_agreement(self):
        return TradeAgreement(
            agreement_id="agree_001",
            buyer_agent_id="buyer_001",
            seller_agent_id="seller_001",
            trade_type=TradeType.AI_POWER,
            title="AI Model Training Service",
            agreed_terms={"delivery_date": "2026-02-27"},
            total_price=0.15,
            currency="AITBC",
            service_level_agreement={"escrow_conditions": {"delivery_confirmed": True}}
        )
    
    def test_create_settlement(self, settlement_layer, sample_agreement):
        """Test settlement creation"""
        
        # Test escrow settlement
        settlement = settlement_layer.create_settlement(sample_agreement, SettlementType.ESCROW)
        
        # Verify settlement structure
        assert "settlement_id" in settlement
        assert "agreement_id" in settlement
        assert "settlement_type" in settlement
        assert "total_amount" in settlement
        assert "requires_escrow" in settlement
        assert "platform_fee" in settlement
        assert "net_amount_seller" in settlement
        
        # Verify escrow configuration
        assert settlement["requires_escrow"] is True
        assert "escrow_config" in settlement
        assert "escrow_address" in settlement["escrow_config"]
        
        # Verify fee calculation
        expected_fee = sample_agreement.total_price * 0.02  # 2% for escrow
        assert settlement["platform_fee"] == expected_fee
        assert settlement["net_amount_seller"] == sample_agreement.total_price - expected_fee
    
    def test_process_payment(self, settlement_layer, sample_agreement):
        """Test payment processing"""
        
        settlement = settlement_layer.create_settlement(sample_agreement, SettlementType.IMMEDIATE)
        
        payment_result = settlement_layer.process_payment(settlement, "blockchain")
        
        # Verify payment result
        assert "transaction_id" in payment_result
        assert "transaction_hash" in payment_result
        assert "status" in payment_result
        assert "amount" in payment_result
        assert "fee" in payment_result
        assert "net_amount" in payment_result
        
        # Verify transaction details
        assert payment_result["status"] == "processing"
        assert payment_result["amount"] == settlement["total_amount"]
        assert payment_result["fee"] == settlement["platform_fee"]
    
    def test_release_escrow(self, settlement_layer, sample_agreement):
        """Test escrow release"""
        
        settlement = settlement_layer.create_settlement(sample_agreement, SettlementType.ESCROW)
        
        # Test successful release
        release_result = settlement_layer.release_escrow(
            settlement, "delivery_confirmed", release_conditions_met=True
        )
        
        # Verify release result
        assert release_result["conditions_met"] is True
        assert release_result["status"] == "released"
        assert "transaction_id" in release_result
        assert "amount_released" in release_result
        
        # Test failed release
        release_failed = settlement_layer.release_escrow(
            settlement, "delivery_not_confirmed", release_conditions_met=False
        )
        
        assert release_failed["conditions_met"] is False
        assert release_failed["status"] == "held"
        assert "hold_reason" in release_failed
    
    def test_handle_dispute(self, settlement_layer, sample_agreement):
        """Test dispute handling"""
        
        settlement = settlement_layer.create_settlement(sample_agreement, SettlementType.ESCROW)
        
        dispute_details = {
            "type": "quality_issue",
            "reason": "Service quality not as expected",
            "initiated_by": "buyer_001"
        }
        
        dispute_result = settlement_layer.handle_dispute(settlement, dispute_details)
        
        # Verify dispute result
        assert "dispute_id" in dispute_result
        assert "dispute_type" in dispute_result
        assert "dispute_reason" in dispute_result
        assert "initiated_by" in dispute_result
        assert "status" in dispute_result
        
        # Verify escrow hold
        assert dispute_result["escrow_status"] == "held_pending_resolution"
        assert dispute_result["escrow_release_blocked"] is True


class TestP2PTradingProtocol:
    """Test P2P trading protocol functionality"""
    
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
    def trading_protocol(self, mock_session):
        return P2PTradingProtocol(mock_session)
    
    def test_create_trade_request(self, trading_protocol, mock_session):
        """Test creating a trade request"""
        
        agent_id = "buyer_001"
        trade_type = TradeType.AI_POWER
        title = "AI Model Training Service"
        description = "Need GPU resources for model training"
        requirements = {
            "specifications": {"cpu_cores": 8, "memory_gb": 32, "gpu_count": 2},
            "timing": {"duration_hours": 12}
        }
        budget_range = {"min": 0.1, "max": 0.2}
        
        # Create trade request
        trade_request = asyncio.run(
            trading_protocol.create_trade_request(
                buyer_agent_id=agent_id,
                trade_type=trade_type,
                title=title,
                description=description,
                requirements=requirements,
                budget_range=budget_range
            )
        )
        
        # Verify request creation
        assert trade_request.buyer_agent_id == agent_id
        assert trade_request.trade_type == trade_type
        assert trade_request.title == title
        assert trade_request.description == description
        assert trade_request.requirements == requirements
        assert trade_request.budget_range == budget_range
        assert trade_request.status == TradeStatus.OPEN
        assert mock_session.committed
    
    def test_find_matches(self, trading_protocol, mock_session):
        """Test finding matches for a trade request"""
        
        # Mock session to return trade request
        mock_request = TradeRequest(
            request_id="req_001",
            buyer_agent_id="buyer_001",
            trade_type=TradeType.AI_POWER,
            requirements={"specifications": {"cpu_cores": 8}},
            budget_range={"min": 0.1, "max": 0.2}
        )
        
        mock_session.exec = lambda query: [mock_request] if hasattr(query, 'where') else []
        mock_session.add = lambda obj: None
        mock_session.commit = lambda: None
        
        # Mock available sellers
        async def mock_get_sellers(request):
            return [
                {
                    "agent_id": "seller_001",
                    "price": 0.15,
                    "specifications": {"cpu_cores": 8, "memory_gb": 32},
                    "timing": {"start_time": datetime.utcnow(), "duration_hours": 12},
                    "regions": ["us-east"],
                    "service_level": "premium"
                }
            ]
        
        async def mock_get_reputations(seller_ids):
            return {"seller_001": 750.0}
        
        trading_protocol.get_available_sellers = mock_get_sellers
        trading_protocol.get_seller_reputations = mock_get_reputations
        
        # Find matches
        matches = asyncio.run(trading_protocol.find_matches("req_001"))
        
        # Verify matches
        assert isinstance(matches, list)
        assert len(matches) > 0
        assert "seller_001" in matches
    
    def test_initiate_negotiation(self, trading_protocol, mock_session):
        """Test initiating negotiation"""
        
        # Mock trade match and request
        mock_match = TradeMatch(
            match_id="match_001",
            request_id="req_001",
            buyer_agent_id="buyer_001",
            seller_agent_id="seller_001",
            seller_offer={"price": 0.15, "specifications": {"cpu_cores": 8}}
        )
        
        mock_request = TradeRequest(
            request_id="req_001",
            buyer_agent_id="buyer_001",
            requirements={"specifications": {"cpu_cores": 8}},
            budget_range={"min": 0.1, "max": 0.2}
        )
        
        mock_session.exec = lambda query: [mock_match] if "match_id" in str(query) else [mock_request]
        mock_session.add = lambda obj: None
        mock_session.commit = lambda: None
        
        # Initiate negotiation
        negotiation = asyncio.run(
            trading_protocol.initiate_negotiation("match_001", "buyer", "balanced")
        )
        
        # Verify negotiation creation
        assert negotiation.match_id == "match_001"
        assert negotiation.buyer_agent_id == "buyer_001"
        assert negotiation.seller_agent_id == "seller_001"
        assert negotiation.status == NegotiationStatus.PENDING
        assert negotiation.negotiation_strategy == "balanced"
        assert "current_terms" in negotiation
        assert "initial_terms" in negotiation
    
    def test_get_trading_summary(self, trading_protocol, mock_session):
        """Test getting trading summary"""
        
        # Mock session to return empty lists
        mock_session.exec = lambda query: []
        
        # Get summary
        summary = asyncio.run(trading_protocol.get_trading_summary("agent_001"))
        
        # Verify summary structure
        assert "agent_id" in summary
        assert "trade_requests" in summary
        assert "trade_matches" in summary
        assert "negotiations" in summary
        assert "agreements" in summary
        assert "success_rate" in summary
        assert "total_trade_volume" in summary
        assert "recent_activity" in summary
        
        # Verify values for empty data
        assert summary["agent_id"] == "agent_001"
        assert summary["trade_requests"] == 0
        assert summary["trade_matches"] == 0
        assert summary["negotiations"] == 0
        assert summary["agreements"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["total_trade_volume"] == 0.0


# Performance Tests
class TestTradingPerformance:
    """Performance tests for trading system"""
    
    @pytest.mark.asyncio
    async def test_bulk_matching_performance(self):
        """Test performance of bulk matching operations"""
        
        # Test matching performance with many requests and sellers
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.asyncio
    async def test_negotiation_performance(self):
        """Test negotiation system performance"""
        
        # Test negotiation performance with multiple concurrent negotiations
        # Should complete within acceptable time limits
        
        pass


# Utility Functions
def create_test_trade_request(**kwargs) -> Dict[str, Any]:
    """Create test trade request data"""
    
    defaults = {
        "buyer_agent_id": "test_buyer_001",
        "trade_type": TradeType.AI_POWER,
        "title": "Test AI Service",
        "description": "Test description",
        "requirements": {
            "specifications": {"cpu_cores": 4, "memory_gb": 16},
            "timing": {"duration_hours": 8}
        },
        "budget_range": {"min": 0.05, "max": 0.1},
        "urgency_level": "normal",
        "preferred_regions": ["us-east"],
        "service_level_required": "standard"
    }
    
    defaults.update(kwargs)
    return defaults


def create_test_seller_offer(**kwargs) -> Dict[str, Any]:
    """Create test seller offer data"""
    
    defaults = {
        "agent_id": "test_seller_001",
        "price": 0.075,
        "specifications": {"cpu_cores": 4, "memory_gb": 16, "gpu_count": 1},
        "timing": {"start_time": datetime.utcnow(), "duration_hours": 8},
        "regions": ["us-east"],
        "service_level": "standard",
        "terms": {"settlement_type": "escrow"}
    }
    
    defaults.update(kwargs)
    return defaults


# Test Configuration
@pytest.fixture(scope="session")
def test_config():
    """Test configuration for trading system tests"""
    
    return {
        "test_agent_count": 100,
        "test_request_count": 500,
        "test_match_count": 1000,
        "performance_threshold_ms": 2000,
        "memory_threshold_mb": 150
    }


# Test Markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.slow = pytest.mark.slow
