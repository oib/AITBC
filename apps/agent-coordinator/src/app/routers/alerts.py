from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aitbc import get_logger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from .. import state
from ..auth.jwt_handler import api_key_manager, jwt_handler
from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Permission, Role, permission_manager
from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..consensus.distributed_consensus import distributed_consensus
from ..models import AgentRegistrationRequest, AgentStatusUpdate, MessageRequest, TaskSubmission
from ..monitoring.alerting import alert_manager
from ..monitoring.prometheus_metrics import metrics_registry, performance_monitor
from ..protocols.communication import MessageType, create_protocol
from ..protocols.message_types import create_task_message
from ..routing.agent_discovery import create_agent_info
from ..routing.load_balancer import LoadBalancingStrategy, TaskPriority

logger = get_logger(__name__)
router = APIRouter()

# Alerting endpoints
@router.get("/alerts")
async def get_alerts(
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get alerts with optional status filter"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        if status == "active":
            alerts = alert_manager.get_active_alerts()
        else:
            alerts = alert_manager.get_alert_history()
        
        return {
            "status": "success",
            "alerts": alerts,
            "total": len(alerts)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Resolve an alert"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = alert_manager.resolve_alert(alert_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts/stats")
async def get_alert_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get alert statistics"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        stats = alert_manager.get_alert_stats()
        
        return {
            "status": "success",
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts/rules")
async def get_alert_rules(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get alert rules"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        rules = [rule.to_dict() for rule in alert_manager.rules.values()]
        
        return {
            "status": "success",
            "rules": rules,
            "total": len(rules)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# SLA monitoring endpoints
@router.get("/sla")
async def get_sla_status(
    sla_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get SLA status"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        if sla_id:
            sla_status = alert_manager.sla_monitor.get_sla_compliance(sla_id)
        else:
            sla_status = alert_manager.sla_monitor.get_all_sla_status()
        
        return {
            "status": "success",
            "sla": sla_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SLA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sla/{sla_id}/record")
async def record_sla_metric(
    sla_id: str,
    value: float,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Record SLA metric"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        alert_manager.sla_monitor.record_metric(sla_id, value)
        
        return {
            "status": "success",
            "message": f"SLA metric recorded for {sla_id}",
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording SLA metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# System status endpoint with monitoring
@router.get("/system/status")
async def get_system_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get comprehensive system status"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SYSTEM_HEALTH):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Get various status information
        performance = performance_monitor.get_performance_summary()
        alerts = alert_manager.get_active_alerts()
        sla_status = alert_manager.sla_monitor.get_all_sla_status()
        
        # Get system health
        import psutil
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        status = {
            "overall": "healthy" if len(alerts) == 0 else "degraded",
            "performance": performance,
            "alerts": {
                "active_count": len(alerts),
                "critical_count": len([a for a in alerts if a.get("severity") == "critical"]),
                "warning_count": len([a for a in alerts if a.get("severity") == "warning"])
            },
            "sla": {
                "overall_compliance": sla_status.get("overall_compliance", 100.0),
                "total_slas": sla_status.get("total_slas", 0)
            },
            "system": {
                "memory_usage": memory.percent,
                "cpu_usage": cpu,
                "uptime": performance["uptime_seconds"]
            },
            "services": {
                "agent_coordinator": "running",
                "agent_registry": "running" if state.agent_registry else "stopped",
                "load_balancer": "running" if state.load_balancer else "stopped",
                "task_distributor": "running" if state.task_distributor else "stopped"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
