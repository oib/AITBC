#!/usr/bin/env python3
"""
Agent Economics Enhancement Tests
Phase 8.3: OpenClaw Agent Economics Enhancement (Weeks 5-6)
"""

import pytest
import asyncio
import time
import json
import requests
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentType(Enum):
    """Agent types in the marketplace"""
    COMPUTE_PROVIDER = "compute_provider"
    COMPUTE_CONSUMER = "compute_consumer"
    POWER_TRADER = "power_trader"
    MARKET_MAKER = "market_maker"
    ARBITRAGE_AGENT = "arbitrage_agent"

class ReputationLevel(Enum):
    """Reputation levels for agents"""
    BRONZE = 0.0
    SILVER = 0.6
    GOLD = 0.8
    PLATINUM = 0.9
    DIAMOND = 0.95

@dataclass
class AgentEconomics:
    """Agent economics data"""
    agent_id: str
    agent_type: AgentType
    aitbc_balance: float
    total_earned: float
    total_spent: float
    reputation_score: float
    reputation_level: ReputationLevel
    successful_transactions: int
    failed_transactions: int
    total_transactions: int
    average_rating: float
    certifications: List[str] = field(default_factory=list)
    partnerships: List[str] = field(default_factory=list)
    
@dataclass
class Transaction:
    """Transaction record"""
    transaction_id: str
    from_agent: str
    to_agent: str
    amount: float
    transaction_type: str
    timestamp: datetime
    status: str
    reputation_impact: float
    
@dataclass
class RewardMechanism:
    """Reward mechanism configuration"""
    mechanism_id: str
    mechanism_type: str
    performance_threshold: float
    reward_rate: float
    bonus_conditions: Dict[str, Any]
    
@dataclass
class TradingProtocol:
    """Agent-to-agent trading protocol"""
    protocol_id: str
    protocol_type: str
    participants: List[str]
    terms: Dict[str, Any]
    settlement_conditions: List[str]

