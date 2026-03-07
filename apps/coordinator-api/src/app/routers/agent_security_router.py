from sqlalchemy.orm import Session
from typing import Annotated
"""
Agent Security API Router for Verifiable AI Agent Orchestration
Provides REST API endpoints for security management and auditing
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from aitbc.logging import get_logger

from ..domain.agent import (
    AIAgentWorkflow, AgentExecution, AgentStatus, VerificationLevel
)
from ..services.agent_security import (
    AgentSecurityManager, AgentAuditor, AgentTrustManager, AgentSandboxManager,
    SecurityLevel, AuditEventType, AgentSecurityPolicy, AgentTrustScore, AgentSandboxConfig,
    AgentAuditLog
)
from ..storage import get_session
from ..deps import require_admin_key
from sqlmodel import Session, select

logger = get_logger(__name__)

router = APIRouter(prefix="/agents/security", tags=["Agent Security"])


@router.post("/policies", response_model=AgentSecurityPolicy)
async def create_security_policy(
    name: str,
    description: str,
    security_level: SecurityLevel,
    policy_rules: dict,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create a new security policy"""
    
    try:
        security_manager = AgentSecurityManager(session)
        policy = await security_manager.create_security_policy(
            name=name,
            description=description,
            security_level=security_level,
            policy_rules=policy_rules
        )
        
        logger.info(f"Security policy created: {policy.id} by {current_user}")
        return policy
        
    except Exception as e:
        logger.error(f"Failed to create security policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies", response_model=List[AgentSecurityPolicy])
