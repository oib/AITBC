"""Router tests for /v1/monitoring/* (#1289 round 9 batch 4).

Core-services dashboard. Health probes hit real service URLs -> all
unhealthy in tests; the contract under test is the honest degraded
shape (never 5xx, correct status taxonomy) plus the DB-backed /metrics.
#2409: the retired "enhanced services" roster (multimodal, gpu_multimodal,
market_enhanced, ...) was replaced by the deployed core services — a
healthy fleet must not read unhealthy because of dead unit names.
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
        assert body["summary"]["total_services"] == 5
        # Retired enhanced services must not appear — they made a healthy
        # fleet read unhealthy (#2409).
        assert not {"multimodal", "gpu_multimodal", "market_enhanced"} & set(body["services"])
        assert {"market", "trading", "governance", "explorer", "pool_hub"} <= set(body["services"])

    def test_summary_lists_all_services(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/dashboard/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["services"]) == 5
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


class TestMonitoringMetricsJobBuckets:
    """#2409: every job state must land in a bucket — canceled/expired were
    silently dropped, so success_rate read unbucketed jobs as failures."""

    def test_all_job_states_are_bucketed(self, client: TestClient, db_session) -> None:
        from coordinator_api.contexts.infrastructure.domain.job import Job

        states = ["COMPLETED", "FAILED", "QUEUED", "ASSIGNED", "RUNNING", "CANCELED", "EXPIRED", "WEIRD_STATE"]
        for i, state in enumerate(states):
            db_session.add(
                Job(
                    id=f"job-{i}",
                    client_id="client1",
                    state=state,
                    payload={"prompt": "x"},
                    constraints={},
                )
            )
        db_session.commit()

        resp = client.get(f"{BASE}/metrics")
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert jobs["total"] == 8
        assert jobs["completed"] == 1
        assert jobs["failed"] == 1
        assert jobs["pending"] == 3
        assert jobs["canceled"] == 1
        assert jobs["expired"] == 1
        assert jobs["other"] == 1
        # Nothing falls through the cracks: buckets sum to total.
        assert (
            jobs["completed"] + jobs["failed"] + jobs["pending"] + jobs["canceled"] + jobs["expired"] + jobs["other"]
            == jobs["total"]
        )

    def test_miners_counted_in_sql(self, client: TestClient, db_session) -> None:
        """#2715: miner totals come from grouped SQL counts, not row loads."""
        from coordinator_api.contexts.infrastructure.domain.miner import Miner

        for i, status in enumerate(["ONLINE", "ONLINE", "OFFLINE"]):
            db_session.add(Miner(id=f"miner-{i}", status=status))
        db_session.commit()

        resp = client.get(f"{BASE}/metrics")
        assert resp.status_code == 200
        miners = resp.json()["miners"]
        assert miners["total"] == 3
        assert miners["online"] == 2
        assert miners["offline"] == 1


class TestHealthLatency:
    """#2715: response_time is measured, not the literal 0.1; the aggregate
    must not crash on floats and must not report a fabricated uptime."""

    def test_check_service_health_measures_real_latency(self, monkeypatch) -> None:
        import asyncio
        import time as _time

        import coordinator_api.contexts.infrastructure.routers.monitoring_dashboard as mod

        class _SlowClient:
            def __init__(self, **kwargs):
                pass

            def get(self, url):
                _time.sleep(0.01)
                return {"ok": True}

        monkeypatch.setattr(mod, "AITBCHTTPClient", _SlowClient)
        result = asyncio.run(mod.check_service_health("svc", {"url": "http://x", "port": 1}))
        assert result["status"] == "healthy"
        assert isinstance(result["response_time"], float)
        assert result["response_time"] >= 0.005

    def test_overall_metrics_averages_float_response_times(self) -> None:
        import coordinator_api.contexts.infrastructure.routers.monitoring_dashboard as mod

        metrics = mod.calculate_overall_metrics(
            {
                "a": {"status": "healthy", "response_time": 0.100},
                "b": {"status": "healthy", "response_time": 0.300},
                "c": {"status": "unhealthy"},
            }
        )
        assert metrics["average_response_time"] == "0.200s"
        assert metrics["overall_status"] == "unhealthy"
        assert "uptime_estimate" not in metrics


class TestDashboardServicesConfig:
    """#2409: the probed roster is env-overridable; bad config falls back to
    the deployed default rather than probing nothing."""

    def test_default_services_are_deployed_core(self, monkeypatch) -> None:
        from coordinator_api.contexts.infrastructure.routers.monitoring_dashboard import (
            _DEFAULT_SERVICES,
            _dashboard_services,
        )

        monkeypatch.delenv("MONITORING_DASHBOARD_SERVICES", raising=False)
        services = _dashboard_services()
        assert services == _DEFAULT_SERVICES
        assert "multimodal" not in services
        assert "market" in services

    def test_env_override_replaces_roster(self, monkeypatch) -> None:
        import json

        from coordinator_api.contexts.infrastructure.routers.monitoring_dashboard import _dashboard_services

        custom = {"custom_svc": {"name": "Custom", "port": 9999, "url": "http://localhost:9999"}}
        monkeypatch.setenv("MONITORING_DASHBOARD_SERVICES", json.dumps(custom))
        assert _dashboard_services() == custom

    def test_bad_env_falls_back_to_default(self, monkeypatch) -> None:
        from coordinator_api.contexts.infrastructure.routers.monitoring_dashboard import (
            _DEFAULT_SERVICES,
            _dashboard_services,
        )

        monkeypatch.setenv("MONITORING_DASHBOARD_SERVICES", "{not json")
        assert _dashboard_services() == _DEFAULT_SERVICES
        monkeypatch.setenv("MONITORING_DASHBOARD_SERVICES", "{}")
        assert _dashboard_services() == _DEFAULT_SERVICES