class AgentEconomicsTests:
    """Test suite for agent economics enhancement"""
    
    def __init__(self, marketplace_url: str = "http://127.0.0.1:18000"):
        self.marketplace_url = marketplace_url
        self.agents = self._setup_agents()
        self.transactions = []
        self.reward_mechanisms = self._setup_reward_mechanisms()
        self.trading_protocols = self._setup_trading_protocols()
        self.session = requests.Session()
        self.session.timeout = 30
        
    def _setup_agents(self) -> List[AgentEconomics]:
        """Setup test agents with economics data"""
        agents = []
        
        # High-reputation provider
        agents.append(AgentEconomics(
            agent_id="provider_diamond_001",
            agent_type=AgentType.COMPUTE_PROVIDER,
            aitbc_balance=2500.0,
            total_earned=15000.0,
            total_spent=2000.0,
            reputation_score=0.97,
            reputation_level=ReputationLevel.DIAMOND,
            successful_transactions=145,
            failed_transactions=3,
            total_transactions=148,
            average_rating=4.9,
            certifications=["gpu_expert", "ml_specialist", "reliable_provider"],
            partnerships=["enterprise_client_a", "research_lab_b"]
        ))
        
        # Medium-reputation provider
        agents.append(AgentEconomics(
            agent_id="provider_gold_001",
            agent_type=AgentType.COMPUTE_PROVIDER,
            aitbc_balance=800.0,
            total_earned=3500.0,
            total_spent=1200.0,
            reputation_score=0.85,
            reputation_level=ReputationLevel.GOLD,
            successful_transactions=67,
            failed_transactions=8,
            total_transactions=75,
            average_rating=4.3,
            certifications=["gpu_provider"],
            partnerships=["startup_c"]
        ))
        
        # Consumer agent
        agents.append(AgentEconomics(
            agent_id="consumer_silver_001",
            agent_type=AgentType.COMPUTE_CONSUMER,
            aitbc_balance=300.0,
            total_earned=0.0,
            total_spent=1800.0,
            reputation_score=0.72,
            reputation_level=ReputationLevel.SILVER,
            successful_transactions=23,
            failed_transactions=2,
            total_transactions=25,
            average_rating=4.1,
            certifications=["verified_consumer"],
            partnerships=[]
        ))
        
        # Power trader
        agents.append(AgentEconomics(
            agent_id="trader_platinum_001",
            agent_type=AgentType.POWER_TRADER,
            aitbc_balance=1200.0,
            total_earned=8500.0,
            total_spent=6000.0,
            reputation_score=0.92,
            reputation_level=ReputationLevel.PLATINUM,
            successful_transactions=89,
            failed_transactions=5,
            total_transactions=94,
            average_rating=4.7,
            certifications=["certified_trader", "market_analyst"],
            partnerships=["exchange_a", "liquidity_provider_b"]
        ))
        
        # Arbitrage agent
        agents.append(AgentEconomics(
            agent_id="arbitrage_gold_001",
            agent_type=AgentType.ARBITRAGE_AGENT,
            aitbc_balance=600.0,
            total_earned=4200.0,
            total_spent=2800.0,
            reputation_score=0.88,
            reputation_level=ReputationLevel.GOLD,
            successful_transactions=56,
            failed_transactions=4,
            total_transactions=60,
            average_rating=4.5,
            certifications=["arbitrage_specialist"],
            partnerships=["market_maker_c"]
        ))
        
        return agents
        
    def _setup_reward_mechanisms(self) -> List[RewardMechanism]:
        """Setup reward mechanisms for testing"""
        return [
            RewardMechanism(
                mechanism_id="performance_bonus_001",
                mechanism_type="performance_based",
                performance_threshold=0.90,
                reward_rate=0.10,  # 10% bonus
                bonus_conditions={
                    "min_transactions": 10,
                    "avg_rating_min": 4.5,
                    "uptime_min": 0.95
                }
            ),
            RewardMechanism(
                mechanism_id="volume_discount_001",
                mechanism_type="volume_based",
                performance_threshold=1000.0,  # 1000 AITBC volume
                reward_rate=0.05,  # 5% discount
                bonus_conditions={
                    "monthly_volume_min": 1000.0,
                    "consistent_trading": True
                }
            ),
            RewardMechanism(
                mechanism_id="referral_program_001",
                mechanism_type="referral_based",
                performance_threshold=0.80,
                reward_rate=0.15,  # 15% referral bonus
                bonus_conditions={
                    "referrals_min": 3,
                    "referral_performance_min": 0.85
                }
            )
        ]
        
    def _setup_trading_protocols(self) -> List[TradingProtocol]:
        """Setup agent-to-agent trading protocols"""
        return [
            TradingProtocol(
                protocol_id="direct_p2p_001",
                protocol_type="direct_peer_to_peer",
                participants=["provider_diamond_001", "consumer_silver_001"],
                terms={
                    "price_per_hour": 3.5,
                    "min_duration_hours": 2,
                    "payment_terms": "prepaid",
                    "performance_sla": 0.95
                },
                settlement_conditions=["performance_met", "payment_confirmed"]
            ),
            TradingProtocol(
                protocol_id="arbitrage_opportunity_001",
                protocol_type="arbitrage",
                participants=["arbitrage_gold_001", "trader_platinum_001"],
                terms={
                    "price_difference_threshold": 0.5,
                    "max_trade_size": 100.0,
                    "settlement_time": "immediate"
                },
                settlement_conditions=["profit_made", "risk_managed"]
            )
        ]
        
    def _get_agent_by_id(self, agent_id: str) -> Optional[AgentEconomics]:
        """Get agent by ID"""
        return next((agent for agent in self.agents if agent.agent_id == agent_id), None)
        
    async def test_agent_reputation_system(self, agent_id: str) -> Dict[str, Any]:
        """Test agent reputation system"""
        try:
            agent = self._get_agent_by_id(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} not found"}
                
            # Test reputation calculation
            reputation_payload = {
                "agent_id": agent_id,
                "transaction_history": {
                    "successful": agent.successful_transactions,
                    "failed": agent.failed_transactions,
                    "total": agent.total_transactions
                },
                "performance_metrics": {
                    "average_rating": agent.average_rating,
                    "uptime": 0.97,
                    "response_time_avg": 0.08
                },
                "certifications": agent.certifications,
                "partnerships": agent.partnerships
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/agents/reputation/calculate",
                json=reputation_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "agent_id": agent_id,
                    "current_reputation": agent.reputation_score,
                    "calculated_reputation": result.get("reputation_score"),
                    "reputation_level": result.get("reputation_level"),
                    "reputation_factors": result.get("factors"),
                    "accuracy": abs(agent.reputation_score - result.get("reputation_score", 0)) < 0.05,
                    "success": True
                }
            else:
                return {
                    "agent_id": agent_id,
                    "error": f"Reputation calculation failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "agent_id": agent_id,
                "error": str(e),
                "success": False
            }
            
    async def test_performance_based_rewards(self, agent_id: str, performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Test performance-based reward mechanisms"""
        try:
            agent = self._get_agent_by_id(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} not found"}
                
            # Test performance reward calculation
            reward_payload = {
                "agent_id": agent_id,
                "performance_metrics": performance_metrics,
                "reward_mechanism": "performance_bonus_001",
                "calculation_period": "monthly"
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/rewards/calculate",
                json=reward_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "agent_id": agent_id,
                    "performance_metrics": performance_metrics,
                    "reward_amount": result.get("reward_amount"),
                    "reward_rate": result.get("reward_rate"),
                    "bonus_conditions_met": result.get("bonus_conditions_met"),
                    "reward_breakdown": result.get("breakdown"),
                    "success": True
                }
            else:
                return {
                    "agent_id": agent_id,
                    "error": f"Reward calculation failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "agent_id": agent_id,
                "error": str(e),
                "success": False
            }
            
    async def test_agent_to_agent_trading(self, protocol_id: str) -> Dict[str, Any]:
        """Test agent-to-agent AI power trading protocols"""
        try:
            protocol = next((p for p in self.trading_protocols if p.protocol_id == protocol_id), None)
            if not protocol:
                return {"error": f"Protocol {protocol_id} not found"}
                
            # Test trading protocol execution
            trading_payload = {
                "protocol_id": protocol_id,
                "participants": protocol.participants,
                "terms": protocol.terms,
                "execution_type": "immediate"
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/trading/execute",
                json=trading_payload,
                timeout=20
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Record transaction
                transaction = Transaction(
                    transaction_id=result.get("transaction_id"),
                    from_agent=protocol.participants[0],
                    to_agent=protocol.participants[1],
                    amount=protocol.terms.get("price_per_hour", 0) * protocol.terms.get("min_duration_hours", 1),
                    transaction_type=protocol.protocol_type,
                    timestamp=datetime.now(),
                    status="completed",
                    reputation_impact=result.get("reputation_impact", 0.01)
                )
                self.transactions.append(transaction)
                
                return {
                    "protocol_id": protocol_id,
                    "transaction_id": transaction.transaction_id,
                    "participants": protocol.participants,
                    "trading_terms": protocol.terms,
                    "execution_result": result,
                    "reputation_impact": transaction.reputation_impact,
                    "success": True
                }
            else:
                return {
                    "protocol_id": protocol_id,
                    "error": f"Trading execution failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "protocol_id": protocol_id,
                "error": str(e),
                "success": False
            }
            
    async def test_marketplace_analytics(self, time_range: str = "monthly") -> Dict[str, Any]:
        """Test marketplace analytics and economic insights"""
        try:
            analytics_payload = {
                "time_range": time_range,
                "metrics": [
                    "trading_volume",
                    "agent_participation",
                    "price_trends",
                    "reputation_distribution",
                    "earnings_analysis"
                ]
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/analytics/marketplace",
                json=analytics_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "time_range": time_range,
                    "trading_volume": result.get("trading_volume"),
                    "agent_participation": result.get("agent_participation"),
                    "price_trends": result.get("price_trends"),
                    "reputation_distribution": result.get("reputation_distribution"),
                    "earnings_analysis": result.get("earnings_analysis"),
                    "economic_insights": result.get("insights"),
                    "success": True
                }
            else:
                return {
                    "time_range": time_range,
                    "error": f"Analytics failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "time_range": time_range,
                "error": str(e),
                "success": False
            }
            
    async def test_agent_certification(self, agent_id: str, certification_type: str) -> Dict[str, Any]:
        """Test agent certification and partnership programs"""
        try:
            agent = self._get_agent_by_id(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} not found"}
                
            # Test certification process
            certification_payload = {
                "agent_id": agent_id,
                "certification_type": certification_type,
                "current_certifications": agent.certifications,
                "performance_history": {
                    "successful_transactions": agent.successful_transactions,
                    "average_rating": agent.average_rating,
                    "reputation_score": agent.reputation_score
                }
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/certifications/evaluate",
                json=certification_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "agent_id": agent_id,
                    "certification_type": certification_type,
                    "certification_granted": result.get("granted", False),
                    "certification_level": result.get("level"),
                    "valid_until": result.get("valid_until"),
                    "requirements_met": result.get("requirements_met"),
                    "benefits": result.get("benefits"),
                    "success": True
                }
            else:
                return {
                    "agent_id": agent_id,
                    "certification_type": certification_type,
                    "error": f"Certification failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "agent_id": agent_id,
                "certification_type": certification_type,
                "error": str(e),
                "success": False
            }
            
    async def test_earnings_analysis(self, agent_id: str, period: str = "monthly") -> Dict[str, Any]:
        """Test agent earnings analysis and projections"""
        try:
            agent = self._get_agent_by_id(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} not found"}
                
            # Test earnings analysis
            earnings_payload = {
                "agent_id": agent_id,
                "analysis_period": period,
                "historical_data": {
                    "total_earned": agent.total_earned,
                    "total_spent": agent.total_spent,
                    "transaction_count": agent.total_transactions,
                    "average_transaction_value": (agent.total_earned + agent.total_spent) / max(agent.total_transactions, 1)
                }
            }
            
            response = self.session.post(
                f"{self.marketplace_url}/v1/analytics/earnings",
                json=earnings_payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                
                return {
                    "agent_id": agent_id,
                    "analysis_period": period,
                    "current_earnings": agent.total_earned,
                    "earnings_trend": result.get("trend"),
                    "projected_earnings": result.get("projected"),
                    "earnings_breakdown": result.get("breakdown"),
                    "optimization_suggestions": result.get("suggestions"),
                    "success": True
                }
            else:
                return {
                    "agent_id": agent_id,
                    "analysis_period": period,
                    "error": f"Earnings analysis failed with status {response.status_code}",
                    "success": False
                }
                
        except Exception as e:
            return {
                "agent_id": agent_id,
                "analysis_period": period,
                "error": str(e),
                "success": False
            }
            
    async def test_trust_system_accuracy(self) -> Dict[str, Any]:
        """Test trust system accuracy and reliability"""
        try:
            # Test trust system across all agents
            trust_results = []
            
            for agent in self.agents:
                trust_payload = {
                    "agent_id": agent.agent_id,
                    "reputation_score": agent.reputation_score,
                    "transaction_history": {
                        "successful": agent.successful_transactions,
                        "failed": agent.failed_transactions,
                        "total": agent.total_transactions
                    },
                    "certifications": agent.certifications,
                    "partnerships": agent.partnerships
                }
                
                response = self.session.post(
                    f"{self.marketplace_url}/v1/trust/evaluate",
                    json=trust_payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    trust_results.append({
                        "agent_id": agent.agent_id,
                        "actual_reputation": agent.reputation_score,
                        "predicted_trust": result.get("trust_score"),
                        "accuracy": abs(agent.reputation_score - result.get("trust_score", 0)),
                        "confidence": result.get("confidence", 0)
                    })
                    
            if trust_results:
                avg_accuracy = statistics.mean([r["accuracy"] for r in trust_results])
                avg_confidence = statistics.mean([r["confidence"] for r in trust_results])
                
                return {
                    "total_agents_tested": len(trust_results),
                    "average_accuracy": avg_accuracy,
                    "target_accuracy": 0.95,  # 95% accuracy target
                    "meets_target": avg_accuracy <= 0.05,  # Within 5% error margin
                    "average_confidence": avg_confidence,
                    "trust_results": trust_results,
                    "success": True
                }
            else:
                return {
                    "error": "No trust results available",
                    "success": False
                }
                
        except Exception as e:
            return {"error": str(e), "success": False}

# Test Fixtures
@pytest.fixture
async def agent_economics_tests():
    """Create agent economics test instance"""
    return AgentEconomicsTests()

@pytest.fixture
def sample_performance_metrics():
    """Sample performance metrics for testing"""
    return {
        "uptime": 0.98,
        "response_time_avg": 0.07,
        "task_completion_rate": 0.96,
        "gpu_utilization_avg": 0.89,
        "customer_satisfaction": 4.8,
        "monthly_volume": 1500.0
    }

# Test Classes
class TestAgentReputationSystem:
    """Test agent reputation and trust systems"""
    
    @pytest.mark.asyncio
    async def test_reputation_calculation_accuracy(self, agent_economics_tests):
        """Test reputation calculation accuracy"""
        test_agents = ["provider_diamond_001", "provider_gold_001", "trader_platinum_001"]
        
        for agent_id in test_agents:
            result = await agent_economics_tests.test_agent_reputation_system(agent_id)
            
            assert result.get("success", False), f"Reputation calculation failed for {agent_id}"
            assert result.get("accuracy", False), f"Reputation calculation inaccurate for {agent_id}"
            assert "reputation_level" in result, f"No reputation level for {agent_id}"
            
    @pytest.mark.asyncio
    async def test_trust_system_reliability(self, agent_economics_tests):
        """Test trust system reliability across all agents"""
        result = await agent_economics_tests.test_trust_system_accuracy()
        
        assert result.get("success", False), "Trust system accuracy test failed"
        assert result.get("meets_target", False), "Trust system does not meet accuracy target"
        assert result.get("average_accuracy", 1.0) <= 0.05, "Trust system accuracy too low"
        assert result.get("average_confidence", 0) >= 0.8, "Trust system confidence too low"

class TestRewardMechanisms:
    """Test performance-based reward mechanisms"""
    
    @pytest.mark.asyncio
    async def test_performance_based_rewards(self, agent_economics_tests, sample_performance_metrics):
        """Test performance-based reward calculation"""
        test_agents = ["provider_diamond_001", "trader_platinum_001"]
        
        for agent_id in test_agents:
            result = await agent_economics_tests.test_performance_based_rewards(
                agent_id,
                sample_performance_metrics
            )
            
            assert result.get("success", False), f"Reward calculation failed for {agent_id}"
            assert "reward_amount" in result, f"No reward amount for {agent_id}"
            assert result.get("reward_amount", 0) >= 0, f"Negative reward for {agent_id}"
            assert "bonus_conditions_met" in result, f"No bonus conditions for {agent_id}"
            
    @pytest.mark.asyncio
    async def test_volume_based_rewards(self, agent_economics_tests):
        """Test volume-based reward mechanisms"""
        high_volume_metrics = {
            "monthly_volume": 2500.0,
            "consistent_trading": True,
            "transaction_count": 150
        }
        
        result = await agent_economics_tests.test_performance_based_rewards(
            "trader_platinum_001",
            high_volume_metrics
        )
        
        assert result.get("success", False), "Volume-based reward test failed"
        assert result.get("reward_amount", 0) > 0, "No volume reward calculated"

class TestAgentToAgentTrading:
    """Test agent-to-agent AI power trading protocols"""
    
    @pytest.mark.asyncio
    async def test_direct_p2p_trading(self, agent_economics_tests):
        """Test direct peer-to-peer trading protocol"""
        result = await agent_economics_tests.test_agent_to_agent_trading("direct_p2p_001")
        
        assert result.get("success", False), "Direct P2P trading failed"
        assert "transaction_id" in result, "No transaction ID generated"
        assert result.get("reputation_impact", 0) > 0, "No reputation impact calculated"
        
    @pytest.mark.asyncio
    async def test_arbitrage_trading(self, agent_economics_tests):
        """Test arbitrage trading protocol"""
        result = await agent_economics_tests.test_agent_to_agent_trading("arbitrage_opportunity_001")
        
        assert result.get("success", False), "Arbitrage trading failed"
        assert "transaction_id" in result, "No transaction ID for arbitrage"
        assert result.get("participants", []) == 2, "Incorrect number of participants"

class TestMarketplaceAnalytics:
    """Test marketplace analytics and economic insights"""
    
    @pytest.mark.asyncio
    async def test_monthly_analytics(self, agent_economics_tests):
        """Test monthly marketplace analytics"""
        result = await agent_economics_tests.test_marketplace_analytics("monthly")
        
        assert result.get("success", False), "Monthly analytics test failed"
        assert "trading_volume" in result, "No trading volume data"
        assert "agent_participation" in result, "No agent participation data"
        assert "price_trends" in result, "No price trends data"
        assert "earnings_analysis" in result, "No earnings analysis data"
        
    @pytest.mark.asyncio
    async def test_weekly_analytics(self, agent_economics_tests):
        """Test weekly marketplace analytics"""
        result = await agent_economics_tests.test_marketplace_analytics("weekly")
        
        assert result.get("success", False), "Weekly analytics test failed"
        assert "economic_insights" in result, "No economic insights provided"

class TestAgentCertification:
    """Test agent certification and partnership programs"""
    
    @pytest.mark.asyncio
    async def test_gpu_expert_certification(self, agent_economics_tests):
        """Test GPU expert certification"""
        result = await agent_economics_tests.test_agent_certification(
            "provider_diamond_001",
            "gpu_expert"
        )
        
        assert result.get("success", False), "GPU expert certification test failed"
        assert "certification_granted" in result, "No certification result"
        assert "certification_level" in result, "No certification level"
        
    @pytest.mark.asyncio
    async def test_market_analyst_certification(self, agent_economics_tests):
        """Test market analyst certification"""
        result = await agent_economics_tests.test_agent_certification(
            "trader_platinum_001",
            "market_analyst"
        )
        
        assert result.get("success", False), "Market analyst certification test failed"
        assert result.get("certification_granted", False), "Certification not granted"

class TestEarningsAnalysis:
    """Test agent earnings analysis and projections"""
    
    @pytest.mark.asyncio
    async def test_monthly_earnings_analysis(self, agent_economics_tests):
        """Test monthly earnings analysis"""
        result = await agent_economics_tests.test_earnings_analysis(
            "provider_diamond_001",
            "monthly"
        )
        
        assert result.get("success", False), "Monthly earnings analysis failed"
        assert "earnings_trend" in result, "No earnings trend provided"
        assert "projected_earnings" in result, "No earnings projection provided"
        assert "optimization_suggestions" in result, "No optimization suggestions"
        
    @pytest.mark.asyncio
    async def test_earnings_projections(self, agent_economics_tests):
        """Test earnings projections for different agent types"""
        test_agents = ["provider_diamond_001", "trader_platinum_001", "arbitrage_gold_001"]
        
        for agent_id in test_agents:
            result = await agent_economics_tests.test_earnings_analysis(agent_id, "monthly")
            
            assert result.get("success", False), f"Earnings analysis failed for {agent_id}"
            assert result.get("projected_earnings", 0) > 0, f"No positive earnings projection for {agent_id}"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
