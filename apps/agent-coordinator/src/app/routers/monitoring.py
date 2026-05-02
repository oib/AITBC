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

# Monitoring and metrics endpoints
@router.get("/metrics")
async def get_prometheus_metrics():
    """Get metrics in Prometheus format"""
    try:
        metrics = metrics_registry.get_all_metrics()
        
        # Convert to Prometheus text format
        prometheus_output = []
        
        for name, metric_data in metrics.items():
            prometheus_output.append(f"# HELP {name} {metric_data['description']}")
            prometheus_output.append(f"# TYPE {name} {metric_data['type']}")
            
            if metric_data['type'] == 'counter':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f"{name}{{{labels}}} {value}")
                    else:
                        prometheus_output.append(f"{name} {value}")
            
            elif metric_data['type'] == 'gauge':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f"{name}{{{labels}}} {value}")
                    else:
                        prometheus_output.append(f"{name} {value}")
            
            elif metric_data['type'] == 'histogram':
                for key, count in metric_data['counts'].items():
                    prometheus_output.append(f"{name}_count{{{key}}} {count}")
                for key, sum_val in metric_data['sums'].items():
                    prometheus_output.append(f"{name}_sum{{{key}}} {sum_val}")
        
        return Response(
            content="\n".join(prometheus_output),
            media_type="text/plain"
        )
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/summary")
async def get_metrics_summary():
    """Get metrics summary for dashboard"""
    try:
        summary = performance_monitor.get_performance_summary()
        
        # Add additional system metrics
        system_metrics = {
            "total_agents": len(state.agent_registry.agents) if state.agent_registry else 0,
            "active_agents": len([a for a in state.agent_registry.agents.values() if getattr(a, 'is_active', True)]) if state.agent_registry else 0,
            "total_tasks": len(state.task_distributor.task_queue._queue) if state.task_distributor and hasattr(state.task_distributor, 'task_queue') else 0,
            "load_balancer_strategy": state.load_balancer.strategy.value if state.load_balancer else "unknown"
        }
        
        return {
            "status": "success",
            "performance": summary,
            "system": system_metrics,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/health")
async def get_health_metrics():
    """Get health metrics for monitoring"""
    try:
        # Get system health metrics
        import psutil
        
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        # Update performance monitor with system metrics
        performance_monitor.update_system_metrics(memory.used, cpu)
        
        health_metrics = {
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percentage": memory.percent
            },
            "cpu": {
                "percentage": cpu,
                "count": psutil.cpu_count()
            },
            "uptime": performance_monitor.get_performance_summary()["uptime_seconds"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return {
            "status": "success",
            "health": health_metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting health metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
