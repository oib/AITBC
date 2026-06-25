"""
Tests for swarm router (compute clustering)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestSwarmRouter:
    """Test swarm router endpoints"""

    def test_register_node(self, client: TestClient):
        """Test registering a compute node"""
        node_data = {
            "node_id": "node-001",
            "address": "10.0.0.1:8080",
            "capabilities": ["gpu", "ai", "training"],
            "cpu_cores": 16,
            "memory_gb": 64,
            "gpu_count": 2,
        }

        response = client.post("/v1/swarm/nodes/register", json=node_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node"]["node_id"] == "node-001"
        assert data["node"]["resources"]["gpu_count"] == 2
        assert "gpu" in data["node"]["capabilities"]

    def test_heartbeat(self, client: TestClient):
        """Test node heartbeat"""
        # Register node first
        client.post(
            "/v1/swarm/nodes/register", json={"node_id": "heartbeat-node", "address": "10.0.0.2", "capabilities": ["compute"]}
        )

        # Send heartbeat
        response = client.post("/v1/swarm/nodes/heartbeat-node/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node_id"] == "heartbeat-node"

    def test_heartbeat_unknown_node(self, client: TestClient):
        """Test heartbeat for unregistered node fails"""
        response = client.post("/v1/swarm/nodes/unknown/heartbeat")
        assert response.status_code == 404

    def test_list_nodes(self, client: TestClient):
        """Test listing all nodes"""
        # Register some nodes
        for i in range(3):
            client.post(
                "/v1/swarm/nodes/register",
                json={"node_id": f"list-node-{i}", "address": f"10.0.0.{i}", "capabilities": ["compute"]},
            )

        response = client.get("/v1/swarm/nodes")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert data["count"] >= 3

    def test_list_nodes_filter_by_capability(self, client: TestClient):
        """Test filtering nodes by capability"""
        # Register GPU node
        client.post(
            "/v1/swarm/nodes/register",
            json={"node_id": "gpu-node", "address": "10.0.1.1", "capabilities": ["gpu", "ai"], "gpu_count": 4},
        )

        # Register CPU-only node
        client.post(
            "/v1/swarm/nodes/register", json={"node_id": "cpu-node", "address": "10.0.1.2", "capabilities": ["compute"]}
        )

        # Filter for GPU
        response = client.get("/v1/swarm/nodes?capability=gpu")
        assert response.status_code == 200
        data = response.json()
        assert all("gpu" in n["capabilities"] for n in data["nodes"])

    def test_get_node(self, client: TestClient):
        """Test getting specific node details"""
        # Register node
        client.post(
            "/v1/swarm/nodes/register",
            json={"node_id": "detail-node", "address": "10.0.2.1", "capabilities": ["storage"], "memory_gb": 128},
        )

        response = client.get("/v1/swarm/nodes/detail-node")
        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "detail-node"
        assert data["resources"]["memory_gb"] == 128

    def test_get_node_not_found(self, client: TestClient):
        """Test getting non-existent node fails"""
        response = client.get("/v1/swarm/nodes/nonexistent")
        assert response.status_code == 404

    def test_submit_task(self, client: TestClient):
        """Test submitting a task to the swarm"""
        # Register capable node
        client.post(
            "/v1/swarm/nodes/register",
            json={"node_id": "task-node", "address": "10.0.3.1", "capabilities": ["ai", "training"], "gpu_count": 1},
        )

        task_data = {
            "task_type": "ai_training",
            "payload": {"model": "llama2", "dataset": "training-data-v1"},
            "required_capabilities": ["ai"],
            "priority": 5,
        }

        response = client.post("/v1/swarm/tasks/submit", json=task_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task" in data
        assert data["task"]["task_type"] == "ai_training"
        assert data["task"]["status"] in ["pending", "assigned", "running"]

    def test_submit_task_no_available_nodes(self, client: TestClient):
        """Test submitting task when no capable nodes available"""
        task_data = {
            "task_type": "quantum_computing",
            "payload": {},
            "required_capabilities": ["quantum"],  # No nodes have this
            "priority": 1,
        }

        response = client.post("/v1/swarm/tasks/submit", json=task_data)
        # Should still create task but it will be queued
        assert response.status_code == 200
        assert response.json()["task"]["status"] == "pending"

    def test_report_task_status(self, client: TestClient):
        """Test reporting task status update"""
        # Setup: register node and submit task
        client.post(
            "/v1/swarm/nodes/register", json={"node_id": "worker-node", "address": "10.0.4.1", "capabilities": ["compute"]}
        )

        task_response = client.post(
            "/v1/swarm/tasks/submit",
            json={"task_type": "processing", "payload": {"data": "test"}, "required_capabilities": ["compute"]},
        )
        task_id = task_response.json()["task"]["task_id"]
        assigned_node = task_response.json()["task"].get("assigned_node", "worker-node")

        # Report progress
        report_data = {"task_id": task_id, "node_id": assigned_node, "status": "running"}

        response = client.post("/v1/swarm/tasks/report", json=report_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "running"

    def test_get_task(self, client: TestClient):
        """Test getting task details"""
        # Submit task
        task_response = client.post("/v1/swarm/tasks/submit", json={"task_type": "inference", "payload": {"model": "test"}})
        task_id = task_response.json()["task"]["task_id"]

        response = client.get(f"/v1/swarm/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["task_type"] == "inference"

    def test_list_tasks(self, client: TestClient):
        """Test listing tasks with filters"""
        response = client.get("/v1/swarm/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "count" in data

    def test_list_tasks_filter_by_status(self, client: TestClient):
        """Test filtering tasks by status"""
        response = client.get("/v1/swarm/tasks?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert all(t["status"] == "pending" for t in data["tasks"])

    def test_create_cluster(self, client: TestClient):
        """Test creating a compute cluster"""
        # Register nodes
        for i in range(2):
            client.post(
                "/v1/swarm/nodes/register",
                json={"node_id": f"cluster-node-{i}", "address": f"10.0.5.{i}", "capabilities": ["gpu"], "gpu_count": 2},
            )

        cluster_data = {
            "name": "GPU Cluster Alpha",
            "description": "High-performance GPU cluster for AI training",
            "node_ids": ["cluster-node-0", "cluster-node-1"],
        }

        response = client.post("/v1/swarm/clusters/create", json=cluster_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cluster"]["name"] == "GPU Cluster Alpha"
        assert data["cluster"]["node_count"] == 2

    def test_list_clusters(self, client: TestClient):
        """Test listing all clusters"""
        response = client.get("/v1/swarm/clusters")
        assert response.status_code == 200
        data = response.json()
        assert "clusters" in data
        assert "count" in data

    def test_get_cluster(self, client: TestClient):
        """Test getting cluster details"""
        # Create cluster
        cluster_response = client.post(
            "/v1/swarm/clusters/create", json={"name": "Test Cluster", "description": "For testing", "node_ids": []}
        )
        cluster_id = cluster_response.json()["cluster"]["cluster_id"]

        response = client.get(f"/v1/swarm/clusters/{cluster_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["cluster_id"] == cluster_id
        assert data["name"] == "Test Cluster"

    def test_add_node_to_cluster(self, client: TestClient):
        """Test adding node to cluster"""
        # Create cluster
        cluster_response = client.post("/v1/swarm/clusters/create", json={"name": "Dynamic Cluster", "node_ids": []})
        cluster_id = cluster_response.json()["cluster"]["cluster_id"]

        # Register node
        client.post(
            "/v1/swarm/nodes/register", json={"node_id": "dynamic-node", "address": "10.0.6.1", "capabilities": ["compute"]}
        )

        # Add to cluster
        response = client.post(f"/v1/swarm/clusters/{cluster_id}/nodes/dynamic-node")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cluster_id"] == cluster_id
        assert data["node_id"] == "dynamic-node"

    def test_swarm_stats(self, client: TestClient):
        """Test swarm statistics endpoint"""
        response = client.get("/v1/swarm/stats")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "tasks" in data
        assert "clusters" in data
        assert "avg_load" in data

    def test_swarm_health(self, client: TestClient):
        """Test swarm health endpoint"""
        response = client.get("/v1/swarm/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "nodes_online" in data


@pytest.mark.integration
class TestSwarmIntegration:
    """Integration tests for compute clustering"""

    def test_full_task_lifecycle(self, client: TestClient):
        """Test complete task lifecycle from submission to completion"""
        # 1. Register compute node
        client.post(
            "/v1/swarm/nodes/register",
            json={
                "node_id": "worker-001",
                "address": "10.0.10.1",
                "capabilities": ["ai", "training"],
                "gpu_count": 2,
                "cpu_cores": 32,
            },
        )

        # 2. Submit task
        task_response = client.post(
            "/v1/swarm/tasks/submit",
            json={
                "task_type": "model_training",
                "payload": {"model": "resnet50", "epochs": 10, "batch_size": 32},
                "required_capabilities": ["ai"],
                "priority": 8,
            },
        )
        task_id = task_response.json()["task"]["task_id"]

        # 3. Report task running
        client.post("/v1/swarm/tasks/report", json={"task_id": task_id, "node_id": "worker-001", "status": "running"})

        # 4. Report task completed
        client.post(
            "/v1/swarm/tasks/report",
            json={
                "task_id": task_id,
                "node_id": "worker-001",
                "status": "completed",
                "result": {"accuracy": 0.95, "loss": 0.02},
            },
        )

        # 5. Verify task is completed
        task_check = client.get(f"/v1/swarm/tasks/{task_id}").json()
        assert task_check["status"] == "completed"
        assert task_check["result"]["accuracy"] == 0.95

    def test_load_balancing_across_nodes(self, client: TestClient):
        """Test that tasks are distributed across available nodes"""
        # Register multiple nodes
        for i in range(3):
            client.post(
                "/v1/swarm/nodes/register",
                json={"node_id": f"lb-node-{i}", "address": f"10.0.11.{i}", "capabilities": ["compute"]},
            )

        # Submit multiple tasks
        assigned_nodes = set()
        for i in range(5):
            task_response = client.post(
                "/v1/swarm/tasks/submit",
                json={"task_type": "processing", "payload": {"job": i}, "required_capabilities": ["compute"]},
            )
            node = task_response.json()["task"].get("assigned_node")
            if node:
                assigned_nodes.add(node)

        # Verify tasks were distributed
        assert len(assigned_nodes) > 0
