"""
Agent Integration and Deployment API Router for Verifiable AI Agent Orchestration
Provides REST API endpoints for production deployment and integration management
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from app.domain.agent import AgentExecution, AIAgentWorkflow, VerificationLevel

from ..deps import require_admin_key
from ..services.agent_integration import (
    AgentDeploymentConfig,
    AgentDeploymentInstance,
    AgentDeploymentManager,
    AgentIntegrationManager,
    AgentMonitoringManager,
    AgentProductionManager,
    DeploymentStatus,
)
from ..storage import get_session
from ..utils.alerting import alert_dispatcher  # type: ignore[import-not-found]

logger = get_logger(__name__)

router = APIRouter(prefix="/agents/integration", tags=["Agent Integration"])


@router.post("/deployments/config", response_model=AgentDeploymentConfig)
@rate_limit(rate=50, per=60)
async def create_deployment_config(
    request: Request,
    workflow_id: str,
    deployment_name: str,
    deployment_config: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentDeploymentConfig:
    """Create deployment configuration for agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        deployment_manager = AgentDeploymentManager(session)
        config = await deployment_manager.create_deployment_config(
            workflow_id=workflow_id, deployment_name=deployment_name, deployment_config=deployment_config
        )
        logger.info("Deployment config created by %s", current_user)
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create deployment config: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create deployment config") from e


@router.get("/deployments/configs", response_model=list[AgentDeploymentConfig])
@rate_limit(rate=200, per=60)
async def list_deployment_configs(
    request: Request,
    workflow_id: str | None = None,
    status: DeploymentStatus | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentDeploymentConfig]:
    """List deployment configurations with filtering"""
    try:
        query = select(AgentDeploymentConfig)
        if workflow_id:
            query = query.where(AgentDeploymentConfig.workflow_id == workflow_id)
        if status:
            query = query.where(AgentDeploymentConfig.status == status)
        configs = session.exec(query).all()
        user_configs = []
        for config in configs:
            workflow = session.get(AIAgentWorkflow, config.workflow_id)
            if workflow and workflow.owner_id == current_user:
                user_configs.append(config)
        return user_configs
    except Exception as e:
        logger.error("Failed to list deployment configs: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/deployments/configs/{config_id}", response_model=AgentDeploymentConfig)
