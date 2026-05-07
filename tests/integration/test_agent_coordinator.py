"""Integration tests for AITBC Agent Coordinator service."""

import pytest
import asyncio
import httpx
from typing import Dict, Any


@pytest.fixture
async def coordinator_client():
    """Create an HTTP client for coordinator API."""
    async with httpx.AsyncClient(base_url="http://localhost:9001", timeout=30) as client:
        yield client


@pytest.fixture
def sample_agent_data():
    """Sample agent registration data."""
    return {
        "agent_id": "test-integration-agent",
        "agent_type": "worker",
        "capabilities": ["data-processing", "analysis"],
        "services": ["task-execution"],
        "endpoints": {"http": "http://localhost:9002"},
        "metadata": {"version": "1.0.0", "test": True}
    }


@pytest.fixture
def sample_task_data():
    """Sample task submission data."""
    return {
        "task_data": {
            "model": "llama2",
            "prompt": "test prompt"
        },
        "priority": "normal",
        "requirements": {}
    }


class TestAgentRegistration:
    """Test agent registration endpoints."""

    @pytest.mark.asyncio
    async def test_register_agent_success(self, coordinator_client, sample_agent_data):
        """Test successful agent registration."""
        response = await coordinator_client.post("/agents/register", json=sample_agent_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == sample_agent_data["agent_id"]

    @pytest.mark.asyncio
    async def test_register_agent_duplicate(self, coordinator_client, sample_agent_data):
        """Test registering duplicate agent."""
        # Register first time
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Try to register again
        response = await coordinator_client.post("/agents/register", json=sample_agent_data)
        # Should succeed (update existing) or fail depending on implementation
        assert response.status_code in (200, 201, 409)

    @pytest.mark.asyncio
    async def test_register_agent_invalid_data(self, coordinator_client):
        """Test registration with invalid data."""
        invalid_data = {"agent_id": "invalid"}  # Missing required fields
        response = await coordinator_client.post("/agents/register", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_agent_missing_agent_id(self, coordinator_client):
        """Test registration without agent ID."""
        invalid_data = {"agent_type": "worker"}
        response = await coordinator_client.post("/agents/register", json=invalid_data)
        assert response.status_code == 422


class TestAgentDiscovery:
    """Test agent discovery endpoints."""

    @pytest.mark.asyncio
    async def test_discover_all_agents(self, coordinator_client, sample_agent_data):
        """Test discovering all agents."""
        # Register an agent first
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Discover all agents
        response = await coordinator_client.post("/agents/discover", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "agents" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_discover_by_status(self, coordinator_client, sample_agent_data):
        """Test discovering agents by status."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Discover active agents
        response = await coordinator_client.post("/agents/discover", json={"status": "active"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_discover_by_type(self, coordinator_client, sample_agent_data):
        """Test discovering agents by type."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Discover worker agents
        response = await coordinator_client.post("/agents/discover", json={"agent_type": "worker"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_discover_empty_result(self, coordinator_client):
        """Test discovering agents with no matches."""
        # Search for non-existent type
        response = await coordinator_client.post("/agents/discover", json={"agent_type": "nonexistent"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 0


class TestAgentStatus:
    """Test agent status endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_info(self, coordinator_client, sample_agent_data):
        """Test getting agent information."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Get agent info
        response = await coordinator_client.get(f"/agents/{sample_agent_data['agent_id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent"]["agent_id"] == sample_agent_data["agent_id"]

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, coordinator_client):
        """Test getting non-existent agent."""
        response = await coordinator_client.get("/agents/nonexistent-agent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent_status(self, coordinator_client, sample_agent_data):
        """Test updating agent status."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Update status
        response = await coordinator_client.put(
            f"/agents/{sample_agent_data['agent_id']}/status",
            json={"status": "busy", "load_metrics": {"active_connections": 5}}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["new_status"] == "busy"

    @pytest.mark.asyncio
    async def test_update_agent_status_invalid(self, coordinator_client, sample_agent_data):
        """Test updating with invalid status."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Try invalid status
        response = await coordinator_client.put(
            f"/agents/{sample_agent_data['agent_id']}/status",
            json={"status": "invalid_status"}
        )
        assert response.status_code in (400, 422)


class TestTaskDistribution:
    """Test task distribution endpoints."""

    @pytest.mark.asyncio
    async def test_submit_task_success(self, coordinator_client, sample_task_data):
        """Test successful task submission."""
        response = await coordinator_client.post("/tasks/submit", json=sample_task_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["status"] == "success"
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_submit_task_invalid_priority(self, coordinator_client):
        """Test task submission with invalid priority."""
        invalid_data = {
            "task_data": {"model": "llama2", "prompt": "test"},
            "priority": "invalid_priority",
            "requirements": {}
        }
        response = await coordinator_client.post("/tasks/submit", json=invalid_data)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_task_distribution_stats(self, coordinator_client):
        """Test getting task distribution statistics."""
        response = await coordinator_client.get("/tasks/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        assert "load_balancer_stats" in data["stats"]

    @pytest.mark.asyncio
    async def test_task_assignment_with_active_agent(self, coordinator_client, sample_agent_data, sample_task_data):
        """Test task assignment to active agent."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Submit task
        response = await coordinator_client.post("/tasks/submit", json=sample_task_data)
        assert response.status_code in (200, 201)
        
        # Check stats
        await asyncio.sleep(1)  # Give time for distribution
        stats_response = await coordinator_client.get("/tasks/status")
        stats_data = stats_response.json()
        assert stats_data["stats"]["tasks_distributed"] >= 1


class TestLoadBalancing:
    """Test load balancing functionality."""

    @pytest.mark.asyncio
    async def test_least_connections_strategy(self, coordinator_client):
        """Test least connections load balancing strategy."""
        # Register multiple agents
        agents = [
            {"agent_id": "agent-1", "agent_type": "worker"},
            {"agent_id": "agent-2", "agent_type": "worker"},
            {"agent_id": "agent-3", "agent_type": "worker"}
        ]
        
        for agent in agents:
            await coordinator_client.post("/agents/register", json=agent)
        
        # Submit multiple tasks
        for i in range(5):
            await coordinator_client.post("/tasks/submit", json={
                "task_data": {"task": f"task-{i}"},
                "priority": "normal",
                "requirements": {}
            })
        
        # Check distribution
        await asyncio.sleep(2)
        stats_response = await coordinator_client.get("/tasks/status")
        stats_data = stats_response.json()
        assert stats_data["stats"]["load_balancer_stats"]["active_agents"] >= 3

    @pytest.mark.asyncio
    async def test_no_eligible_agents(self, coordinator_client, sample_task_data):
        """Test task submission when no eligible agents exist."""
        # Submit task without any agents registered
        response = await coordinator_client.post("/tasks/submit", json=sample_task_data)
        # Should succeed (task queued) or fail depending on implementation
        assert response.status_code in (200, 201, 503)


class TestQueueManagement:
    """Test task queue management endpoints."""

    @pytest.mark.asyncio
    async def test_get_queue_sizes(self, coordinator_client):
        """Test getting queue sizes."""
        response = await coordinator_client.get("/tasks/queues")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "queue_sizes" in data

    @pytest.mark.asyncio
    async def test_clear_queue(self, coordinator_client, sample_task_data):
        """Test clearing a priority queue."""
        # Submit some tasks
        for i in range(3):
            await coordinator_client.post("/tasks/submit", json=sample_task_data)
        
        # Clear normal priority queue
        response = await coordinator_client.post("/tasks/queues/normal/clear")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "cleared_count" in data

    @pytest.mark.asyncio
    async def test_clear_invalid_queue(self, coordinator_client):
        """Test clearing with invalid priority."""
        response = await coordinator_client.post("/tasks/queues/invalid/clear")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, coordinator_client):
        """Test getting detailed queue statistics."""
        response = await coordinator_client.get("/tasks/queues/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "queue_sizes" in data
        assert "distribution_stats" in data


class TestHeartbeat:
    """Test agent heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_agent_heartbeat(self, coordinator_client, sample_agent_data):
        """Test agent heartbeat endpoint."""
        # Register an agent
        await coordinator_client.post("/agents/register", json=sample_agent_data)
        
        # Send heartbeat
        response = await coordinator_client.post(f"/agents/{sample_agent_data['agent_id']}/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "heartbeat_at" in data

    @pytest.mark.asyncio
    async def test_heartbeat_nonexistent_agent(self, coordinator_client):
        """Test heartbeat for non-existent agent."""
        response = await coordinator_client.post("/agents/nonexistent/heartbeat")
        assert response.status_code == 404


class TestHealthCheck:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, coordinator_client):
        """Test service health check."""
        response = await coordinator_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
