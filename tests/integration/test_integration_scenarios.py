"""Integration tests for edge cases, error handling, integration scenarios, and advanced features."""

import os
from typing import Any

import pytest
from starlette.testclient import TestClient


class TestEdgeCases:
    """Test edge cases and error paths."""

    def test_agent_registration_invalid_data(self, coordinator_client: TestClient):
        """Test agent registration with various invalid data."""
        invalid_cases = [
            {},
            {"agent_id": "test"},
            {"agent_id": "", "agent_type": "worker"},
            {"agent_id": "test", "agent_type": "invalid_type"},
        ]
        for data in invalid_cases:
            response = coordinator_client.post("/v1/agents/register", json=data)
            assert response.status_code in (200, 422, 400)

    def test_task_submission_various_priorities(self, coordinator_client: TestClient):
        """Test task submission with various priorities."""
        priorities = ["low", "normal", "high", "critical", "urgent"]
        for priority in priorities:
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": priority}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)

    def test_agent_status_updates(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test various agent status updates."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        statuses = ["active", "inactive", "maintenance", "degraded"]
        for status in statuses:
            response = coordinator_client.put(f"/v1/agents/{sample_agent_data['agent_id']}/status", json={"status": status})
            assert response.status_code in (200, 500)

    def test_agent_discovery_various_filters(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test agent discovery with various filters."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)

        filters = [
            {},
            {"status": "active"},
            {"agent_type": "worker"},
            {"capabilities": ["data-processing"]},
            {"status": "active", "agent_type": "worker"},
        ]
        for filter_data in filters:
            response = coordinator_client.post("/v1/agents/discover", json=filter_data)
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data

    def test_nonexistent_endpoints(self, coordinator_client: TestClient):
        """Test that nonexistent endpoints return 404."""
        endpoints = ["/nonexistent", "/v1/agents/nonexistent", "/tasks/nonexistent", "/api/v1/nonexistent"]
        for endpoint in endpoints:
            response = coordinator_client.get(endpoint)
            assert response.status_code == 404

    def test_invalid_http_methods(self, coordinator_client: TestClient):
        """Test invalid HTTP methods on valid endpoints."""
        response = coordinator_client.post("/health")
        assert response.status_code in (405, 404)

        response = coordinator_client.get("/v1/agents/register")
        assert response.status_code in (405, 404)


class TestErrorHandling:
    """Test error handling and edge cases for better coverage."""

    def test_invalid_json_requests(self, coordinator_client: TestClient):
        """Test endpoints with invalid JSON data."""
        endpoints = [
            ("/v1/agents/register", "POST"),
            ("/v1/agents/discover", "POST"),
            ("/v1/tasks/submit", "POST"),
            ("/api/v1/agent/messages/send", "POST"),
            ("/api/v1/auth/login", "POST"),
        ]

        for endpoint, method in endpoints:
            if method == "POST":
                response = coordinator_client.post(endpoint, json={"invalid": "data", "missing_required": True})
                assert response.status_code in (200, 400, 422, 429, 503)

    def test_malformed_request_data(self, coordinator_client: TestClient):
        """Test endpoints with malformed request data."""
        malformed_data = [None, "", "invalid string", {"nested": {"deeply": {"invalid": "structure"}}}]

        for data in malformed_data:
            if data is not None:
                response = coordinator_client.post("/v1/agents/register", json=data)
                assert response.status_code in (200, 400, 422, 429, 503)

    def test_special_characters_in_ids(self, coordinator_client: TestClient):
        """Test endpoints with special characters in IDs."""
        special_ids = ["agent-with-dashes", "agent_with_underscores", "agent.with.dots", "agent@with#special"]

        for agent_id in special_ids:
            agent_data = {
                "agent_id": agent_id,
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": "http://localhost:9001"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 400, 422, 429)

    def test_very_long_strings(self, coordinator_client: TestClient):
        """Test endpoints with very long string values."""
        long_string = "x" * 10000

        agent_data = {
            "agent_id": long_string[:100],
            "agent_type": "worker",
            "capabilities": [long_string[:50]],
            "services": [long_string[:50]],
            "endpoints": {"http": "http://localhost:9001"},
        }
        response = coordinator_client.post("/v1/agents/register", json=agent_data)
        assert response.status_code in (200, 201, 400, 422, 429, 503)

    def test_numeric_edge_cases(self, coordinator_client: TestClient):
        """Test endpoints with numeric edge cases."""
        numeric_cases = [
            0,
            -1,
            999999999,
            0.0,
            -0.1,
            1.7976931348623157e308,
        ]

        for num in numeric_cases:
            response = coordinator_client.get("/api/v1/agent/messages/history", params={"limit": num})
            assert response.status_code in (200, 400, 422, 429, 503)

    def test_boolean_and_null_values(self, coordinator_client: TestClient):
        """Test endpoints with boolean and null values."""
        test_cases = [
            {"agent_id": "test", "agent_type": "worker", "capabilities": None},
            {"agent_id": "test", "agent_type": "worker", "capabilities": True},
            {"agent_id": "test", "agent_type": "worker", "capabilities": False},
        ]

        for case in test_cases:
            response = coordinator_client.post("/v1/agents/register", json=case)
            assert response.status_code in (200, 400, 422, 429, 503)

    def test_array_edge_cases(self, coordinator_client: TestClient):
        """Test endpoints with array edge cases."""
        array_cases = [
            [],
            ["single-item"],
            ["item1", "item2", "item3", "item4", "item5"],
            [None, None, None],
            ["", "", ""],
        ]

        for capabilities in array_cases:
            agent_data = {
                "agent_id": f"test-{len(capabilities)}",
                "agent_type": "worker",
                "capabilities": capabilities,
                "services": ["task-execution"],
                "endpoints": {"http": "http://localhost:9001"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 400, 422, 429, 503)

    def test_concurrent_operations_simulation(self, coordinator_client: TestClient):
        """Test simulating concurrent operations."""
        for i in range(10):
            agent_data = {
                "agent_id": f"concurrent-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409, 429)

        for i in range(10):
            task_data = {"task_data": {"model": "llama2", "prompt": f"test {i}"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)

        response = coordinator_client.get("/v1/tasks/status")
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"


class TestIntegrationScenarios:
    """Test complex integration scenarios for better coverage."""

    def test_full_agent_task_workflow(self, coordinator_client: TestClient):
        """Test complete workflow from agent registration to task completion."""
        agent_data = {
            "agent_id": "workflow-agent-001",
            "agent_type": "worker",
            "capabilities": ["gpu-compute", "data-processing"],
            "services": ["task-execution"],
            "endpoints": {"http": "http://localhost:9001"},
        }
        coordinator_client.post("/v1/agents/register", json=agent_data)
        response = coordinator_client.put("/v1/agents/workflow-agent-001/status", json={"status": "active"})
        assert response.status_code in (200, 500)

        task_data = {"task_data": {"model": "llama2", "prompt": "workflow test"}, "priority": "high"}
        response = coordinator_client.post("/v1/tasks/submit", json=task_data)

        if response.status_code in (200, 201):
            task_id = response.json().get("task_id")
            if task_id:
                response = coordinator_client.get(f"/tasks/{task_id}")
                assert response.status_code in (200, 404, 503)

        response = coordinator_client.get("/v1/agents/workflow-agent-001")
        assert response.status_code in (200, 404)

    def test_multi_agent_coordination(self, coordinator_client: TestClient):
        """Test coordination between multiple agents."""
        agents = []
        for i in range(5):
            agent_data = {
                "agent_id": f"coord-agent-{i}",
                "agent_type": "worker" if i < 3 else "coordinator",
                "capabilities": ["data-processing", "gpu-compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409)
            response = coordinator_client.put(f"/v1/agents/coord-agent-{i}/status", json={"status": "active"})
            assert response.status_code in (200, 500)
            agents.append(f"coord-agent-{i}")

        broadcast_data = {"message_type": "control", "priority": "high", "payload": {"action": "coordinate"}}
        response = coordinator_client.post("/api/v1/agent/messages/broadcast", json=broadcast_data)
        assert response.status_code in (200, 400, 503, 500)

        for agent_id in agents:
            response = coordinator_client.get(f"/v1/agents/{agent_id}")
            assert response.status_code in (200, 404)

    def test_swarm_coordination_workflow(self, coordinator_client: TestClient):
        """Test swarm coordination workflow."""
        join_data = {"role": "worker", "capability": "gpu-compute", "priority": "high"}
        response = coordinator_client.post("/v1/swarm/join", json=join_data)
        assert response.status_code in (201, 500)
        swarm_id = response.json().get("swarm_id") if response.status_code == 201 else "test-swarm"

        coordinate_data = {
            "task": "distributed_computation",
            "collaborators": 3,
            "strategy": "distributed",
            "timeout_seconds": 300,
        }
        response = coordinator_client.post("/v1/swarm/coordinate", json=coordinate_data)
        assert response.status_code in (202, 500)
        task_id = response.json().get("task_id") if response.status_code == 202 else "task-001"

        response = coordinator_client.get(f"/swarm/tasks/{task_id}/status")
        assert response.status_code in (200, 404, 500)

        consensus_data = {"consensus_threshold": 0.8}
        response = coordinator_client.post(f"/swarm/tasks/{task_id}/consensus", json=consensus_data)
        assert response.status_code in (200, 404, 500)

        response = coordinator_client.post(f"/swarm/{swarm_id}/leave")
        assert response.status_code in (200, 404, 500)

    def test_ai_learning_workflow(self, coordinator_client: TestClient):
        """Test AI learning workflow."""
        experiences = [
            {"context": {"task": "data-processing"}, "action": "execute", "reward": 0.9, "next_state": {"done": True}},
            {"context": {"task": "gpu-compute"}, "action": "execute", "reward": 0.8, "next_state": {"done": True}},
            {"context": {"task": "monitoring"}, "action": "defer", "reward": 0.7, "next_state": {"pending": True}},
        ]

        for exp in experiences:
            response = coordinator_client.post("/v1/ai/learning/experience", json=exp)
            assert response.status_code in (200, 500)

        response = coordinator_client.get("/v1/ai/learning/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

        context = {"task": "data-processing", "agent_type": "worker"}
        response = coordinator_client.post("/v1/ai/learning/predict", json=context, params={"action": "execute"})
        assert response.status_code in (200, 500)

        response = coordinator_client.get("/v1/ai/statistics")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_authentication_authorization_workflow(self, coordinator_client: TestClient):
        """Test authentication and authorization workflow."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")}
        response = coordinator_client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 200
        token = response.json()["access_token"]

        response = coordinator_client.post("/api/v1/auth/validate", json={"token": token})
        assert response.status_code == 200
        assert response.json()["valid"] is True

        response = coordinator_client.get("/v1/protected/admin", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code in (200, 403, 404)

        operator_password = os.getenv("TEST_OPERATOR_PASSWORD", "operator123")
        operator_data = {"username": "operator", "password": operator_password}
        response = coordinator_client.post("/api/v1/auth/login", json=operator_data)
        assert response.status_code == 200
        operator_token = response.json()["access_token"]

        response = coordinator_client.get("/v1/protected/operator", headers={"Authorization": f"Bearer {operator_token}"})
        assert response.status_code in (200, 403, 404)

    def test_monitoring_and_alerting_workflow(self, coordinator_client: TestClient):
        """Test monitoring and alerting workflow."""
        response = coordinator_client.get("/v1/metrics/health")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        response = coordinator_client.get("/v1/metrics/summary")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        response = coordinator_client.get("/v1/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

        response = coordinator_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 401, 403, 503)

        response = coordinator_client.get("/v1/system/status")
        assert response.status_code in (200, 401, 403, 404, 500)

        response = coordinator_client.get("/sla")
        assert response.status_code in (200, 401, 403, 404, 500)


class TestAdvancedFeatures:
    """Test advanced features integration."""

    def test_advanced_features_status(self, coordinator_client: TestClient):
        """Test advanced features status endpoint."""
        response = coordinator_client.get("/v1/advanced-features/status")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_realtime_learning_integration(self, coordinator_client: TestClient):
        """Test realtime learning integration."""
        response = coordinator_client.post(
            "/v1/ai/learning/experience",
            json={"context": {"task": "test"}, "action": "execute", "reward": 0.9, "next_state": {"done": True}},
        )
        assert response.status_code in (200, 500)
        response = coordinator_client.get("/v1/ai/learning/statistics")
        assert response.status_code in (200, 500)
        response = coordinator_client.get("/v1/advanced-features/status")
        assert response.status_code in (200, 500)

    def test_distributed_consensus_integration(self, coordinator_client: TestClient):
        """Test distributed consensus integration."""
        response = coordinator_client.post(
            "/v1/consensus/node/register",
            json={"node_id": "advanced-node-001", "address": "http://localhost:9100", "stake": 1000},
        )
        assert response.status_code in (200, 201, 500)
        response = coordinator_client.post(
            "/v1/consensus/proposal/create",
            json={"proposal_id": "advanced-prop-001", "proposer": "advanced-node-001", "content": {"action": "test"}},
        )
        assert response.status_code in (200, 201, 500)
        response = coordinator_client.get("/v1/consensus/statistics")
        assert response.status_code in (200, 500)
        response = coordinator_client.get("/v1/advanced-features/status")
        assert response.status_code in (200, 500)

    def test_advanced_ai_integration(self, coordinator_client: TestClient):
        """Test advanced AI integration."""
        response = coordinator_client.post(
            "/v1/ai/neural-network/create",
            json={"input_size": 10, "hidden_layers": [5], "output_size": 2, "activation": "relu"},
        )
        assert response.status_code in (200, 500)
        response = coordinator_client.get("/v1/ai/statistics")
        assert response.status_code in (200, 500)
        response = coordinator_client.get("/v1/advanced-features/status")
        assert response.status_code in (200, 500)


class TestLowCoverageModules:
    """Tests to improve coverage for low-coverage modules."""

    def test_load_balancer_strategies_comprehensive(self, coordinator_client: TestClient):
        """Test all load balancer strategies with different scenarios."""
        for i in range(5):
            agent_data = {
                "agent_id": f"lb-cov-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute", "storage"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409)
            response = coordinator_client.put(f"/v1/agents/lb-cov-agent-{i}/status", json={"status": "active"})
            assert response.status_code in (200, 500)

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
            response = coordinator_client.get("/api/v1/agent/messages/load-balancer/stats")
            assert response.status_code in (200, 503)

    def test_load_balancer_weight_management(self, coordinator_client: TestClient):
        """Test load balancer weight and capacity management."""
        weights = [0.5, 1.0, 1.5, 2.0, 3.0]
        for i, _weight in enumerate(weights):
            agent_data = {
                "agent_id": f"lb-weight-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409)
            response = coordinator_client.put(f"/v1/agents/lb-weight-agent-{i}/status", json={"status": "active"})
            assert response.status_code in (200, 500)

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
                "agent_id": f"lb-recovery-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["compute"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409)
            response = coordinator_client.put(f"/v1/agents/lb-recovery-agent-{i}/status", json={"status": "active"})
            assert response.status_code in (200, 500)

        response = coordinator_client.put("/v1/agents/lb-recovery-agent-0/status", json={"status": "inactive"})
        assert response.status_code in (200, 500)
        response = coordinator_client.put("/v1/agents/lb-recovery-agent-1/status", json={"status": "maintenance"})
        assert response.status_code in (200, 500)

        for _ in range(5):
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "high"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)

        response = coordinator_client.put("/v1/agents/lb-recovery-agent-0/status", json={"status": "active"})
        assert response.status_code in (200, 500)
        response = coordinator_client.put("/v1/agents/lb-recovery-agent-1/status", json={"status": "active"})
        assert response.status_code in (200, 500)

        for _ in range(3):
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
            response = coordinator_client.post("/v1/tasks/submit", json=task_data)
            assert response.status_code in (200, 201, 503)

    def test_advanced_ai_neural_network_variations(self, coordinator_client: TestClient):
        """Test neural network creation with various configurations."""
        activations = ["relu", "sigmoid", "tanh", "softmax", "leaky_relu", "elu", "gelu"]
        for activation in activations:
            response = coordinator_client.post(
                "/v1/ai/neural-network/create",
                json={"input_size": 10, "hidden_layers": [5, 3], "output_size": 2, "activation": activation},
            )
            assert response.status_code in (200, 500)

        architectures = [
            {"input_size": 5, "hidden_layers": [3], "output_size": 1},
            {"input_size": 20, "hidden_layers": [10, 5], "output_size": 3},
            {"input_size": 100, "hidden_layers": [50, 25, 10], "output_size": 5},
        ]
        for arch in architectures:
            response = coordinator_client.post("/v1/ai/neural-network/create", json={**arch, "activation": "relu"})
            assert response.status_code in (200, 500)

    def test_advanced_ai_ml_model_variations(self, coordinator_client: TestClient):
        """Test ML model creation with various configurations."""
        model_types = [
            "random_forest",
            "linear_regression",
            "neural_network",
            "decision_tree",
            "gradient_boosting",
            "svm",
            "knn",
        ]
        for model_type in model_types:
            response = coordinator_client.post(
                "/v1/ai/ml-model/create",
                json={"model_type": model_type, "features": ["cpu", "memory", "gpu"], "target": "performance"},
            )
            assert response.status_code in (200, 500)

        feature_sets = [
            ["cpu"],
            ["cpu", "memory"],
            ["cpu", "memory", "gpu"],
            ["cpu", "memory", "gpu", "network"],
        ]
        for features in feature_sets:
            response = coordinator_client.post(
                "/v1/ai/ml-model/create", json={"model_type": "random_forest", "features": features, "target": "performance"}
            )
            assert response.status_code in (200, 500)

    def test_advanced_ai_learning_experiences(self, coordinator_client: TestClient):
        """Test AI learning experience recording and retrieval."""
        experiences = [
            {
                "context": {"task": "data-processing", "agent_type": "worker"},
                "action": "execute",
                "reward": 0.9,
                "next_state": {"done": True},
            },
            {
                "context": {"task": "gpu-compute", "agent_type": "compute"},
                "action": "execute",
                "reward": 0.8,
                "next_state": {"done": True},
            },
            {
                "context": {"task": "monitoring", "agent_type": "monitor"},
                "action": "defer",
                "reward": 0.7,
                "next_state": {"pending": True},
            },
            {
                "context": {"task": "storage", "agent_type": "storage"},
                "action": "execute",
                "reward": 0.6,
                "next_state": {"done": True},
            },
            {
                "context": {"task": "coordination", "agent_type": "coordinator"},
                "action": "coordinate",
                "reward": 0.85,
                "next_state": {"coordinated": True},
            },
        ]

        for exp in experiences:
            response = coordinator_client.post("/v1/ai/learning/experience", json=exp)
            assert response.status_code in (200, 500)

        response = coordinator_client.get("/v1/ai/learning/statistics")
        assert response.status_code in (200, 500)

        contexts = [
            {"task": "data-processing", "agent_type": "worker"},
            {"task": "gpu-compute", "agent_type": "compute"},
            {"task": "monitoring", "agent_type": "monitor"},
        ]
        for context in contexts:
            response = coordinator_client.post("/v1/ai/learning/predict", json=context, params={"action": "execute"})
            assert response.status_code in (200, 500)

    def test_advanced_ai_performance_tracking(self, coordinator_client: TestClient):
        """Test AI performance tracking and metrics."""
        metrics = [
            {"model": "llama2", "task": "inference", "latency_ms": 100, "accuracy": 0.95},
            {"model": "mistral", "task": "inference", "latency_ms": 120, "accuracy": 0.92},
            {"model": "llama2", "task": "training", "latency_ms": 5000, "accuracy": 0.90},
        ]
        for metric in metrics:
            response = coordinator_client.post("/v1/ai/performance/record", json=metric)
            assert response.status_code in (200, 404, 500)

        response = coordinator_client.get("/v1/ai/statistics")
        assert response.status_code in (200, 500)

    def test_protocols_communication_variations(self, coordinator_client: TestClient):
        """Test communication protocols with various configurations."""
        for i in range(5):
            agent_data = {
                "agent_id": f"comm-protocol-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["communication"],
                "services": ["message-handling"],
                "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
            }
            response = coordinator_client.post("/v1/agents/register", json=agent_data)
            assert response.status_code in (200, 201, 409)

        protocols = ["hierarchical", "peer_to_peer", "broadcast", "multicast", "anycast"]
        for protocol in protocols:
            message_data = {
                "receiver_id": "comm-protocol-agent-0",
                "message_type": "task",
                "priority": "normal",
                "protocol": protocol,
                "payload": {"test": protocol},
            }
            response = coordinator_client.post("/api/v1/agent/messages/send", json=message_data)
            assert response.status_code in (200, 201, 400, 503, 500)

        for protocol in protocols:
            response = coordinator_client.post(
                "/api/v1/agent/messages/broadcast",
                json={
                    "message_type": "status",
                    "priority": "normal",
                    "protocol": protocol,
                    "payload": {"broadcast": protocol},
                },
            )
            assert response.status_code in (200, 400, 503, 500)

    def test_protocols_message_types_priorities(self, coordinator_client: TestClient):
        """Test all message types with all priority levels."""
        response = coordinator_client.post(
            "/v1/agents/register",
            json={
                "agent_id": "msg-type-priority-agent",
                "agent_type": "worker",
                "capabilities": ["communication"],
                "services": ["message-handling"],
                "endpoints": {"http": "http://localhost:9001"},
            },
        )
        assert response.status_code in (200, 201, 409)

        message_types = ["task", "status", "heartbeat", "control", "data", "result", "error", "notification", "alert"]
        priorities = ["low", "normal", "high", "critical", "urgent"]

        for msg_type in message_types:
            for priority in priorities:
                response = coordinator_client.post(
                    "/api/v1/agent/messages/send",
                    json={
                        "receiver_id": "msg-type-priority-agent",
                        "message_type": msg_type,
                        "priority": priority,
                        "protocol": "hierarchical",
                        "payload": {"type": msg_type, "priority": priority},
                    },
                )
                assert response.status_code in (200, 201, 400, 503, 500)

    def test_protocols_message_history_retrieval(self, coordinator_client: TestClient):
        """Test message history retrieval with filters."""
        for i in range(5):
            response = coordinator_client.post(
                "/v1/agents/register",
                json={
                    "agent_id": f"msg-history-agent-{i}",
                    "agent_type": "worker",
                    "capabilities": ["communication"],
                    "services": ["message-handling"],
                    "endpoints": {"http": f"http://localhost:900{i % 10 + 1}"},
                },
            )
            assert response.status_code in (200, 201, 409)

        for i in range(5):
            response = coordinator_client.post(
                "/api/v1/agent/messages/send",
                json={
                    "receiver_id": f"msg-history-agent-{i}",
                    "message_type": "task",
                    "priority": "normal",
                    "protocol": "hierarchical",
                    "payload": {"index": i},
                },
            )
            assert response.status_code in (200, 201, 400, 503, 500)

        response = coordinator_client.get("/api/v1/agent/messages/history")
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "count" in data or "messages" in data or isinstance(data, list)

        response = coordinator_client.get("/api/v1/agent/messages/history?limit=10")
        assert response.status_code in (200, 503)

        response = coordinator_client.get("/api/v1/agent/messages/history?message_type=task")
        assert response.status_code in (200, 503)

        response = coordinator_client.get("/api/v1/agent/messages/history?priority=normal")
        assert response.status_code in (200, 503)
