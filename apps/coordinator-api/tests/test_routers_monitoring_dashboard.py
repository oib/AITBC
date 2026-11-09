"""Router tests for /v1/monitoring/* (#1289 round 9 batch 4).

Enhanced-services dashboard. Health probes hit real service URLs -> all
unhealthy in tests; the contract under test is the honest degraded
shape (never 5xx, correct status taxonomy) plus the DB-backed /metrics.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/v1/monitoring"


class TestMonitoringDashboard:
    def test_dashboard_returns_degraded_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["overall_status"] in ("healthy", "degraded", "unhealthy", "error")
        assert body["summary"]["total_services"] == 6
        assert set(body["services"]) >= {"multimodal", "gpu_multimodal", "market_enhanced"}

    def test_summary_lists_all_services(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/dashboard/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["services"]) == 6
        for info in body["services"].values():
            assert {"name", "port", "status", "description", "icon"} <= set(info)

    def test_system_metrics_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/dashboard/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "system" in body or "error" in body
        if "system" in body:
            assert {"cpu_percent", "memory_percent", "disk_percent"} <= set(body["system"])

    def test_metrics_endpoint_db_backed(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["coordinator"]["status"] == "online"
        assert {"total", "completed", "pending", "failed"} <= set(body["jobs"])
        assert {"total", "online", "offline"} <= set(body["miners"])
