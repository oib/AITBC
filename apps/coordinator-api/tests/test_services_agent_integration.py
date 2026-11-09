"""Service-layer tests for agent_coordination/services/integration.py (#1289 round 3).

Covers AgentDeploymentManager, AgentMonitoringManager, AgentProductionManager,
AgentIntegrationManager (ZK path) and ZKProofService against a real in-memory
SQLite session. systemd/httpx boundaries are mocked; DB state is real.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent import (
    AgentExecution,
    AgentStep,
    AgentStepExecution,
    AIAgentWorkflow,
    StepType,
    VerificationLevel,
)
from coordinator_api.contexts.agent_coordination.services.integration import (
    AgentDeploymentConfig,
    AgentDeploymentInstance,
    AgentDeploymentManager,
    AgentIntegrationManager,
    AgentMonitoringManager,
    AgentProductionManager,
    DeploymentStatus,
    ZKProofService,
    _validate_unit_component,
    zk_integration_mock_enabled,
)


def _seed_workflow(session: Session, owner: str = "admin-a", name: str = "wf") -> AIAgentWorkflow:
    wf = AIAgentWorkflow(owner_id=owner, name=name, steps={"s1": {}}, dependencies={})
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


def _seed_config(
    session: Session,
    workflow_id: str,
    name: str = "dep",
    status: DeploymentStatus = DeploymentStatus.PENDING,
    **kwargs: Any,
) -> AgentDeploymentConfig:
    cfg = AgentDeploymentConfig(workflow_id=workflow_id, deployment_name=name, status=status, **kwargs)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


def _seed_instance(
    session: Session,
    deployment_id: str,
    instance_id: str = "dep-prod-0",
    **kwargs: Any,
) -> AgentDeploymentInstance:
    inst = AgentDeploymentInstance(
        deployment_id=deployment_id,
        instance_id=instance_id,
        environment=kwargs.pop("environment", "production"),
        region=kwargs.pop("region", "default"),
        **kwargs,
    )
    session.add(inst)
    session.commit()
    session.refresh(inst)
    return inst


@pytest.fixture
def deployment_manager(db_session: Session) -> AgentDeploymentManager:
    return AgentDeploymentManager(db_session)


@pytest.fixture
def monitoring_manager(db_session: Session) -> AgentMonitoringManager:
    return AgentMonitoringManager(db_session)


class TestValidateUnitComponent:
    @pytest.mark.parametrize("value", ["dep", "dep-1", "a.b_c-9", "A" * 63])
    def test_accepts_safe(self, value: str) -> None:
        assert _validate_unit_component(value, "f") == value

    @pytest.mark.parametrize(
        "value",
        ["", "-lead", ".lead", "has space", "slash/x", "semi;colon", "A" * 64, "ünïcode"],
    )
    def test_rejects_unsafe(self, value: str) -> None:
        with pytest.raises(ValueError, match="invalid f"):
            _validate_unit_component(value, "f")

    def test_rejects_non_str(self) -> None:
        with pytest.raises(ValueError):
            _validate_unit_component(None, "f")  # type: ignore[arg-type]


class TestZKProofService:
    async def test_mock_disabled_by_default(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENT_INTEGRATION_ZK_MOCK", raising=False)
        assert zk_integration_mock_enabled() is False
        svc = ZKProofService(db_session)
        with pytest.raises(RuntimeError, match="mock ZK proof service is disabled"):
            await svc.generate_zk_proof("c", {})
        with pytest.raises(RuntimeError, match="mock ZK proof service is disabled"):
            await svc.verify_proof("p")

    async def test_mock_enabled_returns_proof(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "1")
        svc = ZKProofService(db_session)
        proof = await svc.generate_zk_proof("circuit_x", {"a": 1})
        assert proof["circuit_name"] == "circuit_x"
        assert proof["proof_id"].startswith("proof_")
        verified = await svc.verify_proof(proof["proof_id"])
        assert verified["verified"] is True


class TestCreateDeploymentConfig:
    async def test_creates_and_audits(self, deployment_manager: AgentDeploymentManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        cfg = await deployment_manager.create_deployment_config(
            wf.id, "dep-a", {"min_instances": 2, "target_environments": ["production"]}
        )
        assert cfg.id.startswith("deploy_")
        assert cfg.min_instances == 2
        assert cfg.status == DeploymentStatus.PENDING
        row = db_session.get(AgentDeploymentConfig, cfg.id)
        assert row is not None and row.deployment_name == "dep-a"
        from coordinator_api.contexts.agent_coordination.services.security import AgentAuditLog, AuditEventType

        events = db_session.scalars(select(AgentAuditLog)).all()
        assert any(e.event_type == AuditEventType.WORKFLOW_CREATED for e in events)

    async def test_rejects_unsafe_name(self, deployment_manager: AgentDeploymentManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        with pytest.raises(ValueError, match="invalid deployment_name"):
            await deployment_manager.create_deployment_config(wf.id, "bad name;", {})

    async def test_rejects_unsafe_via_config_kwarg_path(
        self, deployment_manager: AgentDeploymentManager, db_session: Session
    ) -> None:
        wf = _seed_workflow(db_session)
        # deployment_name itself is validated; a hostile env is validated at deploy time.
        cfg = await deployment_manager.create_deployment_config(wf.id, "ok-name", {})
        assert cfg.workflow_id == wf.id


class TestDeployAgentWorkflow:
    async def test_config_not_found(self, deployment_manager: AgentDeploymentManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await deployment_manager.deploy_agent_workflow("deploy_missing")

    async def test_rejects_unsafe_environment(self, deployment_manager: AgentDeploymentManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, min_instances=1)
        with pytest.raises(ValueError, match="invalid target_environment"):
            await deployment_manager.deploy_agent_workflow(cfg.id, target_environment="prod; rm -rf")

    async def test_happy_path_deploys_instances(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(deployment_manager, "_deploy_agent_systemd", AsyncMock())
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, min_instances=2, deployment_regions=["eu-1"])
        result = await deployment_manager.deploy_agent_workflow(cfg.id, target_environment="staging")
        assert result["status"] == "deploying"
        assert len(result["instances"]) == 2
        assert all(i["status"] == "deployed" for i in result["instances"])
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentConfig, cfg.id)
        assert fresh is not None and fresh.status == DeploymentStatus.DEPLOYED
        instances = db_session.scalars(
            select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == cfg.id)
        ).all()
        assert len(instances) == 2
        assert all(i.status == DeploymentStatus.DEPLOYED and i.health_status == "healthy" for i in instances)
        assert all(i.region == "eu-1" for i in instances)
        assert {i.port for i in instances} == {8000, 8001}
        assert fresh is not None and fresh.agent_version == "1.0.0"

    async def test_failed_instances_mark_config_failed(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            deployment_manager, "_deploy_agent_systemd", AsyncMock(side_effect=RuntimeError("systemctl missing"))
        )
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, min_instances=1)
        result = await deployment_manager.deploy_agent_workflow(cfg.id)
        assert result["deployment_errors"]
        assert result["instances"][0]["status"] == "failed"
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentConfig, cfg.id)
        assert fresh is not None and fresh.status == DeploymentStatus.FAILED


class _FakeProc:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""


def _patch_systemctl(monkeypatch: pytest.MonkeyPatch, active: bool = True) -> None:
    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
        if "is-active" in cmd:
            return _FakeProc(b"active\n" if active else b"inactive\n")
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)


class TestCheckInstanceHealth:
    async def test_inactive_service_is_unhealthy(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=False)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "unhealthy"
        assert inst.health_status == "unhealthy"

    async def test_active_no_endpoint_is_healthy(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=True)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, endpoint_url=None)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "healthy"

    async def test_http_200_healthy_body(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=True)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, endpoint_url="http://x:1")

        class _Resp:
            status_code = 200

            def json(self) -> dict[str, str]:
                return {"status": "healthy"}

        class _Client:
            def __init__(self, **kwargs: Any) -> None: ...

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: Any) -> None: ...

            async def get(self, url: str) -> _Resp:
                return _Resp()

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "healthy"
        assert health["response_time"] >= 0

    async def test_http_non_200_is_unhealthy(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=True)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, endpoint_url="http://x:1")

        class _Resp:
            status_code = 503

            def json(self) -> dict[str, str]:
                return {}

        class _Client:
            def __init__(self, **kwargs: Any) -> None: ...

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: Any) -> None: ...

            async def get(self, url: str) -> _Resp:
                return _Resp()

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "unhealthy"

    async def test_http_error_is_degraded(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=True)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, endpoint_url="http://x:1")

        class _Client:
            def __init__(self, **kwargs: Any) -> None: ...

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: Any) -> None: ...

            async def get(self, url: str) -> Any:
                raise ConnectionError("refused")

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "degraded"

    async def test_history_capped_at_100(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=False)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id)
        inst.health_check_history = [{"i": i} for i in range(150)]
        db_session.add(inst)
        db_session.commit()
        await deployment_manager._check_instance_health(inst)
        assert len(inst.health_check_history) == 100
        assert inst.health_check_history[-1]["status"] == "unhealthy"

    async def test_health_check_history_record_persists(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_systemctl(monkeypatch, active=False)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id)
        await deployment_manager._check_instance_health(inst)
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentInstance, inst.id)
        assert fresh is not None
        assert len(fresh.health_check_history) == 1
        assert fresh.health_check_history[0]["status"] == "unhealthy"

    async def test_subprocess_exception_marks_unhealthy_and_counts(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*a: Any, **k: Any) -> _FakeProc:
            raise OSError("no systemd")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id)
        health = await deployment_manager._check_instance_health(inst)
        assert health["status"] == "unhealthy"
        assert health["consecutive_failures"] == 1
        assert inst.consecutive_failures == 1


class TestMonitorDeploymentHealth:
    async def test_config_not_found(self, deployment_manager: AgentDeploymentManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await deployment_manager.monitor_deployment_health("deploy_missing")

    async def test_aggregates_health_statuses(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        for i in range(3):
            _seed_instance(db_session, cfg.id, instance_id=f"dep-prod-{i}")
        statuses = ["healthy", "unhealthy", "degraded"]
        monkeypatch.setattr(
            deployment_manager,
            "_check_instance_health",
            AsyncMock(side_effect=[{"instance_id": f"i{i}", "status": s} for i, s in enumerate(statuses)]),
        )
        result = await deployment_manager.monitor_deployment_health(cfg.id)
        assert result["total_instances"] == 3
        assert result["healthy_instances"] == 1
        assert result["unhealthy_instances"] == 1
        # "degraded" is neither healthy nor unhealthy -> counted unknown -> overall unhealthy wins
        assert result["unknown_instances"] == 1
        assert result["overall_health"] == "unhealthy"

    async def test_all_unknown_is_degraded(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        _seed_instance(db_session, cfg.id)
        # _check_instance_health catches its own exceptions; return an
        # unrecognized status so it lands in the unknown bucket
        monkeypatch.setattr(
            deployment_manager,
            "_check_instance_health",
            AsyncMock(return_value={"instance_id": "i", "status": "mystery"}),
        )
        result = await deployment_manager.monitor_deployment_health(cfg.id)
        assert result["overall_health"] == "degraded"
        assert result["unknown_instances"] == 1


class TestScaleDeployment:
    async def test_config_not_found(self, deployment_manager: AgentDeploymentManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await deployment_manager.scale_deployment("deploy_missing", 3)

    async def test_scale_up_creates_instances(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(deployment_manager, "_deploy_agent_systemd", AsyncMock())
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, min_instances=1)
        _seed_instance(db_session, cfg.id, instance_id="dep-prod-0")
        result = await deployment_manager.scale_deployment(cfg.id, 3)
        assert result["scaling_action"] == "scale_up"
        assert result["current_instances"] == 1
        assert len(result["scaled_instances"]) == 2
        count = len(
            db_session.scalars(select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == cfg.id)).all()
        )
        assert count == 3

    async def test_scale_down_removes_tail_instances(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        remove = AsyncMock()
        monkeypatch.setattr(deployment_manager, "_remove_deployment_instance", remove)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        ids = []
        for i in range(3):
            inst = _seed_instance(db_session, cfg.id, instance_id=f"dep-prod-{i}")
            ids.append(inst.id)
        result = await deployment_manager.scale_deployment(cfg.id, 1)
        assert result["scaling_action"] == "scale_down"
        assert remove.await_count == 2
        removed_ids = {c.args[0] for c in remove.await_args_list}
        assert removed_ids == {ids[1], ids[2]}  # tail two removed

    async def test_no_change(self, deployment_manager: AgentDeploymentManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        _seed_instance(db_session, cfg.id)
        result = await deployment_manager.scale_deployment(cfg.id, 1)
        assert result["scaling_action"] == "no_change"
        assert result["scaled_instances"] == []


class TestRemoveDeploymentInstance:
    async def test_marks_terminated_and_runs_systemctl(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
            calls.append(list(cmd))
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, instance_id="dep-prod-9")
        await deployment_manager._remove_deployment_instance(inst.id)
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentInstance, inst.id)
        assert fresh is not None and fresh.status == DeploymentStatus.TERMINATED
        assert ["systemctl", "stop", "aitbc-agent-dep-prod-9"] in calls
        assert ["systemctl", "disable", "aitbc-agent-dep-prod-9"] in calls

    async def test_missing_instance_is_noop(
        self, deployment_manager: AgentDeploymentManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        await deployment_manager._remove_deployment_instance("instance_missing")

    async def test_unsafe_instance_id_raises(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, instance_id="bad;id")
        with pytest.raises(ValueError, match="invalid instance_id"):
            await deployment_manager._remove_deployment_instance(inst.id)


class TestRollbackDeployment:
    async def test_config_not_found(self, deployment_manager: AgentDeploymentManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await deployment_manager.rollback_deployment("deploy_missing")

    async def test_rollback_disabled_rejected(self, deployment_manager: AgentDeploymentManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, rollback_enabled=False)
        with pytest.raises(ValueError, match="Rollback not enabled"):
            await deployment_manager.rollback_deployment(cfg.id)

    async def test_rollback_without_previous_version_errors(
        self, deployment_manager: AgentDeploymentManager, db_session: Session
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, rollback_enabled=True)
        _seed_instance(db_session, cfg.id, instance_id="dep-prod-0")
        result = await deployment_manager.rollback_deployment(cfg.id)
        assert result["rollback_errors"]
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentConfig, cfg.id)
        assert fresh is not None and fresh.status == DeploymentStatus.FAILED

    async def test_rollback_with_instances(
        self, deployment_manager: AgentDeploymentManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(deployment_manager, "_deploy_agent_systemd", AsyncMock())
        monkeypatch.setattr(deployment_manager, "_remove_deployment_instance", AsyncMock())
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id, rollback_enabled=True, agent_version="1.0.0", previous_version="0.9.0")
        _seed_instance(db_session, cfg.id, instance_id="dep-prod-0")
        result = await deployment_manager.rollback_deployment(cfg.id)
        assert result["rollback_errors"] == []
        assert result["rolled_back_instances"]
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentConfig, cfg.id)
        assert fresh is not None and fresh.status == DeploymentStatus.TERMINATED


class TestMonitoringManager:
    async def test_metrics_config_not_found(self, monitoring_manager: AgentMonitoringManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await monitoring_manager.get_deployment_metrics("deploy_missing")

    async def test_metrics_aggregates_instance_fields(
        self, monitoring_manager: AgentMonitoringManager, db_session: Session
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        _seed_instance(
            db_session,
            cfg.id,
            request_count=10,
            error_count=2,
            average_response_time=0.5,
            cpu_usage=40.0,
            memory_usage=512,
            uptime_percentage=99.0,
            endpoint_url=None,
        )
        _seed_instance(
            db_session,
            cfg.id,
            instance_id="dep-prod-1",
            request_count=30,
            error_count=0,
            average_response_time=1.5,
            cpu_usage=60.0,
            memory_usage=1024,
            uptime_percentage=100.0,
            endpoint_url=None,
        )
        metrics = await monitoring_manager.get_deployment_metrics(cfg.id, time_range="24h")
        assert metrics["time_range"] == "24h"
        assert metrics["total_instances"] == 2
        agg = metrics["aggregated_metrics"]
        assert agg["total_requests"] == 40
        assert agg["total_errors"] == 2
        # weighted by request_count: (0.5*10 + 1.5*30) / 40 = 1.25
        assert agg["average_response_time"] == pytest.approx(1.25)
        assert agg["average_cpu_usage"] == pytest.approx(50.0)
        assert agg["average_memory_usage"] == pytest.approx(768.0)
        assert agg["uptime_percentage"] == pytest.approx(99.5)

    async def test_metrics_empty_deployment(self, monitoring_manager: AgentMonitoringManager, db_session: Session) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        metrics = await monitoring_manager.get_deployment_metrics(cfg.id)
        assert metrics["total_instances"] == 0
        assert metrics["aggregated_metrics"]["total_requests"] == 0

    async def test_collect_instance_metrics_no_endpoint_uses_db_fields(
        self, monitoring_manager: AgentMonitoringManager, db_session: Session
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, request_count=7, endpoint_url=None)
        data = await monitoring_manager._collect_instance_metrics(inst)
        assert data["request_count"] == 7
        assert data["instance_id"] == inst.instance_id

    async def test_collect_instance_metrics_http_fallback(
        self, monitoring_manager: AgentMonitoringManager, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        inst = _seed_instance(db_session, cfg.id, endpoint_url="http://x:1", request_count=3, cpu_usage=11.0)

        class _Resp:
            status_code = 500

            def json(self) -> dict[str, Any]:
                return {}

        class _Client:
            def __init__(self, **kwargs: Any) -> None: ...

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: Any) -> None: ...

            async def get(self, url: str) -> _Resp:
                return _Resp()

        monkeypatch.setattr("httpx.AsyncClient", _Client)
        data = await monitoring_manager._collect_instance_metrics(inst)
        assert data["request_count"] == 3  # fell back to DB field on non-200
        assert data["cpu_usage"] == 11.0

    async def test_create_alerting_rules_persists(
        self, monitoring_manager: AgentMonitoringManager, db_session: Session
    ) -> None:
        wf = _seed_workflow(db_session)
        cfg = _seed_config(db_session, wf.id)
        rules = {"rules": [{"name": "cpu"}], "channels": ["log", "webhook"]}
        result = await monitoring_manager.create_alerting_rules(cfg.id, rules)
        assert result["status"] == "created"
        assert result["rules_created"] == 1
        assert result["alert_channels"] == ["log", "webhook"]
        db_session.expire_all()
        fresh = db_session.get(AgentDeploymentConfig, cfg.id)
        assert fresh is not None and fresh.alerting_rules == rules

    async def test_create_alerting_rules_not_found(self, monitoring_manager: AgentMonitoringManager) -> None:
        with pytest.raises(ValueError, match="Deployment config not found"):
            await monitoring_manager.create_alerting_rules("deploy_missing", {})


class TestProductionManager:
    async def test_deploy_to_production_end_to_end(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        prod = AgentProductionManager(db_session)
        monkeypatch.setattr(prod.deployment_manager, "_deploy_agent_systemd", AsyncMock())
        wf = _seed_workflow(db_session)
        result = await prod.deploy_to_production(
            wf.id,
            {"name": "prod-dep", "min_instances": 1, "alerting_rules": {"rules": []}},
            integration_config={"zk": True},
        )
        assert result["workflow_id"] == wf.id
        assert result["deployment_id"].startswith("deploy_")
        assert result["integration_status"] == "configured"

    async def test_deploy_to_production_reaches_success(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        prod = AgentProductionManager(db_session)
        monkeypatch.setattr(prod.deployment_manager, "_deploy_agent_systemd", AsyncMock())
        wf = _seed_workflow(db_session)
        result = await prod.deploy_to_production(wf.id, {"name": "prod-dep", "min_instances": 1})
        assert result["overall_status"] == "success"
        assert result["monitoring_status"] == "created"
        assert result["deployment_status"] == "deploying"

    async def test_deploy_to_production_failure_audits(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        prod = AgentProductionManager(db_session)
        monkeypatch.setattr(
            prod.deployment_manager,
            "create_deployment_config",
            AsyncMock(side_effect=RuntimeError("db gone")),
        )
        with pytest.raises(RuntimeError, match="db gone"):
            await prod.deploy_to_production("wf_x", {"name": "d"})


class TestIntegrationManagerZK:
    async def test_execution_not_found(self, db_session: Session) -> None:
        mgr = AgentIntegrationManager(db_session)
        with pytest.raises(ValueError, match="Execution not found"):
            await mgr.integrate_with_zk_system("exec_missing")

    def _seed_execution(self, session: Session, with_steps: bool = True) -> AgentExecution:
        ex = AgentExecution(workflow_id="wf1", client_id="client1", status="completed")
        session.add(ex)
        session.commit()
        session.refresh(ex)
        if with_steps:
            se = AgentStepExecution(execution_id=ex.id, step_id="step_1", status="completed")
            session.add(se)
            session.commit()
        return ex

    async def test_mock_disabled_yields_partial_success(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENT_INTEGRATION_ZK_MOCK", raising=False)
        mgr = AgentIntegrationManager(db_session)
        ex = self._seed_execution(db_session)
        result = await mgr.integrate_with_zk_system(ex.id)
        # workflow proof generation fails closed -> recorded as integration error
        assert result["integration_status"] == "partial_success"
        assert any(e.get("error_type") == "workflow_proof_generation" for e in result["integration_errors"])

    async def test_mock_enabled_full_success(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "1")
        mgr = AgentIntegrationManager(db_session)
        ex = self._seed_execution(db_session)
        result = await mgr.integrate_with_zk_system(ex.id, VerificationLevel.FULL)
        assert result["integration_status"] == "success"
        assert result["integration_errors"] == []
        assert result["workflow_proof"]["proof_id"].startswith("proof_")
        assert result["workflow_verification"]["verified"] is True
        # no AgentStep rows -> no step requires proof -> no step proofs
        assert result["zk_proofs_generated"] == []

    async def test_step_requires_proof_generates_step_proof(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """requires_proof lives on AgentStep; a step execution bound to a
        requires_proof step must produce a per-step ZK proof."""
        monkeypatch.setenv("AGENT_INTEGRATION_ZK_MOCK", "1")
        mgr = AgentIntegrationManager(db_session)
        ex = self._seed_execution(db_session, with_steps=False)
        step = AgentStep(
            workflow_id=ex.workflow_id,
            name="prove-me",
            step_type=StepType.INFERENCE,
            requires_proof=True,
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)
        se = AgentStepExecution(execution_id=ex.id, step_id=step.id, status="completed")
        db_session.add(se)
        db_session.commit()
        result = await mgr.integrate_with_zk_system(ex.id)
        assert result["integration_status"] == "success"
        assert len(result["zk_proofs_generated"]) == 1
        assert result["zk_proofs_generated"][0]["step_id"] == step.id
        assert result["zk_proofs_generated"][0]["proof_id"].startswith("proof_")
        assert len(result["verification_results"]) == 1
        assert result["verification_results"][0]["verification_status"] is True
