"""
Agent Discovery Tests
Tests for agent registration, discovery, capability matching, and agent registry
"""

import asyncio
from datetime import UTC, datetime

import pytest
from app.routing.agent_discovery import (
    AgentDiscoveryService,
    AgentInfo,
    AgentRegistry,
    AgentStatus,
    AgentType,
    create_agent_info,
)


class TestAgentInfo:
    """Test agent information structure"""

    def test_agent_info_creation(self):  # noqa: F811
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
            health_score=0.95,
        )

        assert agent_info.agent_id == "agent_001"
        assert agent_info.agent_type == AgentType.WORKER
        assert agent_info.status == AgentStatus.ACTIVE
        assert len(agent_info.capabilities) == 2
        assert agent_info.health_score == 0.95

    def test_agent_info_serialization(self):  # noqa: F811
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
            registration_time=datetime.now(UTC),
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

    def test_create_agent_info_factory(self):  # noqa: F811
        """Test factory function for creating agent info"""
        agent_info = create_agent_info(
            agent_id="agent_003",
            agent_type="worker",
            capabilities=["compute"],
            services=["processing"],
            endpoints={"http": "http://localhost:8082"},
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
                registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            health_score=0.9,
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
            health_score=0.5,
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
            registration_time=datetime.now(UTC),
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
                registration_time=datetime.now(UTC),
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
            load_metrics={"cpu": 0.9, "memory": 0.85},
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
            load_metrics={"cpu": 0.3, "memory": 0.4},
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
            health_score=0.95,
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
            health_score=0.7,
        )

        await registry.register_agent(best_agent)
        await registry.register_agent(other_agent)

        # Find best agent
        found = await service.find_best_agent({"capabilities": ["gpu"], "min_health_score": 0.5})

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
            registration_time=datetime.now(UTC),
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
            tags={"production"},
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

    def test_agent_info_empty_capabilities(self):  # noqa: F811
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
            registration_time=now,
        )

        assert len(agent.capabilities) == 0
        assert len(agent.services) == 0

    def test_agent_info_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080", "grpc": "grpc://localhost:9090", "ws": "ws://localhost:8081"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 3
        assert "http" in agent.endpoints
        assert "grpc" in agent.endpoints
        assert "ws" in agent.endpoints

    def test_agent_info_with_multiple_capabilities(self):  # noqa: F811
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
            registration_time=now,
        )

        assert len(agent.capabilities) == 4
        assert len(agent.services) == 4
        assert "gpu" in agent.capabilities
        assert "training" in agent.services

    def test_agent_info_metadata_manipulation(self):  # noqa: F811
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
            registration_time=now,
        )

        # Add metadata
        agent.metadata["gpu_model"] = "A100"
        agent.metadata["zone"] = "us-west-1"

        assert len(agent.metadata) == 3
        assert "gpu_model" in agent.metadata
        assert agent.metadata["region"] == "us-west"

    def test_agent_info_with_specialist_type(self):  # noqa: F811
        """Test agent info with specialist agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_specialist",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["whisper", "transcription"],
            services=["audio_processing"],
            endpoints={"http": "http://localhost:8101"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.SPECIALIST
        assert "whisper" in agent.capabilities

    def test_agent_info_with_coordinator_type(self):  # noqa: F811
        """Test agent info with coordinator agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_coordinator",
            agent_type=AgentType.COORDINATOR,
            status=AgentStatus.ACTIVE,
            capabilities=["orchestration", "scheduling"],
            services=["workflow_management"],
            endpoints={"http": "http://localhost:8102"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.COORDINATOR
        assert "orchestration" in agent.capabilities

    def test_agent_info_with_multiple_capabilities(self):  # noqa: F811
        """Test agent info with multiple capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_cap",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "storage", "network"],
            services=["training", "inference"],
            endpoints={"http": "http://localhost:8113"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 3
        assert "gpu" in agent.capabilities
        assert "storage" in agent.capabilities

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["transcription"],
            services=["audio"],
            endpoints={"http": "http://localhost:8114"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1
        assert agent.services[0] == "audio"

    def test_agent_info_with_empty_endpoints(self):  # noqa: F811
        """Test agent info with empty endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_no_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            services=["training"],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 0

    def test_agent_info_with_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8116", "grpc": "grpc://localhost:9096", "ws": "ws://localhost:8096"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 3
        assert "http" in agent.endpoints
        assert "grpc" in agent.endpoints

    def test_agent_info_with_no_services(self):  # noqa: F811
        """Test agent info with no services"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_no_services",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            services=[],
            endpoints={"http": "http://localhost:8117"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 0

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["transcription"],
            services=["audio"],
            endpoints={"http": "http://localhost:8118"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1
        assert agent.capabilities[0] == "transcription"

    def test_agent_info_with_specialist_type(self):  # noqa: F811
        """Test agent info with specialist agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_specialist",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["training"],
            endpoints={"http": "http://localhost:8119"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.SPECIALIST

    def test_agent_info_with_maintenance_status(self):  # noqa: F811
        """Test agent info with maintenance status"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_maintenance",
            agent_type=AgentType.WORKER,
            status=AgentStatus.MAINTENANCE,
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8120"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.status == AgentStatus.MAINTENANCE

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_12345",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8121"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "12345" in agent.agent_id

    def test_agent_info_with_long_name_in_metadata(self):  # noqa: F811
        """Test agent info with long name in metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_long_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8122"},
            metadata={"name": "A very long agent name for testing purposes"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata["name"]) > 20

    def test_agent_info_with_empty_metadata(self):  # noqa: F811
        """Test agent info with empty metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8123"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 0

    def test_agent_info_with_multiple_metadata_fields(self):  # noqa: F811
        """Test agent info with multiple metadata fields"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8124"},
            metadata={"name": "Agent", "version": "1.0", "region": "us-west"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 3

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8125"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1

    def test_agent_info_with_multiple_services(self):  # noqa: F811
        """Test agent info with multiple services"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_services",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference", "training", "storage"],
            endpoints={"http": "http://localhost:8126"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 3

    def test_agent_info_with_empty_endpoints(self):  # noqa: F811
        """Test agent info with empty endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 0

    def test_agent_info_with_single_endpoint(self):  # noqa: F811
        """Test agent info with single endpoint"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_endpoint",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8127"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 1

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123_special@",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8128"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id
        assert "@" in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123_456",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8129"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_mixed_case_agent_id(self):  # noqa: F811
        """Test agent info with mixed case agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="Agent123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8130"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id[0].isupper()

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8131"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1

    def test_agent_info_with_empty_capabilities(self):  # noqa: F811
        """Test agent info with empty capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_caps",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=["inference"],
            endpoints={"http": "http://localhost:8132"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 0

    def test_agent_info_with_multiple_metadata_keys(self):  # noqa: F811
        """Test agent info with multiple metadata keys"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_meta",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8133"},
            metadata={"key1": "value1", "key2": "value2", "key3": "value3"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 3

    def test_agent_info_with_empty_metadata(self):  # noqa: F811
        """Test agent info with empty metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_meta_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8134"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 0

    def test_agent_info_with_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8135", "grpc": "localhost:8136"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 2

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8137"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8138"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8139"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "123" in agent.agent_id

    def test_agent_info_with_hyphen_in_agent_id(self):  # noqa: F811
        """Test agent info with hyphen in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8140"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@#$",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8141"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id
        assert "#" in agent.agent_id
        assert "$" in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8142"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_empty_agent_id(self):  # noqa: F811
        """Test agent info with empty agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8143"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id == ""

    def test_agent_info_with_single_character_agent_id(self):  # noqa: F811
        """Test agent info with single character agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="A",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8144"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.agent_id) == 1

    def test_agent_info_with_mixed_case_agent_id(self):  # noqa: F811
        """Test agent info with mixed case agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="AgentID",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8145"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "Agent" in agent.agent_id
        assert "ID" in agent.agent_id

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8146"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id == "123"

    def test_agent_info_with_hyphen_in_agent_id(self):  # noqa: F811
        """Test agent info with hyphen in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8147"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id

    def test_agent_info_with_dot_in_agent_id(self):  # noqa: F811
        """Test agent info with dot in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent.123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8148"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "." in agent.agent_id

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with various special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@#$",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8149"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id
        assert "#" in agent.agent_id
        assert "$" in agent.agent_id

    def test_agent_info_with_spaces_in_agent_id(self):  # noqa: F811
        """Test agent info with spaces in agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent 123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8150"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert " " in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8151"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_pipe_in_agent_id(self):  # noqa: F811
        """Test agent info with pipe in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent|123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8152"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "|" in agent.agent_id

    def test_agent_info_with_colon_in_agent_id(self):  # noqa: F811
        """Test agent info with colon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent:123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8153"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ":" in agent.agent_id

    def test_agent_info_with_semicolon_in_agent_id(self):  # noqa: F811
        """Test agent info with semicolon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent;123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8154"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ";" in agent.agent_id

    def test_agent_info_with_equals_in_agent_id(self):  # noqa: F811
        """Test agent info with equals in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent=123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8155"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "=" in agent.agent_id

    def test_agent_info_with_plus_in_agent_id(self):  # noqa: F811
        """Test agent info with plus in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent+123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8156"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "+" in agent.agent_id

    def test_agent_info_with_slash_in_agent_id(self):  # noqa: F811
        """Test agent info with slash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent/123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8157"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "/" in agent.agent_id

    def test_agent_info_with_backslash_in_agent_id(self):  # noqa: F811
        """Test agent info with backslash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent\\123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8158"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "\\" in agent.agent_id

    def test_agent_info_with_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent[123]",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8159"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "[" in agent.agent_id
        assert "]" in agent.agent_id

    def test_agent_info_with_parenthesis_in_agent_id(self):  # noqa: F811
        """Test agent info with parenthesis in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent(123)",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8160"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "(" in agent.agent_id
        assert ")" in agent.agent_id

    def test_agent_info_with_curly_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with curly bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent{123}",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8161"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "{" in agent.agent_id
        assert "}" in agent.agent_id

    def test_agent_info_with_angle_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with angle bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent<123>",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8162"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "<" in agent.agent_id
        assert ">" in agent.agent_id

    def test_agent_info_with_dollar_in_agent_id(self):  # noqa: F811
        """Test agent info with dollar in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent$123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8163"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "$" in agent.agent_id

    def test_agent_info_with_at_in_agent_id(self):  # noqa: F811
        """Test agent info with at in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8164"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id

    def test_agent_info_with_percent_in_agent_id(self):  # noqa: F811
        """Test agent info with percent in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent%123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8165"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "%" in agent.agent_id

    def test_agent_info_with_ampersand_in_agent_id(self):  # noqa: F811
        """Test agent info with ampersand in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent&123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8166"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "&" in agent.agent_id

    def test_agent_info_with_hash_in_agent_id(self):  # noqa: F811
        """Test agent info with hash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent#123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8167"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "#" in agent.agent_id

    def test_agent_info_with_exclamation_in_agent_id(self):  # noqa: F811
        """Test agent info with exclamation in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent!123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8168"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "!" in agent.agent_id

    def test_agent_info_with_asterisk_in_agent_id(self):  # noqa: F811
        """Test agent info with asterisk in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent*123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8169"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "*" in agent.agent_id

    def test_agent_info_with_plus_in_agent_id(self):  # noqa: F811
        """Test agent info with plus in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent+123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8170"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "+" in agent.agent_id

    def test_agent_info_with_equals_in_agent_id(self):  # noqa: F811
        """Test agent info with equals in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent=123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8171"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "=" in agent.agent_id

    def test_agent_info_with_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent[123]",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8172"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "[" in agent.agent_id

    def test_agent_info_with_curly_brace_in_agent_id(self):  # noqa: F811
        """Test agent info with curly brace in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent{123}",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8173"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "{" in agent.agent_id

    def test_agent_info_with_pipe_in_agent_id(self):  # noqa: F811
        """Test agent info with pipe in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent|123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8174"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "|" in agent.agent_id

    def test_agent_info_with_colon_in_agent_id(self):  # noqa: F811
        """Test agent info with colon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent:123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8175"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ":" in agent.agent_id

    def test_agent_info_with_semicolon_in_agent_id(self):  # noqa: F811
        """Test agent info with semicolon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent;123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8176"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ";" in agent.agent_id

    def test_agent_info_with_comma_in_agent_id(self):  # noqa: F811
        """Test agent info with comma in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent,123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8177"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "," in agent.agent_id

    @pytest.mark.asyncio
    async def test_get_agents_by_type(self):
        """Test getting agents by type"""
        registry = AgentRegistry()

        worker_agent = AgentInfo(
            agent_id="worker_agent",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8178"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        specialist_agent = AgentInfo(
            agent_id="specialist_agent",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8179"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        await registry.register_agent(worker_agent)
        await registry.register_agent(specialist_agent)

        workers = await registry.get_agents_by_type(AgentType.WORKER)

        assert len(workers) == 1
        assert workers[0].agent_id == "worker_agent"
        assert workers[0].agent_type == AgentType.WORKER

    @pytest.mark.asyncio
    async def test_get_service_endpoints_v2(self):
        """Test getting service endpoints - variant 2"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)

        agent_info = AgentInfo(
            agent_id="endpoint_agent",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8180", "grpc": "grpc://localhost:8181"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        await registry.register_agent(agent_info)
        endpoints = await service.get_service_endpoints("inference")

        assert "http" in endpoints
        assert "grpc" in endpoints
        assert len(endpoints["http"]) == 1
        assert len(endpoints["grpc"]) == 1

    @pytest.mark.asyncio
    async def test_get_agent_by_id_not_found(self):
        """Test getting non-existent agent by ID"""
        registry = AgentRegistry()

        retrieved_agent = await registry.get_agent_by_id("nonexistent_agent")

        assert retrieved_agent is None

    @pytest.mark.asyncio
    async def test_get_agents_by_service_empty(self):
        """Test getting agents by service when no agents registered"""
        registry = AgentRegistry()

        agents = await registry.get_agents_by_service("inference")

        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_get_agents_by_capability_empty(self):
        """Test getting agents by capability when no agents registered"""
        registry = AgentRegistry()

        agents = await registry.get_agents_by_capability("gpu")

        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_get_agents_by_type_empty(self):
        """Test getting agents by type when no agents registered"""
        registry = AgentRegistry()

        workers = await registry.get_agents_by_type(AgentType.WORKER)

        assert len(workers) == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_agent(self):
        """Test unregistering a non-existent agent"""
        registry = AgentRegistry()

        success = await registry.unregister_agent("nonexistent_agent")

        assert success is False

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_agent(self):
        """Test updating status of non-existent agent"""
        registry = AgentRegistry()

        success = await registry.update_agent_status("nonexistent_agent", AgentStatus.BUSY)

        assert success is False

    @pytest.mark.asyncio
    async def test_update_heartbeat_nonexistent_agent(self):
        """Test updating heartbeat of non-existent agent"""
        registry = AgentRegistry()

        success = await registry.update_agent_heartbeat("nonexistent_agent")

        assert success is False

    @pytest.mark.asyncio
    async def test_register_duplicate_agent(self):
        """Test registering an agent that already exists"""
        registry = AgentRegistry()

        agent_info = AgentInfo(
            agent_id="duplicate_agent",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8182"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        await registry.register_agent(agent_info)
        success = await registry.register_agent(agent_info)

        assert success is True

    @pytest.mark.asyncio
    async def test_discover_agents_empty_query(self):
        """Test discovering agents with empty query"""
        registry = AgentRegistry()

        agent_info = AgentInfo(
            agent_id="agent_query",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8183"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        await registry.register_agent(agent_info)
        all_agents = await registry.discover_agents({})

        assert len(all_agents) == 1
        assert all_agents[0].agent_id == "agent_query"

    @pytest.mark.asyncio
    async def test_discover_agents_with_multiple_filters(self):
        """Test discovering agents with multiple filters"""
        registry = AgentRegistry()

        agent_info = AgentInfo(
            agent_id="agent_multi",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["inference"],
            endpoints={"http": "http://localhost:8184"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.9,
        )

        await registry.register_agent(agent_info)
        filtered_agents = await registry.discover_agents(
            {"agent_type": "worker", "capabilities": ["gpu"], "min_health_score": 0.8}
        )

        assert len(filtered_agents) == 1
        assert filtered_agents[0].agent_id == "agent_multi"

    @pytest.mark.asyncio
    async def test_find_best_agent_with_requirements(self):
        """Test finding best agent with specific requirements"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)

        best_agent = AgentInfo(
            agent_id="best_agent_test",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["inference"],
            endpoints={"http": "http://localhost:8185"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.95,
        )

        await registry.register_agent(best_agent)
        found = await service.find_best_agent({"capabilities": ["gpu"], "min_health_score": 0.9})

        assert found is not None
        assert found.agent_id == "best_agent_test"

    @pytest.mark.asyncio
    async def test_find_best_agent_no_match(self):
        """Test finding best agent when no agent matches requirements"""
        registry = AgentRegistry()
        service = AgentDiscoveryService(registry)

        agent_info = AgentInfo(
            agent_id="low_health_agent",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["cpu"],
            services=["compute"],
            endpoints={"http": "http://localhost:8186"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.5,
        )

        await registry.register_agent(agent_info)
        found = await service.find_best_agent({"capabilities": ["gpu"], "min_health_score": 0.9})

        assert found is None

    @pytest.mark.asyncio
    async def test_get_registry_stats_empty(self):
        """Test getting registry stats when no agents registered"""
        registry = AgentRegistry()

        stats = await registry.get_registry_stats()

        assert stats["total_agents"] == 0
        # Status counts and type counts might be empty or have default values
        if "status_counts" in stats:
            assert stats.get("status_counts", {}).get("active", 0) == 0
        if "type_counts" in stats:
            assert stats.get("type_counts", {}).get("worker", 0) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
