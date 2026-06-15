from typing import Annotated

"\nAgent Security API Router for Verifiable AI Agent Orchestration\nProvides REST API endpoints for security management and auditing\n"
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)
from sqlalchemy import desc
from sqlmodel import Session, select

from app.domain.agent import AIAgentWorkflow

from ..deps import require_admin_key
from ..services.agent_security import (
    AgentAuditLog,
    AgentAuditor,
    AgentSandboxManager,
    AgentSecurityManager,
    AgentSecurityPolicy,
    AgentTrustManager,
    AgentTrustScore,
    AuditEventType,
    SecurityLevel,
)
from ..storage import get_session

router = APIRouter(prefix="/agents/security", tags=["Agent Security"])


@router.post("/policies", response_model=AgentSecurityPolicy)
@rate_limit(rate=50, per=60)
async def create_security_policy(
    request: Request,
    name: str,
    description: str,
    security_level: SecurityLevel,
    policy_rules: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentSecurityPolicy:
    """Create a new security policy"""
    try:
        security_manager = AgentSecurityManager(session)
        policy = await security_manager.create_security_policy(
            name=name, description=description, security_level=security_level, policy_rules=policy_rules
        )
        logger.info("Security policy created: %s by %s", policy.id, current_user)
        return policy
    except Exception as e:
        logger.error("Failed to create security policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies", response_model=list[AgentSecurityPolicy])
@rate_limit(rate=200, per=60)
async def list_security_policies(
    request: Request,
    security_level: SecurityLevel | None = None,
    is_active: bool | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentSecurityPolicy]:
    """List security policies with filtering"""
    try:
        query = select(AgentSecurityPolicy)
        if security_level:
            query = query.where(AgentSecurityPolicy.security_level == security_level)
        if is_active is not None:
            query = query.where(AgentSecurityPolicy.is_active == is_active)
        policies = list(session.exec(query).all())
        return policies
    except Exception as e:
        logger.error("Failed to list security policies: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/{policy_id}", response_model=AgentSecurityPolicy)
@rate_limit(rate=200, per=60)
async def get_security_policy(
    request: Request,
    policy_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentSecurityPolicy:
    """Get a specific security policy"""
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get security policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/policies/{policy_id}", response_model=AgentSecurityPolicy)
@rate_limit(rate=50, per=60)
async def update_security_policy(
    request: Request,
    policy_id: str,
    policy_updates: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentSecurityPolicy:
    """Update a security policy"""
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        for field, value in policy_updates.items():
            if hasattr(policy, field):
                setattr(policy, field, value)
        policy.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(policy)
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.WORKFLOW_UPDATED,
            user_id=current_user,
            security_level=policy.security_level,
            event_data={"policy_id": policy_id, "updates": policy_updates},
            new_state={"policy": policy.dict()},
        )
        logger.info("Security policy updated: %s by %s", policy_id, current_user)
        return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update security policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/policies/{policy_id}")
@rate_limit(rate=50, per=60)
async def delete_security_policy(
    request: Request,
    policy_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, str]:
    """Delete a security policy"""
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.WORKFLOW_DELETED,
            user_id=current_user,
            security_level=policy.security_level,
            event_data={"policy_id": policy_id, "policy_name": policy.name},
            previous_state={"policy": policy.dict()},
        )
        session.delete(policy)
        session.commit()
        logger.info("Security policy deleted: %s by %s", policy_id, current_user)
        return {"message": "Policy deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete security policy: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-workflow/{workflow_id}")
@rate_limit(rate=50, per=60)
async def validate_workflow_security(
    request: Request,
    workflow_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Validate workflow security requirements"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        security_manager = AgentSecurityManager(session)
        validation_result = await security_manager.validate_workflow_security(workflow, current_user)
        return validation_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to validate workflow security: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs", response_model=list[AgentAuditLog])
@rate_limit(rate=200, per=60)
async def list_audit_logs(
    request: Request,
    event_type: AuditEventType | None = None,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    user_id: str | None = None,
    security_level: SecurityLevel | None = None,
    requires_investigation: bool | None = None,
    risk_score_min: int | None = None,
    risk_score_max: int | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentAuditLog]:
    """List audit logs with filtering"""
    try:
        from ..services.agent_security import AgentAuditLog

        query = select(AgentAuditLog)
        if event_type:
            query = query.where(AgentAuditLog.event_type == event_type)
        if workflow_id:
            query = query.where(AgentAuditLog.workflow_id == workflow_id)
        if execution_id:
            query = query.where(AgentAuditLog.execution_id == execution_id)
        if user_id:
            query = query.where(AgentAuditLog.user_id == user_id)
        if security_level:
            query = query.where(AgentAuditLog.security_level == security_level)
        if requires_investigation is not None:
            query = query.where(AgentAuditLog.requires_investigation == requires_investigation)
        if risk_score_min is not None:
            query = query.where(AgentAuditLog.risk_score >= risk_score_min)
        if risk_score_max is not None:
            query = query.where(AgentAuditLog.risk_score <= risk_score_max)
        query = query.offset(offset).limit(limit)
        query = query.order_by(desc(AgentAuditLog.timestamp))  # type: ignore[arg-type]
        audit_logs = list(session.exec(query).all())
        return audit_logs
    except Exception as e:
        logger.error("Failed to list audit logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs/{audit_id}", response_model=AgentAuditLog)
@rate_limit(rate=200, per=60)
async def get_audit_log(
    request: Request,
    audit_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentAuditLog:
    """Get a specific audit log entry"""
    try:
        audit_log = session.get(AgentAuditLog, audit_id)
        if not audit_log:
            raise HTTPException(status_code=404, detail="Audit log not found")
        return audit_log
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get audit log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-scores")
@rate_limit(rate=200, per=60)
async def list_trust_scores(
    request: Request,
    entity_type: str | None = None,
    entity_id: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentTrustScore]:
    """List trust scores with filtering"""
    try:
        from ..services.agent_security import AgentTrustScore

        query = select(AgentTrustScore)
        if entity_type:
            query = query.where(AgentTrustScore.entity_type == entity_type)
        if entity_id:
            query = query.where(AgentTrustScore.entity_id == entity_id)
        if min_score is not None:
            query = query.where(AgentTrustScore.trust_score >= min_score)
        if max_score is not None:
            query = query.where(AgentTrustScore.trust_score <= max_score)
        query = query.offset(offset).limit(limit)
        query = query.order_by(desc(AgentTrustScore.trust_score))  # type: ignore[arg-type]
        trust_scores = list(session.exec(query).all())
        return trust_scores
    except Exception as e:
        logger.error("Failed to list trust scores: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-scores/{entity_type}/{entity_id}", response_model=AgentTrustScore)
@rate_limit(rate=200, per=60)
async def get_trust_score(
    request: Request,
    entity_type: str,
    entity_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentTrustScore:
    """Get trust score for specific entity"""
    try:
        from ..services.agent_security import AgentTrustScore

        trust_score = session.exec(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == entity_type) & (AgentTrustScore.entity_id == entity_id)
            )
        ).first()
        if not trust_score:
            raise HTTPException(status_code=404, detail="Trust score not found")
        return trust_score
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get trust score: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trust-scores/{entity_type}/{entity_id}/update")
@rate_limit(rate=50, per=60)
async def update_trust_score(
    request: Request,
    entity_type: str,
    entity_id: str,
    execution_success: bool,
    execution_time: float | None = None,
    security_violation: bool = False,
    policy_violation: bool = False,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentTrustScore:
    """Update trust score based on execution results"""
    try:
        trust_manager = AgentTrustManager(session)
        trust_score = await trust_manager.update_trust_score(
            entity_type=entity_type,
            entity_id=entity_id,
            execution_success=execution_success,
            execution_time=execution_time,
            security_violation=security_violation,
            policy_violation=policy_violation,
        )
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.EXECUTION_COMPLETED if execution_success else AuditEventType.EXECUTION_FAILED,
            user_id=current_user,
            security_level=SecurityLevel.PUBLIC,
            event_data={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "execution_success": execution_success,
                "execution_time": execution_time,
                "security_violation": security_violation,
                "policy_violation": policy_violation,
            },
            new_state={"trust_score": trust_score.trust_score},
        )
        logger.info("Trust score updated: %s/%s -> %s", entity_type, entity_id, trust_score.trust_score)
        return trust_score
    except Exception as e:
        logger.error("Failed to update trust score: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sandbox/{execution_id}/create")
@rate_limit(rate=50, per=60)
async def create_sandbox(
    request: Request,
    execution_id: str,
    security_level: SecurityLevel = SecurityLevel.PUBLIC,
    workflow_requirements: dict[str, Any] | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Create sandbox environment for agent execution"""
    try:
        sandbox_manager = AgentSandboxManager(session)
        sandbox = await sandbox_manager.create_sandbox_environment(
            execution_id=execution_id, security_level=security_level, workflow_requirements=workflow_requirements
        )
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.EXECUTION_STARTED,
            execution_id=execution_id,
            user_id=current_user,
            security_level=security_level,
            event_data={
                "sandbox_id": sandbox.id,
                "sandbox_type": sandbox.sandbox_type,
                "security_level": sandbox.security_level,
            },
        )
        logger.info("Sandbox created for execution %s", execution_id)
        return dict(sandbox)
    except Exception as e:
        logger.error("Failed to create sandbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sandbox/{execution_id}/monitor")
@rate_limit(rate=200, per=60)
async def monitor_sandbox(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Monitor sandbox execution for security violations"""
    try:
        sandbox_manager = AgentSandboxManager(session)
        monitoring_data = await sandbox_manager.monitor_sandbox(execution_id)
        return monitoring_data
    except Exception as e:
        logger.error("Failed to monitor sandbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sandbox/{execution_id}/cleanup")
@rate_limit(rate=50, per=60)
async def cleanup_sandbox(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Clean up sandbox environment after execution"""
    try:
        sandbox_manager = AgentSandboxManager(session)
        success = await sandbox_manager.cleanup_sandbox(execution_id)
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.EXECUTION_COMPLETED if success else AuditEventType.EXECUTION_FAILED,
            execution_id=execution_id,
            user_id=current_user,
            security_level=SecurityLevel.PUBLIC,
            event_data={"sandbox_cleanup_success": success},
        )
        return {"success": success, "message": "Sandbox cleanup completed"}
    except Exception as e:
        logger.error("Failed to cleanup sandbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/security-monitor")
@rate_limit(rate=50, per=60)
async def monitor_execution_security(
    request: Request,
    execution_id: str,
    workflow_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Monitor execution for security violations"""
    try:
        security_manager = AgentSecurityManager(session)
        monitoring_result = await security_manager.monitor_execution_security(execution_id, workflow_id)
        return monitoring_result
    except Exception as e:
        logger.error("Failed to monitor execution security: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/security-dashboard")
@rate_limit(rate=200, per=60)
async def get_security_dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get comprehensive security dashboard data"""
    try:
        from ..services.agent_security import AgentAuditLog, AgentSandboxConfig

        recent_audits = list(session.exec(select(AgentAuditLog).order_by(desc(AgentAuditLog.timestamp)).limit(50)).all())  # type: ignore[arg-type]
        high_risk_events = list(
            session.exec(
                select(AgentAuditLog)
                .where(AgentAuditLog.requires_investigation)
                .order_by(desc(AgentAuditLog.timestamp))
                .limit(10)
            ).all()
        )  # type: ignore[arg-type]
        trust_scores = list(session.exec(select(AgentTrustScore)).all())
        avg_trust_score = sum(ts.trust_score for ts in trust_scores) / len(trust_scores) if trust_scores else 0
        active_sandboxes = session.exec(select(AgentSandboxConfig).where(AgentSandboxConfig.is_active)).all()
        total_audits = len(session.exec(select(AgentAuditLog)).all())
        high_risk_count = len(session.exec(select(AgentAuditLog).where(AgentAuditLog.requires_investigation)).all())
        security_violations = len(
            session.exec(select(AgentAuditLog).where(AgentAuditLog.event_type == AuditEventType.SECURITY_VIOLATION)).all()
        )
        return {
            "recent_audits": recent_audits,
            "high_risk_events": high_risk_events,
            "trust_score_stats": {
                "average_score": avg_trust_score,
                "total_entities": len(trust_scores),
                "high_trust_entities": len([ts for ts in trust_scores if ts.trust_score >= 80]),
                "low_trust_entities": len([ts for ts in trust_scores if ts.trust_score < 20]),
            },
            "active_sandboxes": len(active_sandboxes),
            "security_stats": {
                "total_audits": total_audits,
                "high_risk_count": high_risk_count,
                "security_violations": security_violations,
                "risk_rate": high_risk_count / total_audits * 100 if total_audits > 0 else 0,
            },
        }
    except Exception as e:
        logger.error("Failed to get security dashboard: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/security-stats")
@rate_limit(rate=200, per=60)
async def get_security_statistics(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get security statistics and metrics"""
    try:
        from ..services.agent_security import AgentTrustScore

        total_audits = len(session.exec(select(AgentAuditLog)).all())
        event_type_counts = {}
        for event_type in AuditEventType:
            count = len(session.exec(select(AgentAuditLog).where(AgentAuditLog.event_type == event_type)).all())
            event_type_counts[event_type.value] = count
        risk_score_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        all_audits = session.exec(select(AgentAuditLog)).all()
        for audit in all_audits:
            if audit.risk_score <= 30:
                risk_score_distribution["low"] += 1
            elif audit.risk_score <= 70:
                risk_score_distribution["medium"] += 1
            elif audit.risk_score <= 90:
                risk_score_distribution["high"] += 1
            else:
                risk_score_distribution["critical"] += 1
        trust_scores = list(session.exec(select(AgentTrustScore)).all())
        trust_score_distribution = {"very_low": 0, "low": 0, "medium": 0, "high": 0, "very_high": 0}
        for trust_score in trust_scores:
            if trust_score.trust_score <= 20:
                trust_score_distribution["very_low"] += 1
            elif trust_score.trust_score <= 40:
                trust_score_distribution["low"] += 1
            elif trust_score.trust_score <= 60:
                trust_score_distribution["medium"] += 1
            elif trust_score.trust_score <= 80:
                trust_score_distribution["high"] += 1
            else:
                trust_score_distribution["very_high"] += 1
        return {
            "audit_statistics": {
                "total_audits": total_audits,
                "event_type_counts": event_type_counts,
                "risk_score_distribution": risk_score_distribution,
            },
            "trust_statistics": {
                "total_entities": len(trust_scores),
                "average_trust_score": sum(ts.trust_score for ts in trust_scores) / len(trust_scores) if trust_scores else 0,
                "trust_score_distribution": trust_score_distribution,
            },
            "security_health": {
                "high_risk_rate": (risk_score_distribution["high"] + risk_score_distribution["critical"]) / total_audits * 100
                if total_audits > 0
                else 0,
                "average_risk_score": sum(audit.risk_score for audit in all_audits) / len(all_audits) if all_audits else 0,
                "security_violation_rate": event_type_counts.get("security_violation", 0) / total_audits * 100
                if total_audits > 0
                else 0,
            },
        }
    except Exception as e:
        logger.error("Failed to get security statistics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
