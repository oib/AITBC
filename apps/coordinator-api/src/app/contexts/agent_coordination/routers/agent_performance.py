"""
Advanced Agent Performance API Endpoints
REST API for meta-learning, resource optimization, and performance enhancement
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ....domain.agent_performance import (
    LearningStrategy,
    OptimizationTarget,
    PerformanceMetric,
)
from ....services.agent_coordination.performance import (
    AgentPerformanceService,
    MetaLearningEngine,
    PerformanceOptimizer,
    ResourceManager,
)
from ....storage import get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/agent-performance", tags=["agent-performance"])


class PerformanceProfileRequest(BaseModel):
    """Request model for performance profile creation"""

    agent_id: str
    agent_type: str = Field(default="hermes")
    initial_metrics: dict[str, float] = Field(default_factory=dict)


class PerformanceProfileResponse(BaseModel):
    """Response model for performance profile"""

    profile_id: str
    agent_id: str
    agent_type: str
    overall_score: float
    performance_metrics: dict[str, float]
    learning_strategies: list[str]
    specialization_areas: list[str]
    expertise_levels: dict[str, float]
    resource_efficiency: dict[str, float]
    cost_per_task: float
    throughput: float
    average_latency: float
    last_assessed: str | None
    created_at: str
    updated_at: str


class MetaLearningRequest(BaseModel):
    """Request model for meta-learning model creation"""

    model_name: str
    base_algorithms: list[str]
    meta_strategy: LearningStrategy
    adaptation_targets: list[str]


class MetaLearningResponse(BaseModel):
    """Response model for meta-learning model"""

    model_id: str
    model_name: str
    model_type: str
    meta_strategy: str
    adaptation_targets: list[str]
    meta_accuracy: float
    adaptation_speed: float
    generalization_ability: float
    status: str
    created_at: str
    trained_at: str | None


class ResourceAllocationRequest(BaseModel):
    """Request model for resource allocation"""

    agent_id: str
    task_requirements: dict[str, Any]
    optimization_target: OptimizationTarget = Field(default=OptimizationTarget.EFFICIENCY)
    priority_level: str = Field(default="normal")


class ResourceAllocationResponse(BaseModel):
    """Response model for resource allocation"""

    allocation_id: str
    agent_id: str
    cpu_cores: float
    memory_gb: float
    gpu_count: float
    gpu_memory_gb: float
    storage_gb: float
    network_bandwidth: float
    optimization_target: str
    status: str
    allocated_at: str


class PerformanceOptimizationRequest(BaseModel):
    """Request model for performance optimization"""

    agent_id: str
    target_metric: PerformanceMetric
    current_performance: dict[str, float]
    optimization_type: str = Field(default="comprehensive")


class PerformanceOptimizationResponse(BaseModel):
    """Response model for performance optimization"""

    optimization_id: str
    agent_id: str
    optimization_type: str
    target_metric: str
    status: str
    performance_improvement: float
    resource_savings: float
    cost_savings: float
    overall_efficiency_gain: float
    created_at: str
    completed_at: str | None


class CapabilityRequest(BaseModel):
    """Request model for agent capability"""

    agent_id: str
    capability_name: str
    capability_type: str
    domain_area: str
    skill_level: float = Field(ge=0, le=10.0)
    specialization_areas: list[str] = Field(default_factory=list)


class CapabilityResponse(BaseModel):
    """Response model for agent capability"""

    capability_id: str
    agent_id: str
    capability_name: str
    capability_type: str
    domain_area: str
    skill_level: float
    proficiency_score: float
    specialization_areas: list[str]
    status: str
    created_at: str


@router.post("/profiles", response_model=PerformanceProfileResponse)
@rate_limit(rate=20, per=60)
async def create_performance_profile(
    request: Request, profile_request: PerformanceProfileRequest, session: Annotated[Session, Depends(get_session)]
) -> PerformanceProfileResponse:
    """Create agent performance profile"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        profile = await performance_service.create_performance_profile(
            agent_id=profile_request.agent_id,
            agent_type=profile_request.agent_type,
            initial_metrics=profile_request.initial_metrics,
        )
        return PerformanceProfileResponse(
            profile_id=profile.profile_id,
            agent_id=profile.agent_id,
            agent_type=profile.agent_type,
            overall_score=profile.overall_score,
            performance_metrics=profile.performance_metrics,
            learning_strategies=profile.learning_strategies,
            specialization_areas=profile.specialization_areas,
            expertise_levels=profile.expertise_levels,
            resource_efficiency=profile.resource_efficiency,
            cost_per_task=profile.cost_per_task,
            throughput=profile.throughput,
            average_latency=profile.average_latency,
            last_assessed=profile.last_assessed.isoformat() if profile.last_assessed else None,
            created_at=profile.created_at.isoformat(),
            updated_at=profile.updated_at.isoformat(),
        )
    except Exception as e:
        logger.error("Error creating performance profile: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/profiles/{agent_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_performance_profile(
    request: Request, agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Get agent performance profile"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        profile = await performance_service.get_comprehensive_profile(agent_id)
        if "error" in profile:
            raise HTTPException(status_code=404, detail=profile["error"])
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting performance profile for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/profiles/{agent_id}/metrics")
@rate_limit(rate=20, per=60)
async def update_performance_metrics(
    request: Request,
    agent_id: str,
    metrics: dict[str, float],
    session: Annotated[Session, Depends(get_session)],
    task_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update agent performance metrics"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        profile = await performance_service.update_performance_metrics(
            agent_id=agent_id, new_metrics=metrics, task_context=task_context
        )
        return {
            "success": True,
            "profile_id": profile.profile_id,
            "overall_score": profile.overall_score,
            "updated_at": profile.updated_at.isoformat(),
            "improvement_trends": profile.improvement_trends,
        }
    except Exception as e:
        logger.error("Error updating performance metrics for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/meta-learning/models", response_model=MetaLearningResponse)
@rate_limit(rate=20, per=60)
async def create_meta_learning_model(
    request: Request, model_request: MetaLearningRequest, session: Annotated[Session, Depends(get_session)]
) -> MetaLearningResponse:
    """Create meta-learning model"""
    meta_learning_engine = MetaLearningEngine()
    try:
        model = await meta_learning_engine.create_meta_learning_model(
            session=session,
            model_name=model_request.model_name,
            base_algorithms=model_request.base_algorithms,
            meta_strategy=model_request.meta_strategy,
            adaptation_targets=model_request.adaptation_targets,
        )  # type: ignore[arg-type]
        return MetaLearningResponse(
            model_id=model.model_id,
            model_name=model.model_name,
            model_type=model.model_type,
            meta_strategy=model.meta_strategy.value,
            adaptation_targets=model.adaptation_targets,
            meta_accuracy=model.meta_accuracy,
            adaptation_speed=model.adaptation_speed,
            generalization_ability=model.generalization_ability,
            status=model.status,
            created_at=model.created_at.isoformat(),
            trained_at=model.trained_at.isoformat() if model.trained_at else None,
        )
    except Exception as e:
        logger.error("Error creating meta-learning model: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/meta-learning/models/{model_id}/adapt")
@rate_limit(rate=20, per=60)
async def adapt_model_to_task(
    request: Request,
    model_id: str,
    task_data: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    adaptation_steps: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Adapt meta-learning model to new task"""
    meta_learning_engine = MetaLearningEngine()
    try:
        results = await meta_learning_engine.adapt_to_new_task(
            session=session, model_id=model_id, task_data=task_data, adaptation_steps=adaptation_steps
        )
        return results  # type: ignore[no-any-return]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error adapting meta-learning model: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/resources/allocate", response_model=ResourceAllocationResponse)
@rate_limit(rate=20, per=60)
async def allocate_resources(
    request: Request, allocation_request: ResourceAllocationRequest, session: Annotated[Session, Depends(get_session)]
) -> ResourceAllocationResponse:
    """Allocate resources for agent task"""
    resource_manager = ResourceManager()
    try:
        allocation = await resource_manager.allocate_resources(
            session=session,
            agent_id=allocation_request.agent_id,
            task_requirements=allocation_request.task_requirements,
            optimization_target=allocation_request.optimization_target,
            priority_level=allocation_request.priority_level,
        )  # type: ignore[arg-type]
        return ResourceAllocationResponse(
            allocation_id=allocation.allocation_id,
            agent_id=allocation.agent_id,
            cpu_cores=allocation.cpu_cores,
            memory_gb=allocation.memory_gb,
            gpu_count=allocation.gpu_count,
            gpu_memory_gb=allocation.gpu_memory_gb,
            storage_gb=allocation.storage_gb,
            network_bandwidth=allocation.network_bandwidth,
            optimization_target=allocation.optimization_target.value,
            status=allocation.status,
            allocated_at=allocation.allocated_at.isoformat(),
        )
    except Exception as e:
        logger.error("Error allocating resources: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/optimize", response_model=PerformanceOptimizationResponse)
@rate_limit(rate=20, per=60)
async def optimize_performance(
    request: Request, optimization_request: PerformanceOptimizationRequest, session: Annotated[Session, Depends(get_session)]
) -> PerformanceOptimizationResponse:
    """Optimize agent performance"""
    optimizer = PerformanceOptimizer()
    try:
        optimization = await optimizer.optimize_performance(
            session=session,
            agent_id=optimization_request.agent_id,
            target_metric=optimization_request.target_metric,
            current_performance=optimization_request.current_performance,
            optimization_type=optimization_request.optimization_type,
        )  # type: ignore[arg-type]
        return PerformanceOptimizationResponse(
            optimization_id=optimization.optimization_id,
            agent_id=optimization.agent_id,
            optimization_type=optimization.optimization_type,
            target_metric=optimization.target_metric.value,
            status=optimization.status,
            performance_improvement=optimization.performance_improvement,
            resource_savings=optimization.resource_savings,
            cost_savings=optimization.cost_savings,
            overall_efficiency_gain=optimization.overall_efficiency_gain,
            created_at=optimization.created_at.isoformat(),
            completed_at=optimization.completed_at.isoformat() if optimization.completed_at else None,
        )
    except Exception as e:
        logger.error("Error optimizing performance: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/capabilities", response_model=CapabilityResponse)
@rate_limit(rate=20, per=60)
async def create_capability(
    request: Request, capability_request: CapabilityRequest, session: Annotated[Session, Depends(get_session)]
) -> CapabilityResponse:
    """Create agent capability"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        capability = await performance_service.create_capability(
            session=session,
            agent_id=capability_request.agent_id,
            capability_name=capability_request.capability_name,
            capability_type=capability_request.capability_type,
            domain_area=capability_request.domain_area,
            skill_level=capability_request.skill_level,
            specialization_areas=capability_request.specialization_areas,
        )  # type: ignore[arg-type]
        return CapabilityResponse(
            capability_id=capability.capability_id,
            agent_id=capability.agent_id,
            capability_name=capability.capability_name,
            capability_type=capability.capability_type,
            domain_area=capability.domain_area,
            skill_level=capability.skill_level,
            proficiency_score=capability.proficiency_score,
            specialization_areas=capability.specialization_areas,
            status=capability.status,
            created_at=capability.created_at.isoformat(),
        )
    except Exception as e:
        logger.error("Error creating capability: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/capabilities/{agent_id}", response_model=list[CapabilityResponse])
@rate_limit(rate=200, per=60)
async def list_agent_capabilities(
    request: Request, agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> list[CapabilityResponse]:
    """List all capabilities for an agent"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        capabilities = await performance_service.list_capabilities(agent_id)
        return [
            CapabilityResponse(
                capability_id=cap.capability_id,
                agent_id=cap.agent_id,
                capability_name=cap.capability_name,
                capability_type=cap.capability_type,
                domain_area=cap.domain_area,
                skill_level=cap.skill_level,
                proficiency_score=cap.proficiency_score,
                specialization_areas=cap.specialization_areas,
                status=cap.status,
                created_at=cap.created_at.isoformat(),
            )
            for cap in capabilities
        ]
    except Exception as e:
        logger.error("Error listing capabilities for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/analytics/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_performance_analytics(
    request: Request, agent_id: str, period_days: int = 30, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Get performance analytics for an agent"""
    performance_service = AgentPerformanceService(session)  # type: ignore[arg-type]
    try:
        analytics = await performance_service.get_performance_analytics(agent_id, period_days)
        return analytics  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting performance analytics for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e
