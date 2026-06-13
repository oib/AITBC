# mypy: ignore-errors
from datetime import UTC, datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from .. import state
from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Role
from ..monitoring.prometheus_metrics import metrics_registry, performance_monitor
logger = get_logger(__name__)
router = APIRouter()

@router.get('/metrics')
@rate_limit(rate=1000, per=60)
async def get_prometheus_metrics(request: Request) -> Response:
    """Get metrics in Prometheus format"""
    try:
        metrics = metrics_registry.get_all_metrics()
        prometheus_output = []
        for name, metric_data in metrics.items():
            prometheus_output.append(f"# HELP {name} {metric_data['description']}")
            prometheus_output.append(f"# TYPE {name} {metric_data['type']}")
            if metric_data['type'] == 'counter':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f'{name}{{{labels}}} {value}')
                    else:
                        prometheus_output.append(f'{name} {value}')
            elif metric_data['type'] == 'gauge':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f'{name}{{{labels}}} {value}')
                    else:
                        prometheus_output.append(f'{name} {value}')
            elif metric_data['type'] == 'histogram':
                for key, count in metric_data['counts'].items():
                    prometheus_output.append(f'{name}_count{{{key}}} {count}')
                for key, sum_val in metric_data['sums'].items():
                    prometheus_output.append(f'{name}_sum{{{key}}} {sum_val}')
        return Response(content='\n'.join(prometheus_output), media_type='text/plain')
    except Exception as e:
        logger.error('Error getting metrics: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/metrics/summary')
@rate_limit(rate=500, per=60)
async def get_metrics_summary(request: Request) -> dict[str, Any]:
    """Get metrics summary for dashboard"""
    try:
        summary = performance_monitor.get_performance_summary()
        system_metrics = {'total_agents': len(state.agent_registry.agents) if state.agent_registry else 0, 'active_agents': len([a for a in state.agent_registry.agents.values() if getattr(a, 'is_active', True)]) if state.agent_registry else 0, 'total_tasks': len(state.task_distributor.task_queue._queue) if state.task_distributor and hasattr(state.task_distributor, 'task_queue') else 0, 'load_balancer_strategy': state.load_balancer.strategy.value if state.load_balancer else 'unknown'}
        return {'status': 'success', 'performance': summary, 'system': system_metrics, 'timestamp': datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error('Error getting metrics summary: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/metrics/health')
@rate_limit(rate=500, per=60)
async def get_health_metrics(request: Request) -> dict[str, Any]:
    """Get health metrics for monitoring"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        performance_monitor.update_system_metrics(memory.used, cpu)
        health_metrics = {'memory': {'total': memory.total, 'available': memory.available, 'used': memory.used, 'percentage': memory.percent}, 'cpu': {'percentage': cpu, 'count': psutil.cpu_count()}, 'uptime': performance_monitor.get_performance_summary()['uptime_seconds'], 'timestamp': datetime.now(UTC).isoformat()}
        return {'status': 'success', 'health': health_metrics}
    except Exception as e:
        logger.error('Error getting health metrics: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/system/status')
@rate_limit(rate=200, per=60)
async def get_system_status(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get system status (protected endpoint)"""
    try:
        system_metrics = {'total_agents': len(state.agent_registry.agents) if state.agent_registry else 0, 'active_agents': len([a for a in state.agent_registry.agents.values() if getattr(a, 'is_active', True)]) if state.agent_registry else 0, 'total_tasks': len(state.task_distributor.task_queue._queue) if state.task_distributor and hasattr(state.task_distributor, 'task_queue') else 0, 'load_balancer_strategy': state.load_balancer.strategy.value if state.load_balancer else 'unknown', 'timestamp': datetime.now(UTC).isoformat()}
        return {'status': 'success', 'system': system_metrics}
    except Exception as e:
        logger.error('Error getting system status: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/protected/admin')
@rate_limit(rate=200, per=60)
async def protected_admin(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Protected admin endpoint"""
    try:
        if current_user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin role required')
        return {'status': 'success', 'message': 'Admin access granted', 'user': current_user['username']}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error accessing protected admin endpoint: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/protected/operator')
@rate_limit(rate=200, per=60)
async def protected_operator(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Protected operator endpoint"""
    try:
        if current_user.get('role') not in ('admin', 'operator'):
            raise HTTPException(status_code=403, detail='Admin or operator role required')
        return {'status': 'success', 'message': 'Operator access granted', 'user': current_user['username']}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error accessing protected operator endpoint: %s', e)
        raise HTTPException(status_code=500, detail=str(e))