async def list_security_policies(
    security_level: Optional[SecurityLevel] = None,
    is_active: Optional[bool] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """List security policies with filtering"""
    
    try:
        query = select(AgentSecurityPolicy)
        
        if security_level:
            query = query.where(AgentSecurityPolicy.security_level == security_level)
        
        if is_active is not None:
            query = query.where(AgentSecurityPolicy.is_active == is_active)
        
        policies = session.execute(query).all()
        return policies
        
    except Exception as e:
        logger.error(f"Failed to list security policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies/{policy_id}", response_model=AgentSecurityPolicy)
async def get_security_policy(
    policy_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get a specific security policy"""
    
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        return policy
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get security policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/policies/{policy_id}", response_model=AgentSecurityPolicy)
async def update_security_policy(
    policy_id: str,
    policy_updates: dict,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Update a security policy"""
    
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        # Update policy fields
        for field, value in policy_updates.items():
            if hasattr(policy, field):
                setattr(policy, field, value)
        
        policy.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(policy)
        
        # Log policy update
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.WORKFLOW_UPDATED,
            user_id=current_user,
            security_level=policy.security_level,
            event_data={"policy_id": policy_id, "updates": policy_updates},
            new_state={"policy": policy.dict()}
        )
        
        logger.info(f"Security policy updated: {policy_id} by {current_user}")
        return policy
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update security policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/policies/{policy_id}")
async def delete_security_policy(
    policy_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Delete a security policy"""
    
    try:
        policy = session.get(AgentSecurityPolicy, policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        # Log policy deletion
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.WORKFLOW_DELETED,
            user_id=current_user,
            security_level=policy.security_level,
            event_data={"policy_id": policy_id, "policy_name": policy.name},
            previous_state={"policy": policy.dict()}
        )
        
        session.delete(policy)
        session.commit()
        
        logger.info(f"Security policy deleted: {policy_id} by {current_user}")
        return {"message": "Policy deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete security policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-workflow/{workflow_id}")
async def validate_workflow_security(
    workflow_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Validate workflow security requirements"""
    
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check ownership
        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        security_manager = AgentSecurityManager(session)
        validation_result = await security_manager.validate_workflow_security(
            workflow, current_user
        )
        
        return validation_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate workflow security: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs", response_model=List[AgentAuditLog])
async def list_audit_logs(
    event_type: Optional[AuditEventType] = None,
    workflow_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    user_id: Optional[str] = None,
    security_level: Optional[SecurityLevel] = None,
    requires_investigation: Optional[bool] = None,
    risk_score_min: Optional[int] = None,
    risk_score_max: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """List audit logs with filtering"""
    
    try:
        from ..services.agent_security import AgentAuditLog
        
        query = select(AgentAuditLog)
        
        # Apply filters
        if event_type:
            query = query.where(AgentAuditLog.event_type == event_type)
        if workflow_id:
            query = query.where(AgentAuditLog.workflow_id == workflow_id)
        if execution_id:
            query = query.where(AgentLog.execution_id == execution_id)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if security_level:
            query = query.where(AuditLog.security_level == security_level)
        if requires_investigation is not None:
            query = query.where(AuditLog.requires_investigation == requires_investigation)
        if risk_score_min is not None:
            query = query.where(AuditLog.risk_score >= risk_score_min)
        if risk_score_max is not None:
            query = query.where(AuditLog.risk_score <= risk_score_max)
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        query = query.order_by(AuditLog.timestamp.desc())
        
        audit_logs = session.execute(query).all()
        return audit_logs
        
    except Exception as e:
        logger.error(f"Failed to list audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs/{audit_id}", response_model=AgentAuditLog)
async def get_audit_log(
    audit_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get a specific audit log entry"""
    
    try:
        from ..services.agent_security import AgentAuditLog
        
        audit_log = session.get(AuditLog, audit_id)
        if not audit_log:
            raise HTTPException(status_code=404, detail="Audit log not found")
        
        return audit_log
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-scores")
async def list_trust_scores(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """List trust scores with filtering"""
    
    try:
        from ..services.agent_security import AgentTrustScore
        
        query = select(AgentTrustScore)
        
        # Apply filters
        if entity_type:
            query = query.where(AgentTrustScore.entity_type == entity_type)
        if entity_id:
            query = query.where(AgentTrustScore.entity_id == entity_id)
        if min_score is not None:
            query = query.where(AgentTrustScore.trust_score >= min_score)
        if max_score is not None:
            query = query.where(AgentTrustScore.trust_score <= max_score)
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        query = query.order_by(AgentTrustScore.trust_score.desc())
        
        trust_scores = session.execute(query).all()
        return trust_scores
        
    except Exception as e:
        logger.error(f"Failed to list trust scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-scores/{entity_type}/{entity_id}", response_model=AgentTrustScore)
async def get_trust_score(
    entity_type: str,
    entity_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get trust score for specific entity"""
    
    try:
        from ..services.agent_security import AgentTrustScore
        
        trust_score = session.execute(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == entity_type) &
                (AgentTrustScore.entity_id == entity_id)
            )
        ).first()
        
        if not trust_score:
            raise HTTPException(status_code=404, detail="Trust score not found")
        
        return trust_score
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trust score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trust-scores/{entity_type}/{entity_id}/update")
async def update_trust_score(
    entity_type: str,
    entity_id: str,
    execution_success: bool,
    execution_time: Optional[float] = None,
    security_violation: bool = False,
    policy_violation: bool = False,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Update trust score based on execution results"""
    
    try:
        trust_manager = AgentTrustManager(session)
        trust_score = await trust_manager.update_trust_score(
            entity_type=entity_type,
            entity_id=entity_id,
            execution_success=execution_success,
            execution_time=execution_time,
            security_violation=security_violation,
            policy_violation=policy_violation
        )
        
        # Log trust score update
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
                "policy_violation": policy_violation
            },
            new_state={"trust_score": trust_score.trust_score}
        )
        
        logger.info(f"Trust score updated: {entity_type}/{entity_id} -> {trust_score.trust_score}")
        return trust_score
        
    except Exception as e:
        logger.error(f"Failed to update trust score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sandbox/{execution_id}/create")
async def create_sandbox(
    execution_id: str,
    security_level: SecurityLevel = SecurityLevel.PUBLIC,
    workflow_requirements: Optional[dict] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create sandbox environment for agent execution"""
    
    try:
        sandbox_manager = AgentSandboxManager(session)
        sandbox = await sandbox_manager.create_sandbox_environment(
            execution_id=execution_id,
            security_level=security_level,
            workflow_requirements=workflow_requirements
        )
        
        # Log sandbox creation
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.EXECUTION_STARTED,
            execution_id=execution_id,
            user_id=current_user,
            security_level=security_level,
            event_data={
                "sandbox_id": sandbox.id,
                "sandbox_type": sandbox.sandbox_type,
                "security_level": sandbox.security_level
            }
        )
        
        logger.info(f"Sandbox created for execution {execution_id}")
        return sandbox
        
    except Exception as e:
        logger.error(f"Failed to create sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sandbox/{execution_id}/monitor")
async def monitor_sandbox(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Monitor sandbox execution for security violations"""
    
    try:
        sandbox_manager = AgentSandboxManager(session)
        monitoring_data = await sandbox_manager.monitor_sandbox(execution_id)
        
        return monitoring_data
        
    except Exception as e:
        logger.error(f"Failed to monitor sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sandbox/{execution_id}/cleanup")
async def cleanup_sandbox(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Clean up sandbox environment after execution"""
    
    try:
        sandbox_manager = AgentSandboxManager(session)
        success = await sandbox_manager.cleanup_sandbox(execution_id)
        
        # Log sandbox cleanup
        auditor = AgentAuditor(session)
        await auditor.log_event(
            AuditEventType.EXECUTION_COMPLETED if success else AuditEventType.EXECUTION_FAILED,
            execution_id=execution_id,
            user_id=current_user,
            security_level=SecurityLevel.PUBLIC,
            event_data={"sandbox_cleanup_success": success}
        )
        
        return {"success": success, "message": "Sandbox cleanup completed"}
        
    except Exception as e:
        logger.error(f"Failed to cleanup sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/security-monitor")
async def monitor_execution_security(
    execution_id: str,
    workflow_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Monitor execution for security violations"""
    
    try:
        security_manager = AgentSecurityManager(session)
        monitoring_result = await security_manager.monitor_execution_security(
            execution_id, workflow_id
        )
        
        return monitoring_result
        
    except Exception as e:
        logger.error(f"Failed to monitor execution security: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/security-dashboard")
async def get_security_dashboard(
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get comprehensive security dashboard data"""
    
    try:
        from ..services.agent_security import AgentAuditLog, AgentTrustScore, AgentSandboxConfig
        
        # Get recent audit logs
        recent_audits = session.execute(
            select(AgentAuditLog)
            .order_by(AgentAuditLog.timestamp.desc())
            .limit(50)
        ).all()
        
        # Get high-risk events
        high_risk_events = session.execute(
            select(AuditLog)
            .where(AuditLog.requires_investigation == True)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
        ).all()
        
        # Get trust score statistics
        trust_scores = session.execute(select(ActivityTrustScore)).all()
        avg_trust_score = sum(ts.trust_score for ts in trust_scores) / len(trust_scores) if trust_scores else 0
        
        # Get active sandboxes
        active_sandboxes = session.execute(
            select(AgentSandboxConfig)
            .where(AgentSandboxConfig.is_active == True)
        ).all()
        
        # Get security statistics
        total_audits = session.execute(select(AuditLog)).count()
        high_risk_count = session.execute(
            select(AuditLog).where(AuditLog.requires_investigation == True)
        ).count()
        
        security_violations = session.execute(
            select(AuditLog).where(AuditLog.event_type == AuditEventType.SECURITY_VIOLATION)
        ).count()
        
        return {
            "recent_audits": recent_audits,
            "high_risk_events": high_risk_events,
            "trust_score_stats": {
                "average_score": avg_trust_score,
                "total_entities": len(trust_scores),
                "high_trust_entities": len([ts for ts in trust_scores if ts.trust_score >= 80]),
                "low_trust_entities": len([ts for ts in trust_scores if ts.trust_score < 20])
            },
            "active_sandboxes": len(active_sandboxes),
            "security_stats": {
                "total_audits": total_audits,
                "high_risk_count": high_risk_count,
                "security_violations": security_violations,
                "risk_rate": (high_risk_count / total_audits * 100) if total_audits > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get security dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/security-stats")
async def get_security_statistics(
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get security statistics and metrics"""
    
    try:
        from ..services.agent_security import AgentAuditLog, AgentTrustScore, AgentSandboxConfig
        
        # Audit statistics
        total_audits = session.execute(select(AuditLog)).count()
        event_type_counts = {}
        for event_type in AuditEventType:
            count = session.execute(
                select(AuditLog).where(AuditLog.event_type == event_type)
            ).count()
            event_type_counts[event_type.value] = count
        
        # Risk score distribution
        risk_score_distribution = {
            "low": 0,    # 0-30
            "medium": 0,  # 31-70
            "high": 0,    # 71-100
            "critical": 0  # 90-100
        }
        
        all_audits = session.execute(select(AuditLog)).all()
        for audit in all_audits:
            if audit.risk_score <= 30:
                risk_score_distribution["low"] += 1
            elif audit.risk_score <= 70:
                risk_score_distribution["medium"] += 1
            elif audit.risk_score <= 90:
                risk_score_distribution["high"] += 1
            else:
                risk_score_distribution["critical"] += 1
        
        # Trust score statistics
        trust_scores = session.execute(select(AgentTrustScore)).all()
        trust_score_distribution = {
            "very_low": 0,    # 0-20
            "low": 0,        # 21-40
            "medium": 0,      # 41-60
            "high": 0,        # 61-80
            "very_high": 0     # 81-100
        }
        
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
                "risk_score_distribution": risk_score_distribution
            },
            "trust_statistics": {
                "total_entities": len(trust_scores),
                "average_trust_score": sum(ts.trust_score for ts in trust_scores) / len(trust_scores) if trust_scores else 0,
                "trust_score_distribution": trust_score_distribution
            },
            "security_health": {
                "high_risk_rate": (risk_score_distribution["high"] + risk_score_distribution["critical"]) / total_audits * 100 if total_audits > 0 else 0,
                "average_risk_score": sum(audit.risk_score for audit in all_audits) / len(all_audits) if all_audits else 0,
                "security_violation_rate": (event_type_counts.get("security_violation", 0) / total_audits * 100) if total_audits > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get security statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
