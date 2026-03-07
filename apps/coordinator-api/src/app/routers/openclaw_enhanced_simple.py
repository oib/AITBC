from sqlalchemy.orm import Session
from typing import Annotated
"""
OpenClaw Enhanced API Router - Simplified Version
REST API endpoints for OpenClaw integration features
"""

from typing import List, Optional, Dict, Any
from aitbc.logging import get_logger

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..services.openclaw_enhanced_simple import OpenClawEnhancedService, SkillType, ExecutionMode
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..deps import require_admin_key
from sqlmodel import Session

logger = get_logger(__name__)

router = APIRouter(prefix="/openclaw/enhanced", tags=["OpenClaw Enhanced"])


class SkillRoutingRequest(BaseModel):
    """Request for agent skill routing"""
    skill_type: SkillType = Field(..., description="Type of skill required")
    requirements: Dict[str, Any] = Field(..., description="Skill requirements")
    performance_optimization: bool = Field(default=True, description="Enable performance optimization")


class JobOffloadingRequest(BaseModel):
    """Request for intelligent job offloading"""
    job_data: Dict[str, Any] = Field(..., description="Job data and requirements")
    cost_optimization: bool = Field(default=True, description="Enable cost optimization")
    performance_analysis: bool = Field(default=True, description="Enable performance analysis")


class AgentCollaborationRequest(BaseModel):
    """Request for agent collaboration"""
    task_data: Dict[str, Any] = Field(..., description="Task data and requirements")
    agent_ids: List[str] = Field(..., description="List of agent IDs to coordinate")
    coordination_algorithm: str = Field(default="distributed_consensus", description="Coordination algorithm")


class HybridExecutionRequest(BaseModel):
    """Request for hybrid execution optimization"""
    execution_request: Dict[str, Any] = Field(..., description="Execution request data")
    optimization_strategy: str = Field(default="performance", description="Optimization strategy")


class EdgeDeploymentRequest(BaseModel):
    """Request for edge deployment"""
    agent_id: str = Field(..., description="Agent ID to deploy")
    edge_locations: List[str] = Field(..., description="Edge locations for deployment")
    deployment_config: Dict[str, Any] = Field(..., description="Deployment configuration")


class EdgeCoordinationRequest(BaseModel):
    """Request for edge-to-cloud coordination"""
    edge_deployment_id: str = Field(..., description="Edge deployment ID")
    coordination_config: Dict[str, Any] = Field(..., description="Coordination configuration")


class EcosystemDevelopmentRequest(BaseModel):
    """Request for ecosystem development"""
    ecosystem_config: Dict[str, Any] = Field(..., description="Ecosystem configuration")


@router.post("/routing/skill")
async def route_agent_skill(
    request: SkillRoutingRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Route agent skill to appropriate agent"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.route_agent_skill(
            skill_type=request.skill_type,
            requirements=request.requirements,
            performance_optimization=request.performance_optimization
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error routing agent skill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/offloading/intelligent")
async def intelligent_job_offloading(
    request: JobOffloadingRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Intelligent job offloading strategies"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.offload_job_intelligently(
            job_data=request.job_data,
            cost_optimization=request.cost_optimization,
            performance_analysis=request.performance_analysis
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in intelligent job offloading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collaboration/coordinate")
async def coordinate_agent_collaboration(
    request: AgentCollaborationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Agent collaboration and coordination"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.coordinate_agent_collaboration(
            task_data=request.task_data,
            agent_ids=request.agent_ids,
            coordination_algorithm=request.coordination_algorithm
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error coordinating agent collaboration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execution/hybrid-optimize")
async def optimize_hybrid_execution(
    request: HybridExecutionRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Hybrid execution optimization"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.optimize_hybrid_execution(
            execution_request=request.execution_request,
            optimization_strategy=request.optimization_strategy
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error optimizing hybrid execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edge/deploy")
async def deploy_to_edge(
    request: EdgeDeploymentRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Deploy agent to edge computing infrastructure"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.deploy_to_edge(
            agent_id=request.agent_id,
            edge_locations=request.edge_locations,
            deployment_config=request.deployment_config
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error deploying to edge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edge/coordinate")
async def coordinate_edge_to_cloud(
    request: EdgeCoordinationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Coordinate edge-to-cloud agent operations"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.coordinate_edge_to_cloud(
            edge_deployment_id=request.edge_deployment_id,
            coordination_config=request.coordination_config
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error coordinating edge-to-cloud: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosystem/develop")
async def develop_openclaw_ecosystem(
    request: EcosystemDevelopmentRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Build OpenClaw ecosystem components"""
    
    try:
        enhanced_service = OpenClawEnhancedService(session)
        result = await enhanced_service.develop_openclaw_ecosystem(
            ecosystem_config=request.ecosystem_config
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error developing OpenClaw ecosystem: {e}")
        raise HTTPException(status_code=500, detail=str(e))
