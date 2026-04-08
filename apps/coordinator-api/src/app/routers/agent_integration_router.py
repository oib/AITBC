from typing import Annotated

"""
Agent Integration and Deployment API Router for Verifiable AI Agent Orchestration
Provides REST API endpoints for production deployment and integration management
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

from sqlmodel import Session, select

from ..deps import require_admin_key
from ..domain.agent import AgentExecution, AIAgentWorkflow, VerificationLevel
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
from ..utils.alerting import alert_dispatcher

router = APIRouter(prefix="/agents/integration", tags=["Agent Integration"])


@router.post("/deployments/config", response_model=AgentDeploymentConfig)
async def create_deployment_config(
    workflow_id: str,
    deployment_name: str,
    deployment_config: dict,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Create deployment configuration for agent workflow"""

    try:
        # Verify workflow exists and user has access
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        deployment_manager = AgentDeploymentManager(session)
        config = await deployment_manager.create_deployment_config(
            workflow_id=workflow_id, deployment_name=deployment_name, deployment_config=deployment_config
        )

        logger.info(f"Deployment config created: {config.id} by {current_user}")
        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create deployment config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/configs", response_model=list[AgentDeploymentConfig])
async def list_deployment_configs(
    workflow_id: str | None = None,
    status: DeploymentStatus | None = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """List deployment configurations with filtering"""

    try:
        query = select(AgentDeploymentConfig)

        if workflow_id:
            query = query.where(AgentDeploymentConfig.workflow_id == workflow_id)

        if status:
            query = query.where(AgentDeploymentConfig.status == status)

        configs = session.execute(query).all()

        # Filter by user ownership
        user_configs = []
        for config in configs:
            workflow = session.get(AIAgentWorkflow, config.workflow_id)
            if workflow and workflow.owner_id == current_user:
                user_configs.append(config)

        return user_configs

    except Exception as e:
        logger.error(f"Failed to list deployment configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/configs/{config_id}", response_model=AgentDeploymentConfig)
async def get_deployment_config(
    config_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Get specific deployment configuration"""

    try:
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")

        # Check ownership
        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get deployment config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{config_id}/deploy")
async def deploy_workflow(
    config_id: str,
    target_environment: str = "production",
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Deploy agent workflow to target environment"""

    try:
        # Check ownership
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

        logger.info(f"Workflow deployed: {config_id} to {target_environment} by {current_user}")
        return deployment_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deploy workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{config_id}/health")
async def get_deployment_health(
    config_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Get health status of deployment"""

    try:
        # Check ownership
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
        logger.error(f"Failed to get deployment health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{config_id}/scale")
async def scale_deployment(
    config_id: str,
    target_instances: int,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Scale deployment to target number of instances"""

    try:
        # Check ownership
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

        logger.info(f"Deployment scaled: {config_id} to {target_instances} instances by {current_user}")
        return scaling_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to scale deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{config_id}/rollback")
async def rollback_deployment(
    config_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Rollback deployment to previous version"""

    try:
        # Check ownership
        config = session.get(AgentDeploymentConfig, config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Deployment config not found")

        workflow = session.get(AIAgentWorkflow, config.workflow_id)
        if not workflow or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        deployment_manager = AgentDeploymentManager(session)
        rollback_result = await deployment_manager.rollback_deployment(config_id)

        logger.info(f"Deployment rolled back: {config_id} by {current_user}")
        return rollback_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/instances", response_model=list[AgentDeploymentInstance])
async def list_deployment_instances(
    deployment_id: str | None = None,
    environment: str | None = None,
    status: DeploymentStatus | None = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """List deployment instances with filtering"""

    try:
        query = select(AgentDeploymentInstance)

        if deployment_id:
            query = query.where(AgentDeploymentInstance.deployment_id == deployment_id)

        if environment:
            query = query.where(AgentDeploymentInstance.environment == environment)

        if status:
            query = query.where(AgentDeploymentInstance.status == status)

        instances = session.execute(query).all()

        # Filter by user ownership
        user_instances = []
        for instance in instances:
            config = session.get(AgentDeploymentConfig, instance.deployment_id)
            if config:
                workflow = session.get(AIAgentWorkflow, config.workflow_id)
                if workflow and workflow.owner_id == current_user:
                    user_instances.append(instance)

        return user_instances

    except Exception as e:
        logger.error(f"Failed to list deployment instances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/instances/{instance_id}", response_model=AgentDeploymentInstance)
async def get_deployment_instance(
    instance_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Get specific deployment instance"""

    try:
        instance = session.get(AgentDeploymentInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Check ownership
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
        logger.error(f"Failed to get deployment instance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/integrations/zk/{execution_id}")
async def integrate_with_zk_system(
    execution_id: str,
    verification_level: VerificationLevel = VerificationLevel.BASIC,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Integrate agent execution with ZK proof system"""

    try:
        # Check execution ownership
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

        logger.info(f"ZK integration completed: {execution_id} by {current_user}")
        return integration_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to integrate with ZK system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/deployments/{deployment_id}")
async def get_deployment_metrics(
    deployment_id: str,
    time_range: str = "1h",
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Get metrics for deployment over time range"""

    try:
        # Check ownership
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
        logger.error(f"Failed to get deployment metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/production/deploy")
async def deploy_to_production(
    workflow_id: str,
    deployment_config: dict,
    integration_config: dict | None = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
):
    """Deploy agent workflow to production with full integration"""

    try:
        # Check workflow ownership
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        production_manager = AgentProductionManager(session)
        production_result = await production_manager.deploy_to_production(
            workflow_id=workflow_id, deployment_config=deployment_config, integration_config=integration_config
        )

        logger.info(f"Production deployment completed: {workflow_id} by {current_user}")
        return production_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deploy to production: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/dashboard")
async def get_production_dashboard(
    session: Session = Depends(Annotated[Session, Depends(get_session)]), current_user: str = Depends(require_admin_key())
):
    """Get comprehensive production dashboard data"""

    try:
        # Get user's deployments
        user_configs = session.execute(
            select(AgentDeploymentConfig).join(AIAgentWorkflow).where(AIAgentWorkflow.owner_id == current_user)
        ).all()

        dashboard_data = {
            "total_deployments": len(user_configs),
            "active_deployments": len([c for c in user_configs if c.status == DeploymentStatus.DEPLOYED]),
            "failed_deployments": len([c for c in user_configs if c.status == DeploymentStatus.FAILED]),
            "deployments": [],
        }

        # Get detailed deployment info
        for config in user_configs:
            # Get instances for this deployment
            instances = session.execute(
                select(AgentDeploymentInstance).where(AgentDeploymentInstance.deployment_id == config.id)
            ).all()

            # Get metrics for this deployment
            try:
                monitoring_manager = AgentMonitoringManager(session)
                metrics = await monitoring_manager.get_deployment_metrics(config.id)
            except:
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
        logger.error(f"Failed to get production dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/health")
async def get_production_health(
    session: Session = Depends(Annotated[Session, Depends(get_session)]), current_user: str = Depends(require_admin_key())
):
    """Get overall production health status"""

    try:
        # Get user's deployments
        user_configs = session.execute(
            select(AgentDeploymentConfig).join(AIAgentWorkflow).where(AIAgentWorkflow.owner_id == current_user)
        ).all()

        health_status = {
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

        # Check health of each deployment
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

                # Aggregate health counts
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
                logger.error(f"Health check failed for deployment {config.id}: {e}")
                health_status["unknown_deployments"] += 1

        # Determine overall health
        if health_status["unhealthy_deployments"] > 0:
            health_status["overall_health"] = "unhealthy"
        elif health_status["unknown_deployments"] > 0:
            health_status["overall_health"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Failed to get production health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/alerts")
async def get_production_alerts(
    severity: str | None = None,
    limit: int = 50,
    current_user: str = Depends(require_admin_key()),
):
    """Get production alerts and notifications"""

    try:
        alerts = alert_dispatcher.get_recent_alerts(severity=severity, limit=limit)
        return {
            "alerts": alerts,
            "total_count": len(alerts),
            "severity": severity,
            "source": "coordinator_metrics",
        }

    except Exception as e:
        logger.error(f"Failed to get production alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
