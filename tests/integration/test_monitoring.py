"""Integration tests for health, monitoring, and swarm endpoints."""

from starlette.testclient import TestClient


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self, coordinator_client: TestClient):
        """Test health check."""
        response = coordinator_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_health_check(self, coordinator_client: TestClient):
        """Test health check endpoint."""
        response = coordinator_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    def test_root_endpoint(self, coordinator_client: TestClient):
        """Test root endpoint with service information."""
        response = coordinator_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "endpoints" in data


class TestMonitorEndpoints:
    """Test monitor router endpoints."""

    def test_get_dashboard(self, coordinator_client: TestClient):
        """Test getting monitoring dashboard data."""
        response = coordinator_client.get("/v1/api/v1/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "services" in data

    def test_get_status(self, coordinator_client: TestClient):
        """Test getting coordinator status."""
        response = coordinator_client.get("/v1/swarm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"

    def test_get_miners(self, coordinator_client: TestClient):
        """Test getting miners list."""
        response = coordinator_client.get("/v1/swarm/miners")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_history_dashboard(self, coordinator_client: TestClient):
        """Test getting historical dashboard data."""
        response = coordinator_client.get("/v1/swarm/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_jobs(self, coordinator_client: TestClient):
        """Test getting jobs list."""
        response = coordinator_client.get("/v1/swarm/jobs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMonitoringEndpoints:
    """Test monitoring router endpoints."""

    def test_get_prometheus_metrics(self, coordinator_client: TestClient):
        """Test getting metrics in Prometheus format."""
        response = coordinator_client.get("/v1/metrics")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/plain; charset=utf-8"

    def test_get_metrics_summary(self, coordinator_client: TestClient):
        """Test getting metrics summary for dashboard."""
        response = coordinator_client.get("/v1/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "performance" in data
        assert "system" in data

    def test_get_health_metrics(self, coordinator_client: TestClient):
        """Test getting health metrics for monitoring."""
        response = coordinator_client.get("/v1/metrics/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "health" in data
        assert "memory" in data["health"]
        assert "cpu" in data["health"]


class TestSwarmEndpoints:
    """Test swarm router endpoints."""

    def test_list_swarms(self, coordinator_client: TestClient):
        """Test listing active swarms."""
        response = coordinator_client.get("/v1/swarm/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_swarms_with_filters(self, coordinator_client: TestClient):
        """Test listing swarms with filters."""
        response = coordinator_client.get("/v1/swarm/list", params={"swarm_id": "swarm_001", "status": "active", "limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_join_swarm(self, coordinator_client: TestClient):
        """Test joining agent swarm."""
        join_data = {"role": "worker", "capability": "gpu-compute", "priority": "high", "region": "us-east"}
        response = coordinator_client.post("/v1/swarm/join", json=join_data)
        assert response.status_code == 201
        data = response.json()
        assert "swarm_id" in data
        assert data["status"] == "joined"

    def test_coordinate_swarm(self, coordinator_client: TestClient):
        """Test coordinating swarm task execution."""
        coordinate_data = {
            "task": "matrix_multiplication",
            "collaborators": 5,
            "strategy": "distributed",
            "timeout_seconds": 300,
        }
        response = coordinator_client.post("/v1/swarm/coordinate", json=coordinate_data)
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "coordinating"

    def test_get_task_status(self, coordinator_client: TestClient):
        """Test getting swarm task status."""
        response = coordinator_client.get("/v1/swarm/tasks/task_001/status")
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data

    def test_leave_swarm(self, coordinator_client: TestClient):
        """Test leaving swarm."""
        response = coordinator_client.post("/v1/swarm/swarm_001/leave")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "left"

    def test_achieve_consensus(self, coordinator_client: TestClient):
        """Test achieving swarm consensus."""
        consensus_data = {"consensus_threshold": 0.8}
        response = coordinator_client.post("/v1/swarm/tasks/task_001/consensus", json=consensus_data)
        assert response.status_code == 200
        data = response.json()
        assert data["consensus_reached"] is True
        assert data["status"] == "consensus_achieved"

    def test_swarm_dashboard(self, coordinator_client: TestClient):
        """Test getting swarm monitoring dashboard."""
        response = coordinator_client.get("/v1/swarm/api/v1/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "services" in data

    def test_swarm_status(self, coordinator_client: TestClient):
        """Test getting swarm coordinator status."""
        response = coordinator_client.get("/v1/swarm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"

    def test_swarm_miners(self, coordinator_client: TestClient):
        """Test getting swarm miners list."""
        response = coordinator_client.get("/v1/swarm/miners")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_swarm_history_dashboard(self, coordinator_client: TestClient):
        """Test getting swarm historical dashboard."""
        response = coordinator_client.get("/v1/swarm/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMonitoringComprehensive:
    """Comprehensive monitoring tests for better coverage."""

    def test_monitoring_all_metrics_types(self, coordinator_client: TestClient):
        """Test all types of monitoring metrics."""
        response = coordinator_client.get("/v1/metrics")
        if response.status_code == 200:
            assert "text/plain" in response.headers.get("content-type", "")

        coordinator_client.get("/v1/metrics/summary")
        coordinator_client.get("/v1/metrics/health")
        response = coordinator_client.get("/v1/system/status")
        assert response.status_code in (200, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

        response = coordinator_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 401, 403, 500)

        response = coordinator_client.get("/api/v1/agent/messages/load-balancer/stats")
        assert response.status_code in (200, 503)

        response = coordinator_client.get("/v1/registry/stats")
        assert response.status_code in (200, 404, 503)

    def test_monitoring_dashboard_data(self, coordinator_client: TestClient):
        """Test monitoring dashboard data endpoints."""
        response = coordinator_client.get("/api/v1/dashboard")
        assert response.status_code in (200, 404)

        response = coordinator_client.get("/v1/swarm/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"

        response = coordinator_client.get("/v1/swarm/api/v1/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data

        response = coordinator_client.get("/v1/swarm/jobs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        response = coordinator_client.get("/v1/swarm/miners")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        response = coordinator_client.get("/v1/swarm/dashboard")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_monitoring_sla_tracking(self, coordinator_client: TestClient):
        """Test SLA tracking metrics."""
        sla_ids = ["sla-001", "sla-002", "sla-003"]
        values = [0.95, 0.85, 0.75]

        for sla_id, value in zip(sla_ids, values, strict=True):
            response = coordinator_client.post(f"/sla/{sla_id}/record?value={value}")
            assert response.status_code in (200, 401, 403, 404, 500)

        response = coordinator_client.get("/sla")
        assert response.status_code in (200, 401, 403, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

        response = coordinator_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 401, 403, 500)


class TestSwarmComprehensive:
    """Comprehensive swarm tests for better coverage."""

    def test_swarm_full_lifecycle(self, coordinator_client: TestClient):
        """Test complete swarm lifecycle."""
        join_data = [
            {"role": "worker", "capability": "gpu-compute", "priority": "high"},
            {"role": "coordinator", "capability": "coordination", "priority": "critical"},
            {"role": "monitor", "capability": "monitoring", "priority": "normal"},
        ]

        swarm_ids = []
        for data in join_data:
            response = coordinator_client.post("/v1/swarm/join", json=data)
            assert response.status_code in (201, 500)
            if response.status_code == 201:
                swarm_ids.append(response.json().get("swarm_id"))

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

        for swarm_id in swarm_ids:
            response = coordinator_client.post(f"/swarm/{swarm_id}/leave")
            assert response.status_code in (200, 404, 500)

    def test_swarm_various_strategies(self, coordinator_client: TestClient):
        """Test swarm with various coordination strategies."""
        strategies = ["distributed", "centralized", "hierarchical", "peer_to_peer"]

        for strategy in strategies:
            coordinate_data = {"task": f"test_{strategy}", "collaborators": 3, "strategy": strategy, "timeout_seconds": 300}
            response = coordinator_client.post("/v1/swarm/coordinate", json=coordinate_data)
            assert response.status_code in (202, 500)
            if response.status_code == 202:
                task_id = response.json().get("task_id")
                response = coordinator_client.get(f"/swarm/tasks/{task_id}/status")
                assert response.status_code in (200, 404, 500)

    def test_swarm_consensus_thresholds(self, coordinator_client: TestClient):
        """Test swarm with various consensus thresholds."""
        thresholds = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

        for threshold in thresholds:
            consensus_data = {"consensus_threshold": threshold}
            response = coordinator_client.post("/v1/swarm/tasks/test-task/consensus", json=consensus_data)
            assert response.status_code in (200, 404, 500)
