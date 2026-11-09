"""Service-layer tests for agent_coordination/services/security.py (#1289 round 5).

Adjacent to the #1312 integration-layer fixes: AgentAuditor (risk scoring,
hash, high-risk handling), AgentTrustManager (score math, violation
history), AgentSandboxManager (per-level configs, customize, cleanup) and
AgentSecurityManager (policy CRUD, workflow validation, execution
monitoring) — all against the real in-memory session.

The five defects these tests originally pinned strict-xfail were fixed in
#1315 (same branch): high-risk audit logging, trust-score datetime
normalization, JSON-safe policy audit state, the memory-limit comparison,
and change-tracked ``violation_history``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.agent_coordination.domain.agent import (
    AIAgentWorkflow,
    VerificationLevel,
)
from coordinator_api.contexts.agent_coordination.services.security import (
    AgentAuditLog,
    AgentAuditor,
    AgentSandboxConfig,
    AgentTrustScore,
    AgentSandboxManager,
    AgentSecurityManager,
    AgentTrustManager,
    AuditEventType,
    SecurityLevel,
)


def _auditor(session: Session) -> AgentAuditor:
    return AgentAuditor(session)


def _seed_workflow(
    session: Session,
    owner_id: str = "owner-1",
    **kwargs: Any,
) -> AIAgentWorkflow:
    wf = AIAgentWorkflow(
        owner_id=owner_id,
        name="wf",
        steps=kwargs.pop("steps", {"s1": {"name": "step-one", "step_type": "inference"}}),
        **kwargs,
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf


class TestAuditLogEvent:
    async def test_low_risk_event_persists(self, db_session: Session) -> None:
        log = await _auditor(db_session).log_event(
            AuditEventType.WORKFLOW_CREATED,
            workflow_id="wf1",
            user_id="u1",
            security_level=SecurityLevel.PUBLIC,
            event_data={"k": "v"},
        )
        assert log.id.startswith("audit_")
        row = db_session.get(AgentAuditLog, log.id)
        assert row is not None
        assert row.event_type == AuditEventType.WORKFLOW_CREATED
        assert row.risk_score == 5  # WORKFLOW_CREATED base 5 × PUBLIC 1.0
        assert row.cryptographic_hash
        assert row.signature_valid is None
        assert row.requires_investigation is False

    async def test_risk_score_multipliers_and_bonuses(self, db_session: Session) -> None:
        auditor = _auditor(db_session)
        # INTERNAL ×1.2 on EXECUTION_STARTED base 3 -> int(3.6)=3
        log = await auditor.log_event(AuditEventType.EXECUTION_STARTED, security_level=SecurityLevel.INTERNAL)
        assert log.risk_score == 3
        # CONFIDENTIAL ×1.5 on VERIFICATION_FAILED base 50 -> 75 -> triggers investigation path
        # (high-risk handling has its own defect pin; use a mid-range event instead)
        log2 = await auditor.log_event(
            AuditEventType.STEP_FAILED,  # base 20
            security_level=SecurityLevel.CONFIDENTIAL,  # ×1.5 -> 30
            event_data={"error_message": "x"},  # +10 -> 40
        )
        assert log2.risk_score == 40
        assert log2.requires_investigation is False

    def test_risk_score_caps_and_bonuses(self, db_session: Session) -> None:
        # Pure-function check: a >=70 score would route into the broken
        # _handle_high_risk_event path (pinned below), so assert the score
        # math directly instead of going through log_event.
        auditor = _auditor(db_session)
        score = auditor._calculate_risk_score(
            AuditEventType.EXECUTION_FAILED,  # base 30
            {"error_message": "e", "execution_time": 4000, "memory_usage": 9000},  # +10+5+5
            SecurityLevel.RESTRICTED,  # ×2.0 -> 60+20 = 80
        )
        assert score == 80
        # cap check: SANDBOX_BREACH 85 × RESTRICTED 2.0 = 170 -> capped at 100
        assert auditor._calculate_risk_score(AuditEventType.SANDBOX_BREACH, {}, SecurityLevel.RESTRICTED) == 100

    async def test_event_hash_is_canonical(self, db_session: Session) -> None:
        auditor = _auditor(db_session)
        h1 = auditor._generate_event_hash({"a": 1, "b": {"x": 1, "y": 2}})
        h2 = auditor._generate_event_hash({"b": {"y": 2, "x": 1}, "a": 1})
        assert h1 == h2 and len(h1) == 64
        assert auditor._generate_event_hash({}) == ""

    async def test_verify_signature_returns_none_without_keys(self, db_session: Session) -> None:
        auditor = _auditor(db_session)
        assert auditor._verify_signature({}) is None
        assert auditor._verify_signature({"signature": "s"}) is None  # no public_key -> None

    async def test_high_risk_event_logs_and_flags(self, db_session: Session) -> None:
        log = await _auditor(db_session).log_event(
            AuditEventType.SECURITY_VIOLATION,
            execution_id="exec-1",
            security_level=SecurityLevel.INTERNAL,
            event_data={"what": "attempted escape"},
        )
        assert log.risk_score >= 70
        db_session.expire_all()
        row = db_session.get(AgentAuditLog, log.id)
        assert row is not None
        assert row.investigation_notes is not None


class TestTrustManager:
    async def test_first_success_creates_score(self, db_session: Session) -> None:
        tm = AgentTrustManager(db_session)
        score = await tm.update_trust_score("agent", "ag-1", execution_success=True, execution_time=1.5)
        assert score.total_executions == 1
        assert score.successful_executions == 1
        assert score.failed_executions == 0
        assert score.verification_success_rate == 100.0
        assert score.average_execution_time == 1.5
        # 50 + (1.0-0.5)*40 = 70, no violations, last_execution unset during calc
        assert score.trust_score == pytest.approx(70.0)
        assert score.reputation_score == pytest.approx(60.01)  # 50 + 0.01 volume + 10 clean

    async def test_accumulates_and_running_mean(self, db_session: Session) -> None:
        tm = AgentTrustManager(db_session)
        await tm.update_trust_score("agent", "ag-1", True, execution_time=2.0)
        await tm.update_trust_score("agent", "ag-1", False, execution_time=4.0)
        score = await tm.update_trust_score("agent", "ag-1", True, execution_time=6.0)
        assert score.total_executions == 3
        assert score.successful_executions == 2
        assert score.failed_executions == 1
        # running mean of 2,4,6
        assert score.average_execution_time == pytest.approx(4.0)
        assert score.verification_success_rate == pytest.approx(200 / 3)

    async def test_security_violation_penalizes(self, db_session: Session) -> None:
        # Single-call variant: a second update for the same entity hits the
        # naive/aware datetime defect pinned above.
        tm = AgentTrustManager(db_session)
        score = await tm.update_trust_score("agent", "ag-1", execution_success=False, security_violation=True)
        assert score.security_violations == 1
        assert score.last_violation is not None
        # 50 + (0-0.5)*40 - 10 = 20; last_execution unset during first calc
        assert score.trust_score == pytest.approx(20.0)
        assert score.failed_executions == 1

    async def test_violation_history_persists_on_create(self, db_session: Session) -> None:
        """First write is an INSERT, so the mutated list does persist. The
        update-path loss (plain JSON column, untracked append) is real but
        unreachable today — every second update_trust_score dies earlier on
        the naive/aware datetime defect pinned above."""
        tm = AgentTrustManager(db_session)
        score = await tm.update_trust_score("agent", "ag-1", execution_success=False, security_violation=True)
        db_session.expire_all()
        row = db_session.get(type(score), score.id)
        assert row is not None
        assert len(row.violation_history) == 1
        assert row.violation_history[0]["type"] == "security_violation"

    async def test_entity_scoping(self, db_session: Session) -> None:
        # One update per entity (a second update hits the datetime defect);
        # verify the rows are distinct and independently scored.
        tm = AgentTrustManager(db_session)
        await tm.update_trust_score("agent", "ag-1", True)
        await tm.update_trust_score("user", "ag-1", False)
        rows = db_session.scalars(select(AgentTrustScore).where(AgentTrustScore.entity_id == "ag-1")).all()
        by_type = {r.entity_type: r for r in rows}
        assert by_type["agent"].successful_executions == 1
        assert by_type["agent"].failed_executions == 0
        assert by_type["user"].successful_executions == 0
        assert by_type["user"].failed_executions == 1


class TestSandboxManager:
    async def test_security_level_selects_config(self, db_session: Session) -> None:
        sm = AgentSandboxManager(db_session)
        pub = await sm.create_sandbox_environment("e1", SecurityLevel.PUBLIC)
        restricted = await sm.create_sandbox_environment("e2", SecurityLevel.RESTRICTED)
        assert pub.sandbox_type == "process" and pub.network_access is False
        assert restricted.sandbox_type == "vm" and restricted.network_access is True
        assert restricted.memory_limit == 8192
        row = db_session.get(AgentSandboxConfig, "sandbox_e1")
        assert row is not None and row.is_active is True

    async def test_customize_raises_floors_lowers_time(self, db_session: Session) -> None:
        sm = AgentSandboxManager(db_session)
        base = sm._get_sandbox_config(SecurityLevel.PUBLIC)
        custom = sm._customize_sandbox(
            base,
            {
                "cpu_cores": 4.0,  # raises cpu_limit 1.0 -> 4.0
                "memory_mb": 512,  # below floor -> stays 1024
                "max_execution_time": 60,  # lowers 3600 -> 60
                "network_access": True,  # OR -> True
                "allowed_commands": ["gcc"],
            },
        )
        assert custom["cpu_limit"] == 4.0
        assert custom["memory_limit"] == 1024
        assert custom["max_execution_time"] == 60
        assert custom["network_access"] is True
        assert "gcc" in custom["allowed_commands"]

    async def test_monitor_missing_raises_value_error(self, db_session: Session) -> None:
        sm = AgentSandboxManager(db_session)
        with pytest.raises(ValueError, match="Sandbox not found"):
            await sm.monitor_sandbox("nope")

    async def test_monitor_existing_raises_not_implemented(self, db_session: Session) -> None:
        """Documents the deliberate 501 contract (router maps to 501)."""
        sm = AgentSandboxManager(db_session)
        await sm.create_sandbox_environment("e-mon")
        with pytest.raises(NotImplementedError):
            await sm.monitor_sandbox("e-mon")

    async def test_cleanup_marks_inactive(self, db_session: Session) -> None:
        sm = AgentSandboxManager(db_session)
        await sm.create_sandbox_environment("e-clean")
        assert await sm.cleanup_sandbox("e-clean") is True
        row = db_session.get(AgentSandboxConfig, "sandbox_e-clean")
        assert row is not None and row.is_active is False
        assert await sm.cleanup_sandbox("e-clean") is True  # idempotent-ish: still finds row
        assert await sm.cleanup_sandbox("missing") is False


class TestSecurityManager:
    async def test_create_policy_persists_and_audits(self, db_session: Session) -> None:
        mgr = AgentSecurityManager(db_session)
        policy = await mgr.create_security_policy(
            "strict", "desc", SecurityLevel.CONFIDENTIAL, {"require_sandbox": True, "max_memory_usage": 2048}
        )
        assert policy.id.startswith("policy_")
        assert policy.require_sandbox is True
        row = db_session.get(type(policy), policy.id)
        assert row is not None
        events = db_session.scalars(select(AgentAuditLog)).all()
        assert any(e.event_type == AuditEventType.WORKFLOW_CREATED for e in events)

    async def test_validate_by_id_missing_and_ownership(self, db_session: Session) -> None:
        mgr = AgentSecurityManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            await mgr.validate_workflow_security_by_id("wf_missing", "owner-1")
        wf = _seed_workflow(db_session, owner_id="owner-1")
        with pytest.raises(PermissionError):
            await mgr.validate_workflow_security_by_id(wf.id, "intruder")
        result = await mgr.validate_workflow_security_by_id(wf.id, "owner-1")
        assert result["valid"] is True

    async def test_validate_security_levels_and_violations(self, db_session: Session) -> None:
        mgr = AgentSecurityManager(db_session)
        # requires_verification=False -> violation, valid False
        wf_bad = _seed_workflow(db_session, requires_verification=False)
        result = await mgr.validate_workflow_security(wf_bad, "owner-1")
        assert result["valid"] is False
        assert any("verification" in v for v in result["violations"])
        # ZK level -> RESTRICTED required
        wf_zk = _seed_workflow(db_session, requires_verification=True, verification_level=VerificationLevel.ZERO_KNOWLEDGE)
        result = await mgr.validate_workflow_security(wf_zk, "owner-1")
        assert result["required_security_level"] == SecurityLevel.RESTRICTED
        # sensitive step types -> warning
        wf_sens = _seed_workflow(
            db_session,
            steps={"s1": {"name": "train", "step_type": "training"}},
        )
        result = await mgr.validate_workflow_security(wf_sens, "owner-1")
        assert result["warnings"]
        # long execution -> warning
        wf_long = _seed_workflow(db_session, max_execution_time=7200)
        result = await mgr.validate_workflow_security(wf_long, "owner-1")
        assert any("execution time" in w for w in result["warnings"])

    async def test_monitor_execution_no_sandbox_is_monitoring_failed(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """monitor_sandbox raises ValueError for missing sandbox -> caught ->
        monitoring_failed. Auditor is mocked to isolate the monitor contract;
        the real audit path is covered by the next test."""
        mgr = AgentSecurityManager(db_session)
        monkeypatch.setattr(mgr.auditor, "log_event", AsyncMock())
        result = await mgr.monitor_execution_security("exec-x", "wf-x")
        assert result["security_status"] == "monitoring_failed"
        assert result["alerts"]

    async def test_monitor_execution_audit_path_is_real(self, db_session: Session) -> None:
        """Same missing-sandbox path but with the REAL auditor — the
        SECURITY_VIOLATION audit write inside the except handler must not
        break the monitoring_failed return (#1315 defect chain)."""
        mgr = AgentSecurityManager(db_session)
        result = await mgr.monitor_execution_security("exec-x", "wf-x")
        assert result["security_status"] == "monitoring_failed"
        events = db_session.scalars(select(AgentAuditLog)).all()
        assert any(e.event_type == AuditEventType.SECURITY_VIOLATION for e in events)

    async def test_monitor_memory_below_limit_is_clean(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        """No memory_limit_mb key -> check skipped; tiny usage -> clean."""
        mgr = AgentSecurityManager(db_session)
        monkeypatch.setattr(mgr.auditor, "log_event", AsyncMock())
        monkeypatch.setattr(
            mgr.sandbox_manager,
            "monitor_sandbox",
            AsyncMock(
                return_value={
                    "resource_usage": {"cpu_percent": 1.0, "memory_mb": 1.0},
                    "security_events": [],
                }
            ),
        )
        result = await mgr.monitor_execution_security("exec-y", "wf-y")
        assert "High memory usage detected" not in result["violations"]
        assert result["security_status"] == "secure"

    async def test_monitor_memory_alert_fires_above_limit(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = AgentSecurityManager(db_session)
        monkeypatch.setattr(mgr.auditor, "log_event", AsyncMock())
        monkeypatch.setattr(
            mgr.sandbox_manager,
            "monitor_sandbox",
            AsyncMock(
                return_value={
                    "resource_usage": {"cpu_percent": 50.0, "memory_mb": 950.0, "memory_limit_mb": 1024.0},
                    "security_events": [],
                }
            ),
        )
        result = await mgr.monitor_execution_security("exec-y", "wf-y")
        assert "High memory usage detected" in result["violations"]
        assert result["security_status"] == "violations_detected"

    async def test_monitor_memory_alert_respects_limit(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = AgentSecurityManager(db_session)
        monkeypatch.setattr(mgr.auditor, "log_event", AsyncMock())
        monkeypatch.setattr(
            mgr.sandbox_manager,
            "monitor_sandbox",
            AsyncMock(
                return_value={
                    "resource_usage": {"cpu_percent": 50.0, "memory_mb": 100.0, "memory_limit_mb": 8192.0},
                    "security_events": [],
                }
            ),
        )
        result = await mgr.monitor_execution_security("exec-y", "wf-y")
        assert "High memory usage detected" not in result["violations"]
        assert result["security_status"] == "secure"

    async def test_monitor_cpu_and_security_events(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = AgentSecurityManager(db_session)
        monkeypatch.setattr(mgr.auditor, "log_event", AsyncMock())
        monkeypatch.setattr(
            mgr.sandbox_manager,
            "monitor_sandbox",
            AsyncMock(
                return_value={
                    "resource_usage": {"cpu_percent": 95.0, "memory_mb": 100.0},
                    "security_events": ["suspicious syscall"],
                }
            ),
        )
        result = await mgr.monitor_execution_security("exec-z", "wf-z")
        assert result["security_status"] == "violations_detected"
        assert "High CPU usage detected" in result["violations"]
        assert "suspicious syscall" in result["violations"]
