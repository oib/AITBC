"""
Agent Discovery Tests
Tests for agent registration, discovery, capability matching, and agent registry
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
import asyncio
from datetime import UTC, datetime, timedelta

from app.routing.agent_discovery import (
    AgentInfo,
    AgentRegistry,
    AgentDiscoveryService,
    AgentStatus,
    AgentType,
    create_agent_info,
)


class TestAgentInfo:
    """Test agent information structure"""

    def test_agent_info_creation(self):
        """Test creating agent information"""
        agent_info = AgentInfo(
            agent_id="agent_001",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080"},
            metadata={"region": "us-east"},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.95
        )
        
        assert agent_info.agent_id == "agent_001"
        assert agent_info.agent_type == AgentType.WORKER
        assert agent_info.status == AgentStatus.ACTIVE
        assert len(agent_info.capabilities) == 2
        assert agent_info.health_score == 0.95

    def test_agent_info_serialization(self):
        """Test agent info to_dict and from_dict"""
        agent_info = AgentInfo(
            agent_id="agent_002",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8081"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        # Convert to dict
        agent_dict = agent_info.to_dict()
        assert "agent_id" in agent_dict
        assert "agent_type" in agent_dict
        assert "capabilities" in agent_dict
        assert "health_score" in agent_dict
        
        # Convert from dict
        restored_info = AgentInfo.from_dict(agent_dict)
        assert restored_info.agent_id == agent_info.agent_id
        assert restored_info.agent_type == agent_info.agent_type
        assert restored_info.status == agent_info.status

    def test_create_agent_info_factory(self):
        """Test factory function for creating agent info"""
        agent_info = create_agent_info(
            agent_id="agent_003",
            agent_type="worker",
            capabilities=["compute"],
            services=["processing"],
            endpoints={"http": "http://localhost:8082"}
        )
        
        assert agent_info.agent_id == "agent_003"
        assert agent_info.agent_type == AgentType.WORKER
        assert agent_info.status == AgentStatus.ACTIVE
        assert len(agent_info.capabilities) == 1


class TestAgentRegistry:
    """Test agent registry functionality"""

    @pytest.mark.asyncio
    async def test_registry_initialization(self):
        """Test registry initialization"""
        registry = AgentRegistry()
        
        assert len(registry.agents) == 0
        assert len(registry.service_index) == 0
        assert len(registry.capability_index) == 0
        assert registry.heartbeat_interval == 30

    @pytest.mark.asyncio
    async def test_register_agent(self):
        """Test registering an agent"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_004",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8083"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        success = await registry.register_agent(agent_info)
        
        assert success is True
        assert "agent_004" in registry.agents
        assert len(registry.service_index) == 1
        assert len(registry.capability_index) == 1

    @pytest.mark.asyncio
    async def test_unregister_agent(self):
        """Test unregistering an agent"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_005",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["cpu"],
            services=["compute"],
            endpoints={"http": "http://localhost:8084"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        success = await registry.unregister_agent("agent_005")
        
        assert success is True
        assert "agent_005" not in registry.agents

    @pytest.mark.asyncio
    async def test_update_agent_status(self):
        """Test updating agent status"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_006",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8085"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        success = await registry.update_agent_status("agent_006", AgentStatus.BUSY, {"cpu": 0.8})
        
        assert success is True
        assert registry.agents["agent_006"].status == AgentStatus.BUSY
        assert registry.agents["agent_006"].load_metrics["cpu"] == 0.8

    @pytest.mark.asyncio
    async def test_update_agent_heartbeat(self):
        """Test updating agent heartbeat"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_007",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["cpu"],
            services=["compute"],
            endpoints={"http": "http://localhost:8086"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        old_heartbeat = registry.agents["agent_007"].last_heartbeat
        
        # Wait a bit and update heartbeat
        await asyncio.sleep(0.01)
        success = await registry.update_agent_heartbeat("agent_007")
        
        assert success is True
        assert registry.agents["agent_007"].last_heartbeat > old_heartbeat

    @pytest.mark.asyncio
    async def test_discover_agents_by_type(self):
        """Test discovering agents by type"""
        registry = AgentRegistry()
        
        # Register multiple agents
        for i in range(3):
            agent_info = AgentInfo(
                agent_id=f"agent_00{i}",
                agent_type=AgentType.WORKER if i < 2 else AgentType.SPECIALIST,
                status=AgentStatus.ACTIVE,
                capabilities=["gpu"],
                services=["inference"],
                endpoints={"http": f"http://localhost:808{i}"},
                metadata={},
                last_heartbeat=datetime.now(UTC),
                registration_time=datetime.now(UTC)
            )
            await registry.register_agent(agent_info)
        
        # Discover by type
        workers = await registry.discover_agents({"agent_type": "worker"})
        
        assert len(workers) == 2
        assert all(agent.agent_type == AgentType.WORKER for agent in workers)

    @pytest.mark.asyncio
    async def test_discover_agents_by_capability(self):
        """Test discovering agents by capability"""
        registry = AgentRegistry()
        
        # Register agents with different capabilities
        gpu_agent = AgentInfo(
            agent_id="agent_gpu",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["inference"],
            endpoints={"http": "http://localhost:8090"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        cpu_agent = AgentInfo(
            agent_id="agent_cpu",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["cpu"],
            services=["compute"],
            endpoints={"http": "http://localhost:8091"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(gpu_agent)
        await registry.register_agent(cpu_agent)
        
        # Discover by capability
        gpu_agents = await registry.discover_agents({"capabilities": ["gpu"]})
        
        assert len(gpu_agents) == 1
        assert gpu_agents[0].agent_id == "agent_gpu"

    @pytest.mark.asyncio
    async def test_discover_agents_by_status(self):
        """Test discovering agents by status"""
        registry = AgentRegistry()
        
        active_agent = AgentInfo(
            agent_id="agent_active",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8092"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        busy_agent = AgentInfo(
            agent_id="agent_busy",
            agent_type=AgentType.WORKER,
            status=AgentStatus.BUSY,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8093"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(active_agent)
        await registry.register_agent(busy_agent)
        
        # Discover by status
        active_agents = await registry.discover_agents({"status": "active"})
        
        assert len(active_agents) == 1
        assert active_agents[0].status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_discover_agents_by_health_score(self):
        """Test discovering agents by minimum health score"""
        registry = AgentRegistry()
        
        healthy_agent = AgentInfo(
            agent_id="agent_healthy",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8094"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.9
        )
        
        unhealthy_agent = AgentInfo(
            agent_id="agent_unhealthy",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8095"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.5
        )
        
        await registry.register_agent(healthy_agent)
        await registry.register_agent(unhealthy_agent)
        
        # Discover by minimum health score
        healthy_agents = await registry.discover_agents({"min_health_score": 0.8})
        
        assert len(healthy_agents) == 1
        assert healthy_agents[0].agent_id == "agent_healthy"

    @pytest.mark.asyncio
    async def test_get_agent_by_id(self):
        """Test getting agent by ID"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_008",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8096"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        retrieved_agent = await registry.get_agent_by_id("agent_008")
        
        assert retrieved_agent is not None
        assert retrieved_agent.agent_id == "agent_008"

    @pytest.mark.asyncio
    async def test_get_agents_by_service(self):
        """Test getting agents by service"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_009",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference", "training"],
            endpoints={"http": "http://localhost:8097"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        inference_agents = await registry.get_agents_by_service("inference")
        
        assert len(inference_agents) == 1
        assert inference_agents[0].agent_id == "agent_009"

    @pytest.mark.asyncio
    async def test_get_agents_by_capability(self):
        """Test getting agents by capability"""
        registry = AgentRegistry()
        
        agent_info = AgentInfo(
            agent_id="agent_010",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["inference"],
            endpoints={"http": "http://localhost:8098"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        gpu_agents = await registry.get_agents_by_capability("gpu")
        
        assert len(gpu_agents) == 1
        assert gpu_agents[0].agent_id == "agent_010"

    @pytest.mark.asyncio
    async def test_get_registry_stats(self):
        """Test getting registry statistics"""
        registry = AgentRegistry()
        
        # Register multiple agents
        for i in range(3):
            agent_info = AgentInfo(
                agent_id=f"agent_stats_{i}",
                agent_type=AgentType.WORKER if i < 2 else AgentType.SPECIALIST,
                status=AgentStatus.ACTIVE if i < 2 else AgentStatus.BUSY,
                capabilities=["gpu"],
                services=["inference"],
                endpoints={"http": f"http://localhost:810{i}"},
                metadata={},
                last_heartbeat=datetime.now(UTC),
                registration_time=datetime.now(UTC)
            )
            await registry.register_agent(agent_info)
        
        stats = await registry.get_registry_stats()
        
        assert stats["total_agents"] == 3
        assert stats["status_counts"]["active"] == 2
        assert stats["status_counts"]["busy"] == 1
        assert stats["type_counts"]["worker"] == 2
        assert stats["type_counts"]["specialist"] == 1

    @pytest.mark.asyncio
    async def test_health_score_calculation(self):
        """Test health score calculation"""
        registry = AgentRegistry()
        
        # Agent with high load should have lower health score
        high_load_agent = AgentInfo(
            agent_id="agent_high_load",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8100"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            load_metrics={"cpu": 0.9, "memory": 0.85}
        )
        
        # Agent with low load should have higher health score
        low_load_agent = AgentInfo(
            agent_id="agent_low_load",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8101"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            load_metrics={"cpu": 0.3, "memory": 0.4}
        )
        
        await registry.register_agent(high_load_agent)
        await registry.register_agent(low_load_agent)
        
        # Update status to trigger health score calculation
        await registry.update_agent_status("agent_high_load", AgentStatus.ACTIVE)
        await registry.update_agent_status("agent_low_load", AgentStatus.ACTIVE)
        
        high_load_health = registry.agents["agent_high_load"].health_score
        low_load_health = registry.agents["agent_low_load"].health_score
        
        assert low_load_health > high_load_health


class TestAgentDiscoveryService:
    """Test agent discovery service"""

    @pytest.mark.asyncio
    async def test_discovery_service_initialization(self):
        """Test discovery service initialization"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)
        
        assert service.registry == registry
        assert len(service.discovery_handlers) == 0

    @pytest.mark.asyncio
    async def test_register_discovery_handler(self):
        """Test registering discovery handler"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)
        
        async def test_handler(message):
            return None
        
        service.register_discovery_handler("test_handler", test_handler)
        
        assert "test_handler" in service.discovery_handlers

    @pytest.mark.asyncio
    async def test_find_best_agent(self):
        """Test finding best agent for requirements"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)
        
        # Register agents with different health scores
        best_agent = AgentInfo(
            agent_id="agent_best",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8102"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.95
        )
        
        other_agent = AgentInfo(
            agent_id="agent_other",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8103"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.7
        )
        
        await registry.register_agent(best_agent)
        await registry.register_agent(other_agent)
        
        # Find best agent
        found = await service.find_best_agent({
            "capabilities": ["gpu"],
            "min_health_score": 0.5
        })
        
        assert found is not None
        assert found.agent_id == "agent_best"

    @pytest.mark.asyncio
    async def test_get_service_endpoints(self):
        """Test getting service endpoints"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)
        
        agent_info = AgentInfo(
            agent_id="agent_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8104", "ws": "ws://localhost:8105"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC)
        )
        
        await registry.register_agent(agent_info)
        endpoints = await service.get_service_endpoints("inference")
        
        assert "http" in endpoints
        assert "ws" in endpoints
        assert len(endpoints["http"]) == 1

    @pytest.mark.asyncio
    async def test_agent_info_serialization(self):
        """Test AgentInfo serialization to dict and back"""
        agent_info = AgentInfo(
            agent_id="agent_serial",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8106"},
            metadata={"region": "us-west"},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            load_metrics={"cpu": 0.5},
            tags={"production"}
        )
        
        # Convert to dict
        agent_dict = agent_info.to_dict()
        
        assert agent_dict["agent_id"] == "agent_serial"
        assert agent_dict["agent_type"] == "worker"
        assert agent_dict["status"] == "active"
        assert "gpu" in agent_dict["capabilities"]
        assert agent_dict["load_metrics"]["cpu"] == 0.5
        assert "production" in agent_dict["tags"]

        # Convert back from dict
        agent_back = AgentInfo.from_dict(agent_dict)
        
        assert agent_back.agent_id == "agent_serial"
        assert agent_back.agent_type == AgentType.WORKER
        assert agent_back.status == AgentStatus.ACTIVE

    def test_agent_info_empty_capabilities(self):
        """Test agent info with empty capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_caps",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert len(agent.capabilities) == 0
        assert len(agent.services) == 0

    def test_agent_info_multiple_endpoints(self):
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={
                "http": "http://localhost:8080",
                "grpc": "grpc://localhost:9090",
                "ws": "ws://localhost:8081"
            },
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert len(agent.endpoints) == 3
        assert "http" in agent.endpoints
        assert "grpc" in agent.endpoints
        assert "ws" in agent.endpoints

    def test_agent_info_with_multiple_capabilities(self):
        """Test agent info with multiple capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_caps",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "storage", "network", "compute"],
            services=["inference", "backup", "routing", "training"],
            endpoints={"http": "http://localhost:8086"},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert len(agent.capabilities) == 4
        assert len(agent.services) == 4
        assert "gpu" in agent.capabilities
        assert "training" in agent.services

    def test_agent_info_metadata_manipulation(self):
        """Test agent info metadata manipulation"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8087"},
            metadata={"region": "us-west"},
            last_heartbeat=now,
            registration_time=now
        )
        
        # Add metadata
        agent.metadata["gpu_model"] = "A100"
        agent.metadata["zone"] = "us-west-1"
        
        assert len(agent.metadata) == 3
        assert "gpu_model" in agent.metadata
        assert agent.metadata["region"] == "us-west"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
