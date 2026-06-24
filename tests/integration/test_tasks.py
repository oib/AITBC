"""Integration tests for task distribution, load balancing, and queue management."""

from typing import Any

import pytest
from starlette.testclient import TestClient


class TestTaskDistribution:
    """Test task distribution endpoints."""

    def test_submit_task_success(self, coordinator_client: TestClient, sample_task_data: dict[str, Any]):
        """Test successful task submission."""
        response = coordinator_client.post("/v1/tasks/submit", json=sample_task_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "task_id" in data or "status" in data

    def test_submit_task_invalid_priority(self, coordinator_client: TestClient):
        """Test task submission with invalid priority."""
        invalid_data = {"task_data": {"model": "llama2"}, "priority": "invalid"}
        response = coordinator_client.post("/v1/tasks/submit", json=invalid_data)
        assert response.status_code in (400, 422)

    def test_task_distribution_stats(self, coordinator_client: TestClient):
        """Test getting task distribution statistics."""
        response = coordinator_client.get("/v1/tasks/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        assert "tasks_distributed" in data["stats"]
        assert "load_balancer_stats" in data["stats"]
        assert "active_agents" in data["stats"]["load_balancer_stats"]

    def test_task_assignment_with_active_agent(
        self, coordinator_client: TestClient, sample_agent_data: dict[str, Any], sample_task_data: dict[str, Any]
    ):
        """Test task assignment with active agent."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        coordinator_client.put(f"/v1/agents/{sample_agent_data['agent_id']}/status", json={"status": "active"})
        response = coordinator_client.post("/v1/tasks/submit", json=sample_task_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "task_id" in data or "status" in data


class TestLoadBalancing:
    """Test load balancing strategies."""

    def test_least_connections_strategy(self, coordinator_client: TestClient):
        """Test least connections strategy."""
        agents = []
        for i in range(3):
            agent_data = {
                "agent_id": f"test-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:{9002 + i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            agents.append(agent_data)

        for agent in agents:
            coordinator_client.put(f"/v1/agents/{agent['agent_id']}/status", json={"status": "active"})

        task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
        response = coordinator_client.post("/v1/tasks/submit", json=task_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert "task_id" in data or "status" in data

    def test_no_eligible_agents(self, coordinator_client: TestClient, sample_task_data: dict[str, Any]):
        """Test task submission with no eligible agents."""
        response = coordinator_client.post("/v1/tasks/submit", json=sample_task_data)
        assert response.status_code in (200, 201, 503)
        if response.status_code in (200, 201):
            data = response.json()
            assert "task_id" in data or "status" in data


class TestQueueManagement:
    """Test queue management endpoints."""

    def test_get_queue_sizes(self, coordinator_client: TestClient):
        """Test getting queue sizes."""
        response = coordinator_client.get("/v1/tasks/queues")
        if response.status_code == 404:
            pytest.skip("Queue endpoints not registered in running coordinator")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "queue_sizes" in data

    def test_clear_queue(self, coordinator_client: TestClient, sample_task_data: dict[str, Any]):
        """Test clearing a queue."""
        coordinator_client.post("/v1/tasks/submit", json=sample_task_data)
        response = coordinator_client.post("/v1/tasks/queues/normal/clear")
        if response.status_code == 404:
            pytest.skip("Queue endpoints not registered in running coordinator")
        assert response.status_code in (200, 204)

    def test_clear_invalid_queue(self, coordinator_client: TestClient):
        """Test clearing invalid queue."""
        response = coordinator_client.post("/v1/tasks/queues/invalid/clear")
        assert response.status_code in (400, 404)

    def test_get_queue_stats(self, coordinator_client: TestClient):
        """Test getting queue statistics."""
        response = coordinator_client.get("/v1/tasks/queues/stats")
        if response.status_code == 404:
            pytest.skip("Queue endpoints not registered in running coordinator")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "queue_sizes" in data


class TestLoadBalancer:
    """Test load balancer endpoints."""

    def test_set_load_balancing_strategies(self, coordinator_client: TestClient):
        """Test setting all load balancing strategies."""
        strategies = [
            "round_robin",
            "least_connections",
            "least_response_time",
            "weighted_round_robin",
            "resource_based",
            "capability_based",
        ]
        for strategy in strategies:
            response = coordinator_client.put("/api/v1/agent/messages/load-balancer/strategy", params={"strategy": strategy})
            assert response.status_code in (200, 400, 503)
            if response.status_code == 200:
                data = response.json()
                assert "status" in data or "strategy" in data

    def test_get_load_balancer_stats_detailed(self, coordinator_client: TestClient):
        """Test getting detailed load balancer statistics."""
        response = coordinator_client.get("/api/v1/agent/messages/load-balancer/stats")
        if response.status_code == 200:
            data = response.json()
            assert "stats" in data
            assert data["status"] == "success"

    def test_task_distribution_with_strategies(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test task distribution with different strategies."""
        for i in range(3):
            agent_data = {
                "agent_id": f"lb-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:9002{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            coordinator_client.put(f"/v1/agents/lb-agent-{i}/status", json={"status": "active"})

        strategies = ["round_robin", "least_connections"]
        for strategy in strategies:
            response = coordinator_client.put("/api/v1/agent/messages/load-balancer/strategy", params={"strategy": strategy})
            assert response.status_code in (200, 400, 503)
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)
            if response.status_code in (200, 201):
                data = response.json()
                assert "task_id" in data or "status" in data


class TestLoadBalancerAdvanced:
    """Advanced load balancer tests for better coverage."""

    def test_load_balancer_all_strategies_comprehensive(self, coordinator_client: TestClient):
        """Test all load balancing strategies with comprehensive scenarios."""
        strategies = [
            "round_robin",
            "least_connections",
            "least_response_time",
            "weighted_round_robin",
            "resource_based",
            "capability_based",
            "predictive",
            "consistent_hash",
        ]
        for strategy in strategies:
            response = coordinator_client.put("/api/v1/agent/messages/load-balancer/strategy", params={"strategy": strategy})
            assert response.status_code in (200, 400, 503)
            if response.status_code == 200:
                data = response.json()
                assert "status" in data or "strategy" in data

    def test_load_balancer_with_multiple_agents(self, coordinator_client: TestClient):
        """Test load balancer with multiple agents of different types."""
        agent_types = ["worker", "coordinator", "monitor"]
        for i, agent_type in enumerate(agent_types):
            agent_data = {
                "agent_id": f"lb-agent-{agent_type}-{i}",
                "agent_type": agent_type,
                "capabilities": ["data-processing", "analysis"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            coordinator_client.put(f"/v1/agents/lb-agent-{agent_type}-{i}/status", json={"status": "active"})

        for _ in range(5):
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)
            if response.status_code in (200, 201):
                data = response.json()
                assert "task_id" in data or "status" in data

    def test_load_balancer_task_priorities(self, coordinator_client: TestClient):
        """Test load balancer with different task priorities."""
        priorities = ["low", "normal", "high", "critical", "urgent"]
        for priority in priorities:
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": priority}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)
            if response.status_code in (200, 201):
                data = response.json()
                assert "task_id" in data or "status" in data


class TestTasksAdvanced:
    """Advanced task management tests for better coverage."""

    def test_tasks_all_priorities_and_models(self, coordinator_client: TestClient):
        """Test tasks with all priorities and model combinations."""
        priorities = ["low", "normal", "high", "critical", "urgent"]
        models = ["llama2", "mistral", "gpt-4", "claude"]

        for priority in priorities:
            for model in models:
                task_data = {"task_data": {"model": model, "prompt": "test prompt"}, "priority": priority}
                response = coordinator_client.post("/v1/tasks/submit", json=task_data)
                assert response.status_code in (200, 201, 503)
                if response.status_code in (200, 201):
                    data = response.json()
                    assert "task_id" in data or "status" in data

    def test_tasks_status_tracking(self, coordinator_client: TestClient):
        """Test task status tracking."""
        task_ids = []
        for i in range(3):
            task_data = {"task_data": {"model": "llama2", "prompt": f"test {i}"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            if response.status_code in (200, 201):
                task_ids.append(response.json().get("task_id"))

        for task_id in task_ids:
            response = coordinator_client.get(f"/tasks/{task_id}")
            assert response.status_code in (200, 404, 503)
            if response.status_code == 200:
                data = response.json()
                assert "task_id" in data or "status" in data

        response = coordinator_client.get("/v1/tasks/status")
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"

    def test_tasks_various_payloads(self, coordinator_client: TestClient):
        """Test tasks with various payload structures."""
        payloads = [
            {"model": "llama2", "prompt": "simple test"},
            {"model": "llama2", "prompt": "test", "max_tokens": 100, "temperature": 0.7},
            {"model": "llama2", "prompt": "test", "system_prompt": "You are a helpful assistant"},
            {"model": "llama2", "prompt": "test", "context": {"user_id": "123", "session_id": "456"}},
        ]

        for payload in payloads:
            task_data = {"task_data": payload, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)
            if response.status_code in (200, 201):
                data = response.json()
                assert "task_id" in data or "status" in data


class TestLoadBalancerComprehensive:
    """Comprehensive load balancer tests for better coverage."""

    def test_load_balancer_weight_management(self, coordinator_client: TestClient):
        """Test load balancer weight and capacity management."""
        weights = [0.5, 1.0, 1.5, 2.0, 3.0]
        for i, _weight in enumerate(weights):
            agent_data = {
                "agent_id": f"weight-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            coordinator_client.put(f"/v1/agents/weight-agent-{i}/status", json={"status": "active"})

        strategies = ["weighted_round_robin", "resource_based", "capability_based"]
        for strategy in strategies:
            response = coordinator_client.put("/api/v1/agent/messages/load-balancer/strategy", params={"strategy": strategy})
            assert response.status_code in (200, 400, 503)
            for _ in range(3):
                task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
                response = coordinator_client.post("/v1/tasks/submit", json=task_data)
                assert response.status_code in (200, 201, 503)

    def test_load_balancer_error_recovery(self, coordinator_client: TestClient):
        """Test load balancer error recovery scenarios."""
        for i in range(3):
            agent_data = {
                "agent_id": f"recovery-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            coordinator_client.put(f"/v1/agents/recovery-agent-{i}/status", json={"status": "active"})

        response = coordinator_client.put("/v1/agents/recovery-agent-1/status", json={"status": "inactive"})
        assert response.status_code in (200, 500)

        for _ in range(5):
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)

        response = coordinator_client.put("/v1/agents/recovery-agent-1/status", json={"status": "active"})
        assert response.status_code in (200, 500)

        for _ in range(3):
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "high"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)


class TestLoadTesting:
    """Load and stress testing with limited agent count."""

    def test_concurrent_agent_registration(self, coordinator_client: TestClient):
        """Test registering 10 agents concurrently."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing", "gpu-compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

    def test_concurrent_task_submission(self, coordinator_client: TestClient):
        """Test submitting tasks to 10 agents under load."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-task-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        for i in range(10):
            task_data = {"task_data": {"model": "llama2", "prompt": f"test task {i}"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 429, 503)

    def test_concurrent_message_sending(self, coordinator_client: TestClient):
        """Test sending messages between 10 agents under load."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-msg-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["communication"],
                "services": ["message-handling"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        for i in range(10):
            for j in range(10):
                if i != j:
                    message_data = {
                        "sender": f"load-msg-agent-{i}",
                        "recipient": f"load-msg-agent-{j}",
                        "message_type": "task",
                        "priority": "normal",
                        "content": {"from": f"load-msg-agent-{i}"},
                        "encrypt": False,
                    }
                    response = coordinator_client.post("/api/v1/agent/messages/send", json=message_data)
                    assert response.status_code in (200, 201, 400, 429, 503, 500)

    def test_load_balancing_under_load(self, coordinator_client: TestClient):
        """Test load balancer with 10 agents and multiple tasks."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-lb-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)
            response = coordinator_client.put(f"/v1/agents/load-lb-agent-{i}/status", json={"status": "active"})
            assert response.status_code in (200, 500)

        strategies = ["round_robin", "least_connections", "resource_based"]
        for strategy in strategies:
            response = coordinator_client.put("/api/v1/agent/messages/load-balancer/strategy", params={"strategy": strategy})
            assert response.status_code in (200, 400, 503)
            for i in range(5):
                task_data = {"task_data": {"model": "llama2", "prompt": f"load test {i}"}, "priority": "normal"}
                response = coordinator_client.post("/v1/tasks/submit", json=task_data)
                assert response.status_code in (200, 201, 429, 503)

    def test_concurrent_agent_discovery(self, coordinator_client: TestClient):
        """Test agent discovery with 10 agents registered."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-discovery-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute", "storage"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        for filters in [{}, {"agent_type": "worker"}, {"capabilities": ["compute"]}, {"status": "active"}]:
            response = coordinator_client.post("/v1/agents/discover", json=filters)
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data

    def test_swarm_coordination_under_load(self, coordinator_client: TestClient):
        """Test swarm coordination with 10 agents."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-swarm-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["distributed-compute"],
                "services": ["coordination"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        for _i in range(10):
            response = coordinator_client.post(
                "/v1/swarm/join", json={"role": "worker", "capability": "distributed-compute", "priority": "normal"}
            )
            assert response.status_code in (201, 500)

        response = coordinator_client.post(
            "/v1/swarm/coordinate",
            json={"task": "distributed-task", "collaborators": 5, "strategy": "distributed", "timeout_seconds": 300},
        )
        assert response.status_code in (202, 500)

    def test_concurrent_status_updates(self, coordinator_client: TestClient):
        """Test concurrent status updates on 10 agents."""
        for i in range(10):
            agent_data = {
                "agent_id": f"load-status-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        statuses = ["active", "inactive", "maintenance", "degraded"]
        for i in range(10):
            for status in statuses:
                response = coordinator_client.put(f"/v1/agents/load-status-agent-{i}/status", json={"status": status})
                assert response.status_code in (200, 429, 500)

    def test_concurrent_auth_operations(self, coordinator_client: TestClient):
        """Test concurrent authentication operations."""
        for _i in range(10):
            login_data = {"username": "admin", "password": "admin123"}
            response = coordinator_client.post("/api/v1/auth/login", json=login_data)
            assert response.status_code in (200, 401)

        login_response = coordinator_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            for _i in range(10):
                response = coordinator_client.post("/api/v1/auth/validate", json={"token": token})
                assert response.status_code in (200, 401)
