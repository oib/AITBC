#!/usr/bin/env python3
"""
Comprehensive Test Framework for OpenClaw Agent Marketplace
Tests for Phase 8-10: Global AI Power Marketplace Expansion
"""

import pytest
import asyncio
import time
import json
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MarketplaceConfig:
    """Configuration for marketplace testing"""
    primary_marketplace: str = "http://127.0.0.1:18000"
    secondary_marketplace: str = "http://127.0.0.1:18001"
    gpu_service: str = "http://127.0.0.1:8002"
    test_timeout: int = 30
    max_retries: int = 3
    
@dataclass
class AgentInfo:
    """Agent information for testing"""
    agent_id: str
    agent_type: str
    capabilities: List[str]
    reputation_score: float
    aitbc_balance: float
    region: str
    
@dataclass
class AIResource:
    """AI resource for marketplace trading"""
    resource_id: str
    resource_type: str
    compute_power: float
    gpu_memory: int
    price_per_hour: float
    availability: bool
    provider_id: str

class OpenClawMarketplaceTestFramework:
    """Comprehensive test framework for OpenClaw Agent Marketplace"""
    
    def __init__(self, config: MarketplaceConfig):
        self.config = config
        self.agents: List[AgentInfo] = []
        self.resources: List[AIResource] = []
        self.session = requests.Session()
        self.session.timeout = config.test_timeout
        
    async def setup_test_environment(self):
        """Setup test environment with agents and resources"""
        logger.info("Setting up OpenClaw Marketplace test environment...")
        
        # Create test agents
        self.agents = [
            AgentInfo(
                agent_id="agent_provider_001",
                agent_type="compute_provider",
                capabilities=["gpu_computing", "multimodal_processing", "reinforcement_learning"],
                reputation_score=0.95,
                aitbc_balance=1000.0,
                region="us-east-1"
            ),
            AgentInfo(
                agent_id="agent_consumer_001",
                agent_type="compute_consumer",
                capabilities=["ai_inference", "model_training", "data_processing"],
                reputation_score=0.88,
                aitbc_balance=500.0,
                region="us-west-2"
            ),
            AgentInfo(
                agent_id="agent_trader_001",
                agent_type="power_trader",
                capabilities=["resource_optimization", "price_arbitrage", "market_analysis"],
                reputation_score=0.92,
                aitbc_balance=750.0,
                region="eu-central-1"
            )
        ]
        
        # Create test AI resources
        self.resources = [
            AIResource(
                resource_id="gpu_resource_001",
                resource_type="nvidia_a100",
                compute_power=312.0,
                gpu_memory=40,
                price_per_hour=2.5,
                availability=True,
                provider_id="agent_provider_001"
            ),
            AIResource(
                resource_id="gpu_resource_002",
                resource_type="nvidia_h100",
                compute_power=670.0,
                gpu_memory=80,
                price_per_hour=5.0,
                availability=True,
                provider_id="agent_provider_001"
            ),
            AIResource(
                resource_id="edge_resource_001",
                resource_type="edge_gpu",
                compute_power=50.0,
                gpu_memory=8,
                price_per_hour=0.8,
                availability=True,
                provider_id="agent_provider_001"
            )
        ]
        
        logger.info(f"Created {len(self.agents)} test agents and {len(self.resources)} test resources")
        
    async def cleanup_test_environment(self):
        """Cleanup test environment"""
        logger.info("Cleaning up test environment...")
        self.agents.clear()
        self.resources.clear()
        
    async def test_marketplace_health(self, marketplace_url: str) -> bool:
        """Test marketplace health endpoint"""
        try:
            response = self.session.get(f"{marketplace_url}/health", timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Marketplace health check failed: {e}")
            return False
            
    async def test_agent_registration(self, agent: AgentInfo, marketplace_url: str) -> bool:
        """Test agent registration"""
        try:
            payload = {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "capabilities": agent.capabilities,
                "region": agent.region,
                "initial_reputation": agent.reputation_score
            }
            
            response = self.session.post(
                f"{marketplace_url}/v1/agents/register",
                json=payload,
                timeout=10
            )
            
            return response.status_code == 201
        except Exception as e:
            logger.error(f"Agent registration failed: {e}")
            return False
            
    async def test_resource_listing(self, resource: AIResource, marketplace_url: str) -> bool:
        """Test AI resource listing"""
        try:
            payload = {
                "resource_id": resource.resource_id,
                "resource_type": resource.resource_type,
                "compute_power": resource.compute_power,
                "gpu_memory": resource.gpu_memory,
                "price_per_hour": resource.price_per_hour,
                "availability": resource.availability,
                "provider_id": resource.provider_id
            }
            
            response = self.session.post(
                f"{marketplace_url}/v1/marketplace/list",
                json=payload,
                timeout=10
            )
            
            return response.status_code == 201
        except Exception as e:
            logger.error(f"Resource listing failed: {e}")
            return False
            
    async def test_ai_power_rental(self, resource_id: str, consumer_id: str, duration_hours: int, marketplace_url: str) -> Dict[str, Any]:
        """Test AI power rental transaction"""
        try:
            payload = {
                "resource_id": resource_id,
                "consumer_id": consumer_id,
                "duration_hours": duration_hours,
                "max_price_per_hour": 10.0,
                "requirements": {
                    "min_compute_power": 50.0,
                    "min_gpu_memory": 8,
                    "gpu_required": True
                }
            }
            
            response = self.session.post(
                f"{marketplace_url}/v1/marketplace/rent",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 201:
                return response.json()
            else:
                return {"error": f"Rental failed with status {response.status_code}"}
                
        except Exception as e:
            logger.error(f"AI power rental failed: {e}")
            return {"error": str(e)}
            
    async def test_smart_contract_execution(self, contract_type: str, params: Dict[str, Any], marketplace_url: str) -> Dict[str, Any]:
        """Test smart contract execution"""
        try:
            payload = {
                "contract_type": contract_type,
                "parameters": params,
                "gas_limit": 1000000,
                "value": params.get("value", 0)
            }
            
            response = self.session.post(
                f"{marketplace_url}/v1/blockchain/contracts/execute",
                json=payload,
                timeout=20
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Contract execution failed with status {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Smart contract execution failed: {e}")
            return {"error": str(e)}
            
    async def test_performance_metrics(self, marketplace_url: str) -> Dict[str, Any]:
        """Test marketplace performance metrics"""
        try:
            response = self.session.get(f"{marketplace_url}/v1/metrics/performance", timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Performance metrics failed with status {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Performance metrics failed: {e}")
            return {"error": str(e)}
            
    async def test_geographic_load_balancing(self, consumer_region: str, marketplace_urls: List[str]) -> Dict[str, Any]:
        """Test geographic load balancing"""
        results = {}
        
        for url in marketplace_urls:
            try:
                start_time = time.time()
                response = self.session.get(f"{url}/v1/marketplace/nearest", timeout=10)
                end_time = time.time()
                
                results[url] = {
                    "response_time": (end_time - start_time) * 1000,  # Convert to ms
                    "status_code": response.status_code,
                    "success": response.status_code == 200
                }
            except Exception as e:
                results[url] = {
                    "error": str(e),
                    "success": False
                }
                
        return results
        
    async def test_agent_reputation_system(self, agent_id: str, marketplace_url: str) -> Dict[str, Any]:
        """Test agent reputation system"""
        try:
            response = self.session.get(f"{marketplace_url}/v1/agents/{agent_id}/reputation", timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Reputation check failed with status {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Agent reputation check failed: {e}")
            return {"error": str(e)}
            
    async def test_payment_processing(self, from_agent: str, to_agent: str, amount: float, marketplace_url: str) -> Dict[str, Any]:
        """Test AITBC payment processing"""
        try:
            payload = {
                "from_agent": from_agent,
                "to_agent": to_agent,
                "amount": amount,
                "currency": "AITBC",
                "payment_type": "ai_power_rental"
            }
            
            response = self.session.post(
                f"{marketplace_url}/v1/payments/process",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Payment processing failed with status {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Payment processing failed: {e}")
            return {"error": str(e)}

# Test Fixtures
@pytest.fixture
async def marketplace_framework():
    """Create marketplace test framework"""
    config = MarketplaceConfig()
    framework = OpenClawMarketplaceTestFramework(config)
    await framework.setup_test_environment()
    yield framework
    await framework.cleanup_test_environment()

@pytest.fixture
def sample_agent():
    """Sample agent for testing"""
    return AgentInfo(
        agent_id="test_agent_001",
        agent_type="compute_provider",
        capabilities=["gpu_computing", "ai_inference"],
        reputation_score=0.90,
        aitbc_balance=100.0,
        region="us-east-1"
    )

@pytest.fixture
def sample_resource():
    """Sample AI resource for testing"""
    return AIResource(
        resource_id="test_resource_001",
        resource_type="nvidia_a100",
        compute_power=312.0,
        gpu_memory=40,
        price_per_hour=2.5,
        availability=True,
        provider_id="test_provider_001"
    )

# Test Classes
class TestMarketplaceHealth:
    """Test marketplace health and connectivity"""
    
    @pytest.mark.asyncio
    async def test_primary_marketplace_health(self, marketplace_framework):
        """Test primary marketplace health"""
        result = await marketplace_framework.test_marketplace_health(marketplace_framework.config.primary_marketplace)
        assert result is True, "Primary marketplace should be healthy"
        
    @pytest.mark.asyncio
    async def test_secondary_marketplace_health(self, marketplace_framework):
        """Test secondary marketplace health"""
        result = await marketplace_framework.test_marketplace_health(marketplace_framework.config.secondary_marketplace)
        assert result is True, "Secondary marketplace should be healthy"

class TestAgentRegistration:
    """Test agent registration and management"""
    
    @pytest.mark.asyncio
    async def test_agent_registration_success(self, marketplace_framework, sample_agent):
        """Test successful agent registration"""
        result = await marketplace_framework.test_agent_registration(
            sample_agent, 
            marketplace_framework.config.primary_marketplace
        )
        assert result is True, "Agent registration should succeed"
        
    @pytest.mark.asyncio
    async def test_agent_reputation_tracking(self, marketplace_framework, sample_agent):
        """Test agent reputation tracking"""
        # First register the agent
        await marketplace_framework.test_agent_registration(
            sample_agent, 
            marketplace_framework.config.primary_marketplace
        )
        
        # Then check reputation
        reputation = await marketplace_framework.test_agent_reputation_system(
            sample_agent.agent_id,
            marketplace_framework.config.primary_marketplace
        )
        
        assert "reputation_score" in reputation, "Reputation score should be tracked"
        assert reputation["reputation_score"] >= 0.0, "Reputation score should be valid"

class TestResourceTrading:
    """Test AI resource trading and marketplace operations"""
    
    @pytest.mark.asyncio
    async def test_resource_listing_success(self, marketplace_framework, sample_resource):
        """Test successful resource listing"""
        result = await marketplace_framework.test_resource_listing(
            sample_resource,
            marketplace_framework.config.primary_marketplace
        )
        assert result is True, "Resource listing should succeed"
        
    @pytest.mark.asyncio
    async def test_ai_power_rental_success(self, marketplace_framework, sample_resource):
        """Test successful AI power rental"""
        # First list the resource
        await marketplace_framework.test_resource_listing(
            sample_resource,
            marketplace_framework.config.primary_marketplace
        )
        
        # Then rent the resource
        rental_result = await marketplace_framework.test_ai_power_rental(
            sample_resource.resource_id,
            "test_consumer_001",
            2,  # 2 hours
            marketplace_framework.config.primary_marketplace
        )
        
        assert "rental_id" in rental_result, "Rental should create a rental ID"
        assert rental_result.get("status") == "confirmed", "Rental should be confirmed"

class TestSmartContracts:
    """Test blockchain smart contract integration"""
    
    @pytest.mark.asyncio
    async def test_ai_power_rental_contract(self, marketplace_framework):
        """Test AI power rental smart contract"""
        params = {
            "resource_id": "test_resource_001",
            "consumer_id": "test_consumer_001",
            "provider_id": "test_provider_001",
            "duration_hours": 2,
            "price_per_hour": 2.5,
            "value": 5.0  # Total payment in AITBC
        }
        
        result = await marketplace_framework.test_smart_contract_execution(
            "ai_power_rental",
            params,
            marketplace_framework.config.primary_marketplace
        )
        
        assert "transaction_hash" in result, "Contract execution should return transaction hash"
        assert result.get("status") == "success", "Contract execution should succeed"
        
    @pytest.mark.asyncio
    async def test_payment_processing_contract(self, marketplace_framework):
        """Test payment processing smart contract"""
        params = {
            "from_agent": "test_consumer_001",
            "to_agent": "test_provider_001",
            "amount": 5.0,
            "payment_type": "ai_power_rental",
            "value": 5.0
        }
        
        result = await marketplace_framework.test_smart_contract_execution(
            "payment_processing",
            params,
            marketplace_framework.config.primary_marketplace
        )
        
        assert "transaction_hash" in result, "Payment contract should return transaction hash"
        assert result.get("status") == "success", "Payment contract should succeed"

class TestPerformanceOptimization:
    """Test marketplace performance and optimization"""
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self, marketplace_framework):
        """Test performance metrics collection"""
        metrics = await marketplace_framework.test_performance_metrics(
            marketplace_framework.config.primary_marketplace
        )
        
        assert "response_time" in metrics, "Response time should be tracked"
        assert "throughput" in metrics, "Throughput should be tracked"
        assert "gpu_utilization" in metrics, "GPU utilization should be tracked"
        
    @pytest.mark.asyncio
    async def test_geographic_load_balancing(self, marketplace_framework):
        """Test geographic load balancing"""
        marketplace_urls = [
            marketplace_framework.config.primary_marketplace,
            marketplace_framework.config.secondary_marketplace
        ]
        
        results = await marketplace_framework.test_geographic_load_balancing(
            "us-east-1",
            marketplace_urls
        )
        
        for url, result in results.items():
            assert result.get("success", False), f"Load balancing should work for {url}"
            assert result.get("response_time", 1000) < 1000, f"Response time should be < 1000ms for {url}"

class TestAgentEconomics:
    """Test agent economics and payment systems"""
    
    @pytest.mark.asyncio
    async def test_aitbc_payment_processing(self, marketplace_framework):
        """Test AITBC payment processing"""
        result = await marketplace_framework.test_payment_processing(
            "test_consumer_001",
            "test_provider_001",
            5.0,
            marketplace_framework.config.primary_marketplace
        )
        
        assert "payment_id" in result, "Payment should create a payment ID"
        assert result.get("status") == "completed", "Payment should be completed"
        
    @pytest.mark.asyncio
    async def test_agent_balance_tracking(self, marketplace_framework, sample_agent):
        """Test agent balance tracking"""
        # Register agent first
        await marketplace_framework.test_agent_registration(
            sample_agent,
            marketplace_framework.config.primary_marketplace
        )
        
        # Check balance
        response = marketplace_framework.session.get(
            f"{marketplace_framework.config.primary_marketplace}/v1/agents/{sample_agent.agent_id}/balance"
        )
        
        if response.status_code == 200:
            balance_data = response.json()
            assert "aitbc_balance" in balance_data, "AITBC balance should be tracked"
            assert balance_data["aitbc_balance"] >= 0.0, "Balance should be non-negative"

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
