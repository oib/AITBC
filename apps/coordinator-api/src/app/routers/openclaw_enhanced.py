from sqlalchemy.orm import Session
from typing import Annotated
"""
OpenClaw Integration Enhancement API Router - Phase 6.6
REST API endpoints for advanced agent orchestration, edge computing integration, and ecosystem development
"""

from typing import List, Optional
from aitbc.logging import get_logger

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..domain import AIAgentWorkflow, AgentExecution, AgentStatus
from ..services.openclaw_enhanced import OpenClawEnhancedService, SkillType, ExecutionMode
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..deps import require_admin_key
from ..schemas.openclaw_enhanced import (
    SkillRoutingRequest, SkillRoutingResponse,
    JobOffloadingRequest, JobOffloadingResponse,
    AgentCollaborationRequest, AgentCollaborationResponse,
    HybridExecutionRequest, HybridExecutionResponse,
    EdgeDeploymentRequest, EdgeDeploymentResponse,
    EdgeCoordinationRequest, EdgeCoordinationResponse,
    EcosystemDevelopmentRequest, EcosystemDevelopmentResponse
)

logger = get_logger(__name__)

router = APIRouter(prefix="/openclaw/enhanced", tags=["OpenClaw Enhanced"])


@router.post("/routing/skill", response_model=SkillRoutingResponse)
async def route_agent_skill(
    routing_request: SkillRoutingRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Sophisticated agent skill routing"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.route_agent_skill(
            skill_type=routing_request.skill_type,
            requirements=routing_request.requirements,
            performance_optimization=routing_request.performance_optimization
        )
        
        return SkillRoutingResponse(
            selected_agent=result["selected_agent"],
            routing_strategy=result["routing_strategy"],
            expected_performance=result["expected_performance"],
            estimated_cost=result["estimated_cost"]
        )
        
    except Exception as e:
        logger.error(f"Error routing agent skill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/offloading/intelligent", response_model=JobOffloadingResponse)
async def intelligent_job_offloading(
    offloading_request: JobOffloadingRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Intelligent job offloading strategies"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.offload_job_intelligently(
            job_data=offloading_request.job_data,
            cost_optimization=offloading_request.cost_optimization,
            performance_analysis=offloading_request.performance_analysis
        )
        
        return JobOffloadingResponse(
            should_offload=result["should_offload"],
            job_size=result["job_size"],
            cost_analysis=result["cost_analysis"],
            performance_prediction=result["performance_prediction"],
            fallback_mechanism=result["fallback_mechanism"]
        )
        
    except Exception as e:
        logger.error(f"Error in intelligent job offloading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collaboration/coordinate", response_model=AgentCollaborationResponse)
async def coordinate_agent_collaboration(
    collaboration_request: AgentCollaborationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Agent collaboration and coordination"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.coordinate_agent_collaboration(
            task_data=collaboration_request.task_data,
            agent_ids=collaboration_request.agent_ids,
            coordination_algorithm=collaboration_request.coordination_algorithm
        )
        
        return AgentCollaborationResponse(
            coordination_method=result["coordination_method"],
            selected_coordinator=result["selected_coordinator"],
            consensus_reached=result["consensus_reached"],
            task_distribution=result["task_distribution"],
            estimated_completion_time=result["estimated_completion_time"]
        )
        
    except Exception as e:
        logger.error(f"Error coordinating agent collaboration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/hybrid-optimize", response_model=HybridExecutionResponse)
async def optimize_hybrid_execution(
    execution_request: HybridExecutionRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Hybrid execution optimization"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.optimize_hybrid_execution(
            execution_request=execution_request.execution_request,
            optimization_strategy=execution_request.optimization_strategy
        )
        
        return HybridExecutionResponse(
            execution_mode=result["execution_mode"],
            strategy=result["strategy"],
            resource_allocation=result["resource_allocation"],
            performance_tuning=result["performance_tuning"],
            expected_improvement=result["expected_improvement"]
        )
        
    except Exception as e:
        logger.error(f"Error optimizing hybrid execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edge/deploy", response_model=EdgeDeploymentResponse)
async def deploy_to_edge(
    deployment_request: EdgeDeploymentRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Deploy agent to edge computing infrastructure"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.deploy_to_edge(
            agent_id=deployment_request.agent_id,
            edge_locations=deployment_request.edge_locations,
            deployment_config=deployment_request.deployment_config
        )
        
        return EdgeDeploymentResponse(
            deployment_id=result["deployment_id"],
            agent_id=result["agent_id"],
            edge_locations=result["edge_locations"],
            deployment_results=result["deployment_results"],
            status=result["status"]
        )
        
    except Exception as e:
        logger.error(f"Error deploying to edge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edge/coordinate", response_model=EdgeCoordinationResponse)
async def coordinate_edge_to_cloud(
    coordination_request: EdgeCoordinationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Coordinate edge-to-cloud agent operations"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.coordinate_edge_to_cloud(
            edge_deployment_id=coordination_request.edge_deployment_id,
            coordination_config=coordination_request.coordination_config
        )
        
        return EdgeCoordinationResponse(
            coordination_id=result["coordination_id"],
            edge_deployment_id=result["edge_deployment_id"],
            synchronization=result["synchronization"],
            load_balancing=result["load_balancing"],
            failover=result["failover"],
            status=result["status"]
        )
        
    except Exception as e:
        logger.error(f"Error coordinating edge-to-cloud: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosystem/develop", response_model=EcosystemDevelopmentResponse)
async def develop_openclaw_ecosystem(
    ecosystem_request: EcosystemDevelopmentRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Build comprehensive OpenClaw ecosystem"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.develop_openclaw_ecosystem(
            ecosystem_config=ecosystem_request.ecosystem_config
        )
        
        return EcosystemDevelopmentResponse(
            ecosystem_id=result["ecosystem_id"],
            developer_tools=result["developer_tools"],
            marketplace=result["marketplace"],
            community=result["community"],
            partnerships=result["partnerships"],
            status=result["status"]
        )
        
    except Exception as e:
        logger.error(f"Error developing OpenClaw ecosystem: {e}")
        raise HTTPException(status_code=500, detail=str(e))
