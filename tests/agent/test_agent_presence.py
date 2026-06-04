"""
Agent Presence Tests
Tests for agent presence, heartbeat, and status monitoring
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime, timedelta

from app.routing.agent_discovery import AgentInfo, AgentStatus, AgentType


class TestAgentPresence:
    """Test agent presence tracking"""

    def test_agent_info_creation(self):
        """Test creating agent info"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_001",
            agent_type=AgentType.WORKER,
            status=AgentStatus.INACTIVE,
            capabilities=["gpu", "cpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080"},
            metadata={"region": "us-east"},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert agent.agent_id == "agent_001"
        assert agent.agent_type == AgentType.WORKER
        assert len(agent.capabilities) == 2
        assert agent.status == AgentStatus.INACTIVE

    def test_agent_status_transitions(self):
        """Test agent status transitions"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_002",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.INACTIVE,
            capabilities=["storage"],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        # Initially inactive
        assert agent.status == AgentStatus.INACTIVE
        
        # Transition to active
        agent.status = AgentStatus.ACTIVE
        assert agent.status == AgentStatus.ACTIVE
        
        # Transition to busy
        agent.status = AgentStatus.BUSY
        assert agent.status == AgentStatus.BUSY

    def test_agent_heartbeat_tracking(self):
        """Test agent heartbeat timestamp updates"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_003",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        # Initially has heartbeat
        assert agent.last_heartbeat is not None
        assert isinstance(agent.last_heartbeat, datetime)
        
        # Update heartbeat
        agent.last_heartbeat = datetime.now(UTC)
        assert agent.last_heartbeat > now

    def test_agent_health_score_calculation(self):
        """Test agent health score based on activity"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_004",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
            health_score=1.0
        )
        
        # Health score should be high for active agent
        assert agent.health_score == 1.0
        assert agent.status == AgentStatus.ACTIVE

    def test_agent_capabilities_filtering(self):
        """Test filtering agents by capabilities"""
        now = datetime.now(UTC)
        agents = [
            AgentInfo(
                agent_id="agent_001",
                agent_type=AgentType.WORKER,
                status=AgentStatus.ACTIVE,
                capabilities=["gpu", "cpu"],
                services=[],
                endpoints={},
                metadata={},
                last_heartbeat=now,
                registration_time=now
            ),
            AgentInfo(
                agent_id="agent_002",
                agent_type=AgentType.WORKER,
                status=AgentStatus.ACTIVE,
                capabilities=["cpu"],
                services=[],
                endpoints={},
                metadata={},
                last_heartbeat=now,
                registration_time=now
            ),
            AgentInfo(
                agent_id="agent_003",
                agent_type=AgentType.SPECIALIST,
                status=AgentStatus.ACTIVE,
                capabilities=["storage", "gpu"],
                services=[],
                endpoints={},
                metadata={},
                last_heartbeat=now,
                registration_time=now
            )
        ]
        
        # Filter by GPU capability
        gpu_agents = [a for a in agents if "gpu" in a.capabilities]
        assert len(gpu_agents) == 2
        
        # Filter by storage capability
        storage_agents = [a for a in agents if "storage" in a.capabilities]
        assert len(storage_agents) == 1

    def test_agent_services_registration(self):
        """Test agent service registration"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_005",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=["inference", "training", "serving"],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert len(agent.services) == 3
        assert "inference" in agent.services
        assert "training" in agent.services
        assert "serving" in agent.services

    def test_agent_endpoint_management(self):
        """Test agent endpoint configuration"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_006",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={
                "http": "http://localhost:8080",
                "grpc": "localhost:9090",
                "websocket": "ws://localhost:8081"
            },
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        assert len(agent.endpoints) == 3
        assert agent.endpoints["http"] == "http://localhost:8080"
        assert agent.endpoints["grpc"] == "localhost:9090"

    def test_agent_metadata_storage(self):
        """Test agent metadata for additional information"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_007",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={
                "region": "us-east",
                "gpu_model": "NVIDIA A100",
                "memory_gb": 80,
                "version": "1.0.0"
            },
            last_heartbeat=now,
            registration_time=now
        )
        
        assert agent.metadata["region"] == "us-east"
        assert agent.metadata["gpu_model"] == "NVIDIA A100"
        assert agent.metadata["memory_gb"] == 80

    def test_agent_status_values(self):
        """Test all agent status enum values"""
        statuses = [
            AgentStatus.ACTIVE,
            AgentStatus.INACTIVE,
            AgentStatus.BUSY,
            AgentStatus.MAINTENANCE,
            AgentStatus.ERROR
        ]
        
        for status in statuses:
            assert isinstance(status.value, str)

    def test_agent_type_values(self):
        """Test all agent type enum values"""
        types = [
            AgentType.COORDINATOR,
            AgentType.WORKER,
            AgentType.SPECIALIST,
            AgentType.MONITOR,
            AgentType.GATEWAY,
            AgentType.ORCHESTRATOR
        ]
        
        for agent_type in types:
            assert isinstance(agent_type.value, str)

    def test_agent_load_metrics(self):
        """Test agent load metrics tracking"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_008",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
            load_metrics={
                "cpu": 0.5,
                "memory": 0.6,
                "gpu": 0.8
            }
        )
        
        assert len(agent.load_metrics) == 3
        assert agent.load_metrics["cpu"] == 0.5
        assert agent.load_metrics["gpu"] == 0.8

    def test_agent_tags_management(self):
        """Test agent tags for categorization"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_009",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
            tags={"gpu", "inference", "production"}
        )
        
        assert len(agent.tags) == 3
        assert "gpu" in agent.tags
        assert "inference" in agent.tags
        assert "production" in agent.tags

    def test_agent_tags_add_remove(self):
        """Test adding and removing tags"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_010",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
            tags={"gpu"}
        )
        
        # Add tag
        agent.tags.add("inference")
        assert "inference" in agent.tags
        assert len(agent.tags) == 2
        
        # Remove tag
        agent.tags.remove("gpu")
        assert "gpu" not in agent.tags
        assert len(agent.tags) == 1

    def test_agent_info_with_all_fields(self):
        """Test agent info with all fields populated"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_full",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "storage", "network"],
            services=["inference", "backup", "routing"],
            endpoints={
                "http": "http://localhost:8083",
                "grpc": "grpc://localhost:9093",
                "ws": "ws://localhost:8084"
            },
            metadata={"region": "us-west", "gpu_model": "A100", "zone": "us-west-1"},
            last_heartbeat=now,
            registration_time=now,
            load_metrics={
                "cpu": 0.75,
                "memory": 0.60,
                "gpu": 0.85,
                "disk": 0.40,
                "network_in": 2000,
                "network_out": 1500,
                "active_connections": 100
            },
            tags={"production", "high-performance", "gpu-cluster"}
        )
        
        assert len(agent.capabilities) == 3
        assert len(agent.services) == 3
        assert len(agent.endpoints) == 3
        assert len(agent.metadata) == 3
        assert len(agent.load_metrics) == 7
        assert len(agent.tags) == 3

    def test_agent_info_status_changes(self):
        """Test agent info status changes"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_status",
            agent_type=AgentType.WORKER,
            status=AgentStatus.INACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8085"},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        # Change status to active
        agent.status = AgentStatus.ACTIVE
        assert agent.status == AgentStatus.ACTIVE
        
        # Change status to inactive
        agent.status = AgentStatus.INACTIVE
        assert agent.status == AgentStatus.INACTIVE

    def test_agent_info_timestamp_comparison(self):
        """Test agent info timestamp comparison"""
        now = datetime.now(UTC)
        later = now + timedelta(hours=1)
        
        agent1 = AgentInfo(
            agent_id="agent_time1",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        agent2 = AgentInfo(
            agent_id="agent_time2",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=later,
            registration_time=now
        )
        
        assert agent2.last_heartbeat > agent1.last_heartbeat

    def test_agent_info_endpoint_manipulation(self):
        """Test agent info endpoint manipulation"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={"http": "http://localhost:8089"},
            metadata={},
            last_heartbeat=now,
            registration_time=now
        )
        
        # Add endpoint
        agent.endpoints["grpc"] = "grpc://localhost:9095"
        assert len(agent.endpoints) == 2
        
        # Remove endpoint
        del agent.endpoints["http"]
        assert "http" not in agent.endpoints
        assert len(agent.endpoints) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
