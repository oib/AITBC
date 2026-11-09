"""Tests for /v1/agents/integration/* — AdminDep gating, owner scoping, and
manager delegation (#1289 continuation).

``agent_integration_router`` (15 endpoints, mounted 2026-09-11) was the largest
router surface left uncovered by the #1289 sweep. Every endpoint takes
``AdminDep`` and then enforces *workflow ownership* on top: ``user["sub"]``
must equal ``workflow.owner_id``. This file pins:

- auth gating (401 unauthenticated, 403 non-admin)
- the 404/403 ownership branches on config/instance/execution lookups
- owner filtering on the list endpoints and the production aggregates
- delegation to the service managers (patched at the router namespace — the
  managers' constructors chain into orchestrator/security/auditor services
  that are out of scope for a router sweep)
- the ZK mock gate (``AGENT_INTEGRATION_ZK_MOCK`` off → 503) and the alerts
  passthrough
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AIAgentWorkflow,
)
from coordinator_api.contexts.agent_coordination.routers import (
    agent_integration_router as ri,
)
from coordinator_api.contexts.agent_coordination.services.integration import (
    AgentDeploymentConfig,
    AgentDeploymentInstance,
    DeploymentStatus,
)

ADMIN_A = "admin-a"
ADMIN_B = "admin-b"


def _headers(sub: str, role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin_a() -> dict[str, str]:
    return _headers(ADMIN_A)


def _admin_b() -> dict[str, str]:
    return _headers(ADMIN_B)


def _client() -> dict[str, str]:
    return _headers("client-1", "client")


def _seed_workflow(db_session: Session, owner_id: str, name: str = "wf") -> AIAgentWorkflow:
    wf = AIAgentWorkflow(
        owner_id=owner_id,
        name=name,
        description="seeded",
        steps={"step_1": {"action": "noop"}},
        is_public=False,
        tags="[]",
    )
    db_session.add(wf)
    db_session.commit()
    db_session.refresh(wf)
    return wf


def _seed_config(
    db_session: Session,
    workflow_id: str,
    name: str = "dep",
    status: DeploymentStatus = DeploymentStatus.PENDING,
) -> AgentDeploymentConfig:
    cfg = AgentDeploymentConfig(
        workflow_id=workflow_id,
        deployment_name=name,
        status=status,
    )
    db_session.add(cfg)
    db_session.commit()
    db_session.refresh(cfg)
    return cfg


def _seed_instance(
    db_session: Session,
    deployment_id: str,
    environment: str = "production",
    status: DeploymentStatus = DeploymentStatus.DEPLOYED,
    health_status: str = "healthy",
) -> AgentDeploymentInstance:
    inst = AgentDeploymentInstance(
        deployment_id=deployment_id,
        instance_id=f"inst-{deployment_id}-{environment}",
        environment=environment,
        region="us-east",
        status=status,
        health_status=health_status,
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)
    return inst


@pytest.fixture
def managers(monkeypatch):
    """Patch the four service-manager classes + alert dispatcher at the router
    namespace with AsyncMock-backed namespaces."""
    deployment = SimpleNamespace(
        create_deployment_config=AsyncMock(),
        deploy_agent_workflow=AsyncMock(return_value={"status": "deployed", "deployment_id": "dep-x"}),
        monitor_deployment_health=AsyncMock(
            return_value={
                "overall_health": "healthy",
                "healthy_instances": 1,
                "unhealthy_instances": 0,
                "total_instances": 1,
            }
        ),
        scale_deployment=AsyncMock(return_value={"status": "scaled", "instances": 3}),
        rollback_deployment=AsyncMock(return_value={"status": "rolled_back"}),
    )
    integration = SimpleNamespace(integrate_with_zk_system=AsyncMock(return_value={"zk_status": "integrated"}))
    monitoring = SimpleNamespace(get_deployment_metrics=AsyncMock(return_value={"aggregated_metrics": {"cpu": 1.5}}))
    production = SimpleNamespace(deploy_to_production=AsyncMock(return_value={"overall_status": "success"}))
    alerts = SimpleNamespace(get_recent_alerts=Mock(return_value=[{"id": "alert-1"}]))

    monkeypatch.setattr(ri, "AgentDeploymentManager", lambda session: deployment)
    monkeypatch.setattr(ri, "AgentIntegrationManager", lambda session: integration)
    monkeypatch.setattr(ri, "AgentMonitoringManager", lambda session: monitoring)
    monkeypatch.setattr(ri, "AgentProductionManager", lambda session: production)
    monkeypatch.setattr(ri, "alert_dispatcher", alerts)
    return SimpleNamespace(
        deployment=deployment,
        integration=integration,
        monitoring=monitoring,
        production=production,
        alerts=alerts,
    )


BASE = "/v1/agents/integration"


@pytest.mark.unit
class TestAuthGating:
    def test_create_config_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/deployments/config",
            params={"workflow_id": "w", "deployment_name": "d"},
            json={"k": "v"},
        )
        assert resp.status_code == 401

    def test_create_config_rejects_client_role(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/deployments/config",
            params={"workflow_id": "w", "deployment_name": "d"},
            json={"k": "v"},
            headers=_client(),
        )
        assert resp.status_code == 403

    def test_list_configs_requires_auth(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/deployments/configs")
        assert resp.status_code == 401

    def test_production_alerts_requires_auth(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/production/alerts")
        assert resp.status_code == 401


@pytest.mark.unit
class TestDeploymentConfigEndpoints:
    def test_create_config_workflow_not_found_404(self, client: TestClient, managers) -> None:
        resp = client.post(
            f"{BASE}/deployments/config",
            params={"workflow_id": "nope", "deployment_name": "d"},
            json={"min_instances": 1},
            headers=_admin_a(),
        )
        assert resp.status_code == 404

    def test_create_config_other_owner_403(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_B)
        resp = client.post(
            f"{BASE}/deployments/config",
            params={"workflow_id": wf.id, "deployment_name": "d"},
            json={"min_instances": 1},
            headers=_admin_a(),
        )
        assert resp.status_code == 403

    def test_create_config_success_delegates(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        managers.deployment.create_deployment_config.return_value = cfg
        resp = client.post(
            f"{BASE}/deployments/config",
            params={"workflow_id": wf.id, "deployment_name": "my-dep"},
            json={"min_instances": 2},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        managers.deployment.create_deployment_config.assert_awaited_once()
        kwargs = managers.deployment.create_deployment_config.await_args.kwargs
        assert kwargs["workflow_id"] == wf.id
        assert kwargs["deployment_name"] == "my-dep"
        assert kwargs["deployment_config"] == {"min_instances": 2}

    def test_list_configs_owner_scoping(self, client: TestClient, db_session: Session, managers) -> None:
        wf_a = _seed_workflow(db_session, ADMIN_A, "wf-a")
        wf_b = _seed_workflow(db_session, ADMIN_B, "wf-b")
        cfg_a = _seed_config(db_session, wf_a.id, "dep-a")
        _seed_config(db_session, wf_b.id, "dep-b")
        resp = client.get(f"{BASE}/deployments/configs", headers=_admin_a())
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()}
        assert ids == {cfg_a.id}

    def test_get_config_404_and_owner_403(self, client: TestClient, db_session: Session, managers) -> None:
        resp = client.get(f"{BASE}/deployments/configs/nope", headers=_admin_a())
        assert resp.status_code == 404
        wf_b = _seed_workflow(db_session, ADMIN_B)
        cfg_b = _seed_config(db_session, wf_b.id)
        resp = client.get(f"{BASE}/deployments/configs/{cfg_b.id}", headers=_admin_a())
        assert resp.status_code == 403

    def test_get_config_owner_200(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        resp = client.get(f"{BASE}/deployments/configs/{cfg.id}", headers=_admin_a())
        assert resp.status_code == 200
        assert resp.json()["id"] == cfg.id


@pytest.mark.unit
class TestDeploymentActionEndpoints:
    """deploy / health / scale / rollback share the same guard shape:
    config 404 -> workflow owner 403 -> manager delegation."""

    @pytest.mark.parametrize(
        "method,path_suffix,expected_key",
        [
            ("post", "deploy", "deploy_agent_workflow"),
            ("get", "health", "monitor_deployment_health"),
            ("post", "scale", "scale_deployment"),
            ("post", "rollback", "rollback_deployment"),
        ],
    )
    def test_missing_config_404(self, client: TestClient, managers, method: str, path_suffix: str, expected_key: str) -> None:
        kwargs: dict[str, Any] = {"params": {"target_instances": 2}} if path_suffix == "scale" else {}
        resp = getattr(client, method)(f"{BASE}/deployments/nope/{path_suffix}", headers=_admin_a(), **kwargs)
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "method,path_suffix,manager_attr,call_kwargs",
        [
            ("post", "deploy", "deploy_agent_workflow", {}),
            ("get", "health", "monitor_deployment_health", {}),
            ("post", "scale", "scale_deployment", {"params": {"target_instances": 4}}),
            ("post", "rollback", "rollback_deployment", {}),
        ],
    )
    def test_other_owner_403(
        self,
        client: TestClient,
        db_session: Session,
        managers,
        method: str,
        path_suffix: str,
        manager_attr: str,
        call_kwargs: dict,
    ) -> None:
        wf_b = _seed_workflow(db_session, ADMIN_B)
        cfg_b = _seed_config(db_session, wf_b.id)
        resp = getattr(client, method)(f"{BASE}/deployments/{cfg_b.id}/{path_suffix}", headers=_admin_a(), **call_kwargs)
        assert resp.status_code == 403
        assert getattr(managers.deployment, manager_attr).await_count == 0

    def test_deploy_success_passes_environment(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        resp = client.post(
            f"{BASE}/deployments/{cfg.id}/deploy",
            params={"target_environment": "staging"},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        kwargs = managers.deployment.deploy_agent_workflow.await_args.kwargs
        assert kwargs["deployment_config_id"] == cfg.id
        assert kwargs["target_environment"] == "staging"

    def test_scale_success_passes_target(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        resp = client.post(
            f"{BASE}/deployments/{cfg.id}/scale",
            params={"target_instances": 7},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        kwargs = managers.deployment.scale_deployment.await_args.kwargs
        assert kwargs["deployment_config_id"] == cfg.id
        assert kwargs["target_instances"] == 7

    def test_rollback_success(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        resp = client.post(f"{BASE}/deployments/{cfg.id}/rollback", headers=_admin_a())
        assert resp.status_code == 200
        assert managers.deployment.rollback_deployment.await_args.args == (cfg.id,)


@pytest.mark.unit
class TestDeploymentInstances:
    def test_list_instances_owner_scoping_and_filters(self, client: TestClient, db_session: Session, managers) -> None:
        wf_a = _seed_workflow(db_session, ADMIN_A, "wf-a")
        wf_b = _seed_workflow(db_session, ADMIN_B, "wf-b")
        cfg_a = _seed_config(db_session, wf_a.id)
        cfg_b = _seed_config(db_session, wf_b.id)
        inst_a = _seed_instance(db_session, cfg_a.id, environment="production")
        _seed_instance(db_session, cfg_b.id, environment="staging")
        _seed_instance(db_session, cfg_a.id, environment="staging", health_status="unhealthy")

        resp = client.get(f"{BASE}/deployments/instances", headers=_admin_a())
        assert resp.status_code == 200
        ids = {i["id"] for i in resp.json()}
        assert inst_a.id in ids
        assert len(ids) == 2  # both of admin-a's instances, none of admin-b's

        resp = client.get(
            f"{BASE}/deployments/instances",
            params={"environment": "staging", "status": "deployed"},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        envs = {i["environment"] for i in resp.json()}
        assert envs == {"staging"}

    def test_get_instance_404s_and_403(self, client: TestClient, db_session: Session, managers) -> None:
        resp = client.get(f"{BASE}/deployments/instances/nope", headers=_admin_a())
        assert resp.status_code == 404
        wf_b = _seed_workflow(db_session, ADMIN_B)
        cfg_b = _seed_config(db_session, wf_b.id)
        inst_b = _seed_instance(db_session, cfg_b.id)
        resp = client.get(f"{BASE}/deployments/instances/{inst_b.id}", headers=_admin_a())
        assert resp.status_code == 403

    def test_get_instance_owner_200(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id)
        resp = client.get(f"{BASE}/deployments/instances/{inst.id}", headers=_admin_a())
        assert resp.status_code == 200
        assert resp.json()["id"] == inst.id


@pytest.mark.unit
class TestZkIntegration:
    def test_mock_disabled_returns_503(self, client: TestClient, db_session: Session, managers) -> None:
        """Default AGENT_INTEGRATION_ZK_MOCK is off — the endpoint must refuse
        before touching the execution lookup."""
        resp = client.post(f"{BASE}/integrations/zk/exec-x", headers=_admin_a())
        assert resp.status_code == 503
        managers.integration.integrate_with_zk_system.assert_not_called()

    def test_enabled_missing_execution_404(self, client: TestClient, db_session: Session, managers, monkeypatch) -> None:
        monkeypatch.setattr(ri, "zk_integration_mock_enabled", lambda: True)
        resp = client.post(f"{BASE}/integrations/zk/nope", headers=_admin_a())
        assert resp.status_code == 404

    def test_enabled_other_owner_403(self, client: TestClient, db_session: Session, managers, monkeypatch) -> None:
        monkeypatch.setattr(ri, "zk_integration_mock_enabled", lambda: True)
        wf_b = _seed_workflow(db_session, ADMIN_B)
        ex = AgentExecution(workflow_id=wf_b.id, client_id="client1")
        db_session.add(ex)
        db_session.commit()
        db_session.refresh(ex)
        resp = client.post(f"{BASE}/integrations/zk/{ex.id}", headers=_admin_a())
        assert resp.status_code == 403

    def test_enabled_success_delegates(self, client: TestClient, db_session: Session, managers, monkeypatch) -> None:
        monkeypatch.setattr(ri, "zk_integration_mock_enabled", lambda: True)
        wf = _seed_workflow(db_session, ADMIN_A)
        ex = AgentExecution(workflow_id=wf.id, client_id="client1")
        db_session.add(ex)
        db_session.commit()
        db_session.refresh(ex)
        resp = client.post(
            f"{BASE}/integrations/zk/{ex.id}",
            params={"verification_level": "full"},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        kwargs = managers.integration.integrate_with_zk_system.await_args.kwargs
        assert kwargs["execution_id"] == ex.id
        assert kwargs["verification_level"].value == "full"


@pytest.mark.unit
class TestMetricsAndProduction:
    def test_metrics_missing_config_404(self, client: TestClient, managers) -> None:
        resp = client.get(f"{BASE}/metrics/deployments/nope", headers=_admin_a())
        assert resp.status_code == 404

    def test_metrics_success_passes_time_range(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        cfg = _seed_config(db_session, wf.id)
        resp = client.get(
            f"{BASE}/metrics/deployments/{cfg.id}",
            params={"time_range": "24h"},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        assert resp.json()["aggregated_metrics"] == {"cpu": 1.5}
        kwargs = managers.monitoring.get_deployment_metrics.await_args.kwargs
        assert kwargs["deployment_config_id"] == cfg.id
        assert kwargs["time_range"] == "24h"

    def test_production_deploy_workflow_not_found_404(self, client: TestClient, managers) -> None:
        resp = client.post(
            f"{BASE}/production/deploy",
            params={"workflow_id": "nope"},
            json={"deployment_config": {"name": "prod"}},
            headers=_admin_a(),
        )
        assert resp.status_code == 404

    def test_production_deploy_other_owner_403(self, client: TestClient, db_session: Session, managers) -> None:
        wf_b = _seed_workflow(db_session, ADMIN_B)
        resp = client.post(
            f"{BASE}/production/deploy",
            params={"workflow_id": wf_b.id},
            json={"deployment_config": {"name": "prod"}},
            headers=_admin_a(),
        )
        assert resp.status_code == 403
        managers.production.deploy_to_production.assert_not_called()

    def test_production_deploy_success(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        resp = client.post(
            f"{BASE}/production/deploy",
            params={"workflow_id": wf.id},
            json={"deployment_config": {"name": "prod-dep", "min_instances": 2}},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        assert resp.json()["overall_status"] == "success"
        kwargs = managers.production.deploy_to_production.await_args.kwargs
        assert kwargs["workflow_id"] == wf.id
        assert kwargs["deployment_config"]["name"] == "prod-dep"

    @pytest.mark.xfail(
        strict=True,
        reason="join bug: select(AgentDeploymentConfig).join(AIAgentWorkflow) has no FK relationship -> InvalidRequestError -> 500 on every call (#1289 sweep find, needs follow-up row)",
    )
    def test_dashboard_aggregates_own_deployments(self, client: TestClient, db_session: Session, managers) -> None:
        wf_a = _seed_workflow(db_session, ADMIN_A, "wf-a")
        wf_b = _seed_workflow(db_session, ADMIN_B, "wf-b")
        cfg_deployed = _seed_config(db_session, wf_a.id, "dep-ok", DeploymentStatus.DEPLOYED)
        cfg_failed = _seed_config(db_session, wf_a.id, "dep-bad", DeploymentStatus.FAILED)
        _seed_config(db_session, wf_b.id, "dep-other", DeploymentStatus.DEPLOYED)
        _seed_instance(db_session, cfg_deployed.id, health_status="healthy")
        _seed_instance(db_session, cfg_deployed.id, environment="staging", health_status="unhealthy")

        resp = client.get(f"{BASE}/production/dashboard", headers=_admin_a())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_deployments"] == 2
        assert data["active_deployments"] == 1
        assert data["failed_deployments"] == 1
        by_id = {d["deployment_id"]: d for d in data["deployments"]}
        assert by_id[cfg_deployed.id]["total_instances"] == 2
        assert by_id[cfg_deployed.id]["healthy_instances"] == 1
        assert by_id[cfg_failed.id]["total_instances"] == 0

    @pytest.mark.xfail(
        strict=True,
        reason="join bug: select(AgentDeploymentConfig).join(AIAgentWorkflow) has no FK relationship -> InvalidRequestError -> 500 on every call (#1289 sweep find, needs follow-up row)",
    )
    def test_health_aggregates_status(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        _seed_config(db_session, wf.id, "dep-1", DeploymentStatus.DEPLOYED)
        managers.deployment.monitor_deployment_health.return_value = {
            "overall_health": "healthy",
            "healthy_instances": 2,
            "unhealthy_instances": 0,
            "total_instances": 2,
        }
        resp = client.get(f"{BASE}/production/health", headers=_admin_a())
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_health"] == "healthy"
        assert data["healthy_deployments"] == 1
        assert data["total_instances"] == 2

    @pytest.mark.xfail(
        strict=True,
        reason="join bug: select(AgentDeploymentConfig).join(AIAgentWorkflow) has no FK relationship -> InvalidRequestError -> 500 on every call (#1289 sweep find, needs follow-up row)",
    )
    def test_health_unhealthy_and_degraded(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        _seed_config(db_session, wf.id, "dep-1", DeploymentStatus.DEPLOYED)
        _seed_config(db_session, wf.id, "dep-2", DeploymentStatus.DEPLOYED)
        # First config unhealthy, second raises -> unknown -> degraded? unhealthy wins.
        managers.deployment.monitor_deployment_health.side_effect = [
            {
                "overall_health": "unhealthy",
                "healthy_instances": 0,
                "unhealthy_instances": 1,
                "total_instances": 1,
            },
            RuntimeError("boom"),
        ]
        resp = client.get(f"{BASE}/production/health", headers=_admin_a())
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_health"] == "unhealthy"
        assert data["unhealthy_deployments"] == 1
        assert data["unknown_deployments"] == 1

    @pytest.mark.xfail(
        strict=True,
        reason="join bug: select(AgentDeploymentConfig).join(AIAgentWorkflow) has no FK relationship -> InvalidRequestError -> 500 on every call (#1289 sweep find, needs follow-up row)",
    )
    def test_health_all_unknown_is_degraded(self, client: TestClient, db_session: Session, managers) -> None:
        wf = _seed_workflow(db_session, ADMIN_A)
        _seed_config(db_session, wf.id, "dep-1", DeploymentStatus.DEPLOYED)
        managers.deployment.monitor_deployment_health.side_effect = RuntimeError("down")
        resp = client.get(f"{BASE}/production/health", headers=_admin_a())
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_health"] == "degraded"
        assert data["unknown_deployments"] == 1

    def test_alerts_passthrough(self, client: TestClient, managers) -> None:
        managers.alerts.get_recent_alerts.return_value = [{"id": "a1"}, {"id": "a2"}]
        resp = client.get(
            f"{BASE}/production/alerts",
            params={"severity": "critical", "limit": 5},
            headers=_admin_a(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert data["severity"] == "critical"
        managers.alerts.get_recent_alerts.assert_called_once_with(severity="critical", limit=5)
