from typing import Annotated

from sqlalchemy.orm import Session

"\nhermes Integration Enhancement API Router - Phase 6.6\nREST API endpoints for advanced agent orchestration, edge computing integration, and ecosystem development\n"
from aitbc import get_logger  # noqa: E402

logger = get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from aitbc.rate_limiting import rate_limit  # noqa: E402

from ....deps import require_admin_key  # noqa: E402
from ....schemas.hermes_enhanced import (  # noqa: E402
    AgentCollaborationRequest,
    AgentCollaborationResponse,
    EcosystemDevelopmentRequest,
    EcosystemDevelopmentResponse,
    EdgeCoordinationRequest,
    EdgeCoordinationResponse,
    EdgeDeploymentRequest,
    EdgeDeploymentResponse,
    HybridExecutionRequest,
    HybridExecutionResponse,
    JobOffloadingRequest,
    JobOffloadingResponse,
    SkillRoutingRequest,
    SkillRoutingResponse,
)
from ....storage import get_session  # noqa: E402
from ..services.hermes_enhanced import hermesEnhancedService  # noqa: E402

router = APIRouter(prefix="/hermes/enhanced", tags=["hermes Enhanced"])


@router.post("/routing/skill", response_model=SkillRoutingResponse)
@rate_limit(rate=20, per=60)
async def route_agent_skill(
    request: Request,
    routing_request: SkillRoutingRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> SkillRoutingResponse:
    """Sophisticated agent skill routing"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.route_agent_skill(
            skill_type=routing_request.skill_type,
            requirements=routing_request.requirements,
            performance_optimization=routing_request.performance_optimization,
        )  # type: ignore[arg-type]
        return SkillRoutingResponse(
            selected_agent=result["selected_agent"],
            routing_strategy=result["routing_strategy"],
            expected_performance=result["expected_performance"],
            estimated_cost=result["estimated_cost"],
        )
    except Exception as e:
        logger.error("Error routing agent skill: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/offloading/intelligent", response_model=JobOffloadingResponse)
@rate_limit(rate=20, per=60)
async def intelligent_job_offloading(
    request: Request,
    offloading_request: JobOffloadingRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> JobOffloadingResponse:
    """Intelligent job offloading strategies"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.offload_job_intelligently(
            job_data=offloading_request.job_data,
            cost_optimization=offloading_request.cost_optimization,
            performance_analysis=offloading_request.performance_analysis,
        )
        return JobOffloadingResponse(
            should_offload=result["should_offload"],
            job_size=result["job_size"],
            cost_analysis=result["cost_analysis"],
            performance_prediction=result["performance_prediction"],
            fallback_mechanism=result["fallback_mechanism"],
        )
    except Exception as e:
        logger.error("Error in intelligent job offloading: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/collaboration/coordinate", response_model=AgentCollaborationResponse)
@rate_limit(rate=20, per=60)
async def coordinate_agent_collaboration(
    request: Request,
    collaboration_request: AgentCollaborationRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> AgentCollaborationResponse:
    """Agent collaboration and coordination"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.coordinate_agent_collaboration(
            task_data=collaboration_request.task_data,
            agent_ids=collaboration_request.agent_ids,
            coordination_algorithm=collaboration_request.coordination_algorithm,
        )
        return AgentCollaborationResponse(
            coordination_method=result["coordination_method"],
            selected_coordinator=result["selected_coordinator"],
            consensus_reached=result["consensus_reached"],
            task_distribution=result["task_distribution"],
            estimated_completion_time=result["estimated_completion_time"],
        )
    except Exception as e:
        logger.error("Error coordinating agent collaboration: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/execution/hybrid-optimize", response_model=HybridExecutionResponse)
@rate_limit(rate=20, per=60)
async def optimize_hybrid_execution(
    request: Request,
    execution_request: HybridExecutionRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> HybridExecutionResponse:
    """Hybrid execution optimization"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.optimize_hybrid_execution(
            execution_request=execution_request.execution_request,
            optimization_strategy=execution_request.optimization_strategy,
        )
        return HybridExecutionResponse(
            execution_mode=result["execution_mode"],
            strategy=result["strategy"],
            resource_allocation=result["resource_allocation"],
            performance_tuning=result["performance_tuning"],
            expected_improvement=result["expected_improvement"],
        )
    except Exception as e:
        logger.error("Error optimizing hybrid execution: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/edge/deploy", response_model=EdgeDeploymentResponse)
@rate_limit(rate=20, per=60)
async def deploy_to_edge(
    request: Request,
    deployment_request: EdgeDeploymentRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> EdgeDeploymentResponse:
    """Deploy agent to edge computing infrastructure"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.deploy_to_edge(
            agent_id=deployment_request.agent_id,
            edge_locations=deployment_request.edge_locations,
            deployment_config=deployment_request.deployment_config,
        )
        return EdgeDeploymentResponse(
            deployment_id=result["deployment_id"],
            agent_id=result["agent_id"],
            edge_locations=result["edge_locations"],
            deployment_results=result["deployment_results"],
            status=result["status"],
        )
    except Exception as e:
        logger.error("Error deploying to edge: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/edge/coordinate", response_model=EdgeCoordinationResponse)
@rate_limit(rate=20, per=60)
async def coordinate_edge_to_cloud(
    request: Request,
    coordination_request: EdgeCoordinationRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> EdgeCoordinationResponse:
    """Coordinate edge-to-cloud agent operations"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.coordinate_edge_to_cloud(
            edge_deployment_id=coordination_request.edge_deployment_id,
            coordination_config=coordination_request.coordination_config,
        )
        return EdgeCoordinationResponse(
            coordination_id=result["coordination_id"],
            edge_deployment_id=result["edge_deployment_id"],
            synchronization=result["synchronization"],
            load_balancing=result["load_balancing"],
            failover=result["failover"],
            status=result["status"],
        )
    except Exception as e:
        logger.error("Error coordinating edge-to-cloud: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ecosystem/develop", response_model=EcosystemDevelopmentResponse)
@rate_limit(rate=20, per=60)
async def develop_hermes_ecosystem(
    request: Request,
    ecosystem_request: EcosystemDevelopmentRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: str = Depends(require_admin_key()),
) -> EcosystemDevelopmentResponse:
    """Build comprehensive hermes ecosystem"""
    try:
        enhanced_service = hermesEnhancedService(session)  # type: ignore[arg-type]
        result = await enhanced_service.develop_hermes_ecosystem(ecosystem_config=ecosystem_request.ecosystem_config)
        return EcosystemDevelopmentResponse(
            ecosystem_id=result["ecosystem_id"],
            developer_tools=result["developer_tools"],
            marketplace=result["marketplace"],
            community=result["community"],
            partnerships=result["partnerships"],
            status=result["status"],
        )
    except Exception as e:
        logger.error("Error developing hermes ecosystem: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