@rate_limit(rate=200, per=60)
async def get_deployment_config(
    request: Request,
    config_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentDeploymentConfig:
    """Get specific deployment configuration"""
    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get deployment config: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/deployments/{config_id}/deploy")
@rate_limit(rate=50, per=60)
async def deploy_workflow(
    request: Request,
    config_id: str,
    target_environment: str = "production",
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Deploy agent workflow to target environment"""
    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        deployment_manager = AgentDeploymentManager(session)
        deployment_result = await deployment_manager.deploy_agent_workflow(
            deployment_config_id=config_id, target_environment=target_environment
        )
        logger.info("Workflow deployed: %s to %s by %s", config_id, target_environment, current_user)
        return deployment_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to deploy workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/deployments/{config_id}/health")
@rate_limit(rate=200, per=60)
async def get_deployment_health(
    request: Request,
    config_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get health status of deployment"""
    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        deployment_manager = AgentDeploymentManager(session)
        health_result = await deployment_manager.monitor_deployment_health(config_id)
        return health_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get deployment health: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/deployments/{config_id}/scale")
@rate_limit(rate=50, per=60)
async def scale_deployment(
    request: Request,
    config_id: str,
    target_instances: int,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Scale deployment to target number of instances"""
    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        deployment_manager = AgentDeploymentManager(session)
        scaling_result = await deployment_manager.scale_deployment(
            deployment_config_id=config_id, target_instances=target_instances
        )
        logger.info("Deployment scaled: %s to %s instances by %s", config_id, target_instances, current_user)
        return scaling_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to scale deployment: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/deployments/{config_id}/rollback")
@rate_limit(rate=50, per=60)
async def rollback_deployment(
    request: Request,
    config_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Rollback deployment to previous version"""
    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        deployment_manager = AgentDeploymentManager(session)
        rollback_result = await deployment_manager.rollback_deployment(config_id)
        logger.info("Deployment rolled back: %s by %s", config_id, current_user)
        return rollback_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rollback deployment: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/deployments/instances", response_model=list[AgentDeploymentInstance])
@rate_limit(rate=200, per=60)
async def list_deployment_instances(
    request: Request,
    deployment_id: str | None = None,
    environment: str | None = None,
    status: DeploymentStatus | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentDeploymentInstance]:
    """List deployment instances with filtering"""
    try:
        query = select(AgentDeploymentInstance)
        if deployment_id:
            query = query.where(AgentDeploymentInstance.deployment_id == deployment_id)
        if environment:
            query = query.where(AgentDeploymentInstance.environment == environment)
        if status:
            query = query.where(AgentDeploymentInstance.status == status)
        instances = session.exec(query).all()
        user_instances = []
        for instance in instances:
            config = session.get(AgentDeploymentConfig, instance.deployment_id)
            if config:
                workflow = session.get(AIAgentWorkflow, config.workflow_id)
                if workflow and workflow.owner_id == current_user:
                    user_instances.append(instance)
        return user_instances
    except Exception as e:
        logger.error("Failed to list deployment instances: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/deployments/instances/{instance_id}", response_model=AgentDeploymentInstance)
@rate_limit(rate=200, per=60)
async def get_deployment_instance(
    request: Request,
    instance_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentDeploymentInstance:
    """Get specific deployment instance"""
    try:
        instance = session.get(AgentDeploymentInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        config = session.get(AgentDeploymentConfig, instance.deployment_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        return instance
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get deployment instance: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/integrations/zk/{execution_id}")
@rate_limit(rate=50, per=60)
async def integrate_with_zk_system(
    request: Request,
    execution_id: str,
    verification_level: VerificationLevel = VerificationLevel.BASIC,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Integrate agent execution with ZK proof system"""
    try:
        execution = session.get(AgentExecution, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        workflow = session.get(AIAgentWorkflow, execution.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        integration_manager = AgentIntegrationManager(session)
        integration_result = await integration_manager.integrate_with_zk_system(
            execution_id=execution_id, verification_level=verification_level
        )
        logger.info("ZK integration completed: %s by %s", execution_id, current_user)
        return integration_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to integrate with ZK system: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics/deployments/{deployment_id}")
@rate_limit(rate=200, per=60)
async def get_deployment_metrics(
    request: Request,
    deployment_id: str,
    time_range: str = "1h",
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get metrics for deployment over time range"""
    try:
        config = session.get(AgentDeploymentConfig, deployment_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        monitoring_manager = AgentMonitoringManager(session)
        metrics = await monitoring_manager.get_deployment_metrics(deployment_config_id=deployment_id, time_range=time_range)
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get deployment metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/production/deploy")
@rate_limit(rate=50, per=60)
async def deploy_to_production(
    request: Request,
    workflow_id: str,
    deployment_config: dict[str, Any],
    integration_config: dict[str, Any] | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Deploy agent workflow to production with full integration"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        production_manager = AgentProductionManager(session)
        production_result = await production_manager.deploy_to_production(
            workflow_id=workflow_id, deployment_config=deployment_config, integration_config=integration_config
        )
        logger.info("Production deployment completed: %s by %s", workflow_id, current_user)
        return production_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to deploy to production: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/production/dashboard")
@rate_limit(rate=200, per=60)
async def get_production_dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get comprehensive production dashboard data"""
    try:
        user_configs = session.exec(
            select(AgentDeploymentConfig).join(AIAgentWorkflow).where(AIAgentWorkflow.owner_id == current_user)
        ).all()
        dashboard_data: dict[str, Any] = {
            "total_deployments": len(user_configs),
            "active_deployments": len([c for c in user_configs if c.status == DeploymentStatus.DEPLOYED]),
            "failed_deployments": len([c for c in user_configs if c.status == DeploymentStatus.FAILED]),
            "deployments": [],
        }
        for config in user_configs:
            instances = session.exec(
                select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == config.id)
            ).all()
            try:
                monitoring_manager = AgentMonitoringManager(session)
                metrics = await monitoring_manager.get_deployment_metrics(config.id)
            except Exception:
                metrics = {"aggregated_metrics": {}}
            dashboard_data["deployments"].append(
                {
                    "deployment_id": config.id,
                    "deployment_name": config.deployment_name,
                    "workflow_id": config.workflow_id,
                    "status": config.status,
                    "total_instances": len(instances),
                    "healthy_instances": len([i for i in instances if i.health_status == "healthy"]),
                    "metrics": metrics["aggregated_metrics"],
                    "created_at": config.created_at.isoformat(),
                    "deployment_time": config.deployment_time.isoformat() if config.deployment_time else None,
                }
            )
        return dashboard_data
    except Exception as e:
        logger.error("Failed to get production dashboard: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/production/health")
@rate_limit(rate=200, per=60)
async def get_production_health(
    request: Request,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get overall production health status"""
    try:
        user_configs = session.exec(
            select(AgentDeploymentConfig).join(AIAgentWorkflow).where(AIAgentWorkflow.owner_id == current_user)
        ).all()
        health_status: dict[str, Any] = {
            "overall_health": "healthy",
            "total_deployments": len(user_configs),
            "healthy_deployments": 0,
            "unhealthy_deployments": 0,
            "unknown_deployments": 0,
            "total_instances": 0,
            "healthy_instances": 0,
            "unhealthy_instances": 0,
            "deployment_health": [],
        }
        for config in user_configs:
            try:
                deployment_manager = AgentDeploymentManager(session)
                deployment_health = await deployment_manager.monitor_deployment_health(config.id)
                health_status["deployment_health"].append(
                    {
                        "deployment_id": config.id,
                        "deployment_name": config.deployment_name,
                        "overall_health": deployment_health["overall_health"],
                        "healthy_instances": deployment_health["healthy_instances"],
                        "unhealthy_instances": deployment_health["unhealthy_instances"],
                        "total_instances": deployment_health["total_instances"],
                    }
                )
                health_status["total_instances"] += deployment_health["total_instances"]
                health_status["healthy_instances"] += deployment_health["healthy_instances"]
                health_status["unhealthy_instances"] += deployment_health["unhealthy_instances"]
                if deployment_health["overall_health"] == "healthy":
                    health_status["healthy_deployments"] += 1
                elif deployment_health["overall_health"] == "unhealthy":
                    health_status["unhealthy_deployments"] += 1
                else:
                    health_status["unknown_deployments"] += 1
            except Exception as e:
                logger.error("Health check failed for deployment %s: %s", config.id, e)
                health_status["unknown_deployments"] += 1
        if health_status["unhealthy_deployments"] > 0:
            health_status["overall_health"] = "unhealthy"
        elif health_status["unknown_deployments"] > 0:
            health_status["overall_health"] = "degraded"
        return health_status
    except Exception as e:
        logger.error("Failed to get production health: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/production/alerts")
@rate_limit(rate=200, per=60)
async def get_production_alerts(
    request: Request,
    severity: str | None = None,
    limit: int = 50,
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get production alerts and notifications"""
    try:
        alerts = alert_dispatcher.get_recent_alerts(severity=severity, limit=limit)
        return {"alerts": alerts, "total_count": len(alerts), "severity": severity, "source": "coordinator_metrics"}
    except Exception as e:
        logger.error("Failed to get production alerts: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
