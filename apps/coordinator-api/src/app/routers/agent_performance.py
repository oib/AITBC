from typing import Annotated

from sqlalchemy.orm import Session

"""
Advanced Agent Performance API Endpoints
REST API for meta-learning, resource optimization, and performance enhancement
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from aitbc import get_logger

logger = get_logger(__name__)

from ..domain.agent_performance import (
    AgentCapability,
    AgentPerformanceProfile,
    CreativeCapability,
    FusionModel,
    LearningStrategy,
    MetaLearningModel,
    OptimizationTarget,
    PerformanceMetric,
    PerformanceOptimization,
    ReinforcementLearningConfig,
    ResourceAllocation,
    ResourceType,
)
from ..services.agent_performance_service import (
    AgentPerformanceService,
    MetaLearningEngine,
    PerformanceOptimizer,
    ResourceManager,
)
from ..storage import get_session

router = APIRouter(prefix="/v1/agent-performance", tags=["agent-performance"])


# Pydantic models for API requests/responses
class PerformanceProfileRequest(BaseModel):
    """Request model for performance profile creation"""

    agent_id: str
    agent_type: str = Field(default="openclaw")
    initial_metrics: Dict[str, float] = Field(default_factory=dict)


class PerformanceProfileResponse(BaseModel):
    """Response model for performance profile"""

    profile_id: str
    agent_id: str
    agent_type: str
    overall_score: float
    performance_metrics: Dict[str, float]
    learning_strategies: List[str]
    specialization_areas: List[str]
    expertise_levels: Dict[str, float]
    resource_efficiency: Dict[str, float]
    cost_per_task: float
    throughput: float
    average_latency: float
    last_assessed: Optional[str]
    created_at: str
    updated_at: str


class MetaLearningRequest(BaseModel):
    """Request model for meta-learning model creation"""

    model_name: str
    base_algorithms: List[str]
    meta_strategy: LearningStrategy
    adaptation_targets: List[str]


class MetaLearningResponse(BaseModel):
    """Response model for meta-learning model"""

    model_id: str
    model_name: str
    model_type: str
    meta_strategy: str
    adaptation_targets: List[str]
    meta_accuracy: float
    adaptation_speed: float
    generalization_ability: float
    status: str
    created_at: str
    trained_at: Optional[str]


class ResourceAllocationRequest(BaseModel):
    """Request model for resource allocation"""

    agent_id: str
    task_requirements: Dict[str, Any]
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
    current_performance: Dict[str, float]
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
    completed_at: Optional[str]


class CapabilityRequest(BaseModel):
    """Request model for agent capability"""

    agent_id: str
    capability_name: str
    capability_type: str
    domain_area: str
    skill_level: float = Field(ge=0, le=10.0)
    specialization_areas: List[str] = Field(default_factory=list)


class CapabilityResponse(BaseModel):
    """Response model for agent capability"""

    capability_id: str
    agent_id: str
    capability_name: str
    capability_type: str
    domain_area: str
    skill_level: float
    proficiency_score: float
    specialization_areas: List[str]
    status: str
    created_at: str


# API Endpoints


@router.post("/profiles", response_model=PerformanceProfileResponse)
async def create_performance_profile(
    profile_request: PerformanceProfileRequest, session: Annotated[Session, Depends(get_session)]
) -> PerformanceProfileResponse:
    """Create agent performance profile"""

    performance_service = AgentPerformanceService(session)

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
        logger.error(f"Error creating performance profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profiles/{agent_id}", response_model=Dict[str, Any])
async def get_performance_profile(agent_id: str, session: Annotated[Session, Depends(get_session)]) -> Dict[str, Any]:
    """Get agent performance profile"""

    performance_service = AgentPerformanceService(session)

    try:
        profile = await performance_service.get_comprehensive_profile(agent_id)

        if "error" in profile:
            raise HTTPException(status_code=404, detail=profile["error"])

        return profile

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting performance profile for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/profiles/{agent_id}/metrics")
async def update_performance_metrics(
    agent_id: str,
    metrics: Dict[str, float],
    session: Annotated[Session, Depends(get_session)],
    task_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update agent performance metrics"""

    performance_service = AgentPerformanceService(session)

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
        logger.error(f"Error updating performance metrics for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/meta-learning/models", response_model=MetaLearningResponse)
async def create_meta_learning_model(
    model_request: MetaLearningRequest, session: Annotated[Session, Depends(get_session)]
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
        )

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
        logger.error(f"Error creating meta-learning model: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/meta-learning/models/{model_id}/adapt")
async def adapt_model_to_task(
    model_id: str,
    task_data: Dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    adaptation_steps: int = Query(default=10, ge=1, le=50),
) -> Dict[str, Any]:
    """Adapt meta-learning model to new task"""

    meta_learning_engine = MetaLearningEngine()

    try:
        results = await meta_learning_engine.adapt_to_new_task(
            session=session, model_id=model_id, task_data=task_data, adaptation_steps=adaptation_steps
        )

        return {
            "success": True,
            "model_id": model_id,
            "adaptation_results": results,
            "adapted_at": datetime.now(timezone.utc).isoformat(),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error adapting model {model_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/meta-learning/models")
async def list_meta_learning_models(
    session: Annotated[Session, Depends(get_session)],
    status: Optional[str] = Query(default=None, description="Filter by status"),
    meta_strategy: Optional[str] = Query(default=None, description="Filter by meta strategy"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
) -> List[Dict[str, Any]]:
    """List meta-learning models"""

    try:
        query = select(MetaLearningModel)

        if status:
            query = query.where(MetaLearningModel.status == status)
        if meta_strategy:
            query = query.where(MetaLearningModel.meta_strategy == LearningStrategy(meta_strategy))

        models = session.execute(query.order_by(MetaLearningModel.created_at.desc()).limit(limit)).all()

        return [
            {
                "model_id": model.model_id,
                "model_name": model.model_name,
                "model_type": model.model_type,
                "meta_strategy": model.meta_strategy.value,
                "adaptation_targets": model.adaptation_targets,
                "meta_accuracy": model.meta_accuracy,
                "adaptation_speed": model.adaptation_speed,
                "generalization_ability": model.generalization_ability,
                "status": model.status,
                "deployment_count": model.deployment_count,
                "success_rate": model.success_rate,
                "created_at": model.created_at.isoformat(),
                "trained_at": model.trained_at.isoformat() if model.trained_at else None,
            }
            for model in models
        ]

    except Exception as e:
        logger.error(f"Error listing meta-learning models: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/resources/allocate", response_model=ResourceAllocationResponse)
async def allocate_resources(
    allocation_request: ResourceAllocationRequest, session: Annotated[Session, Depends(get_session)]
) -> ResourceAllocationResponse:
    """Allocate resources for agent task"""

    resource_manager = ResourceManager()

    try:
        allocation = await resource_manager.allocate_resources(
            session=session,
            agent_id=allocation_request.agent_id,
            task_requirements=allocation_request.task_requirements,
            optimization_target=allocation_request.optimization_target,
        )

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
        logger.error(f"Error allocating resources: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/resources/{agent_id}")
async def get_resource_allocations(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
) -> List[Dict[str, Any]]:
    """Get resource allocations for agent"""

    try:
        query = select(ResourceAllocation).where(ResourceAllocation.agent_id == agent_id)

        if status:
            query = query.where(ResourceAllocation.status == status)

        allocations = session.execute(query.order_by(ResourceAllocation.created_at.desc()).limit(limit)).all()

        return [
            {
                "allocation_id": allocation.allocation_id,
                "agent_id": allocation.agent_id,
                "task_id": allocation.task_id,
                "cpu_cores": allocation.cpu_cores,
                "memory_gb": allocation.memory_gb,
                "gpu_count": allocation.gpu_count,
                "gpu_memory_gb": allocation.gpu_memory_gb,
                "storage_gb": allocation.storage_gb,
                "network_bandwidth": allocation.network_bandwidth,
                "optimization_target": allocation.optimization_target.value,
                "priority_level": allocation.priority_level,
                "status": allocation.status,
                "efficiency_score": allocation.efficiency_score,
                "cost_efficiency": allocation.cost_efficiency,
                "allocated_at": allocation.allocated_at.isoformat() if allocation.allocated_at else None,
                "started_at": allocation.started_at.isoformat() if allocation.started_at else None,
                "completed_at": allocation.completed_at.isoformat() if allocation.completed_at else None,
            }
            for allocation in allocations
        ]

    except Exception as e:
        logger.error(f"Error getting resource allocations for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/optimization/optimize", response_model=PerformanceOptimizationResponse)
async def optimize_performance(
    optimization_request: PerformanceOptimizationRequest, session: Annotated[Session, Depends(get_session)]
) -> PerformanceOptimizationResponse:
    """Optimize agent performance"""

    performance_optimizer = PerformanceOptimizer()

    try:
        optimization = await performance_optimizer.optimize_agent_performance(
            session=session,
            agent_id=optimization_request.agent_id,
            target_metric=optimization_request.target_metric,
            current_performance=optimization_request.current_performance,
        )

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
        logger.error(f"Error optimizing performance: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/optimization/{agent_id}")
async def get_optimization_history(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    status: Optional[str] = Query(default=None, description="Filter by status"),
    target_metric: Optional[str] = Query(default=None, description="Filter by target metric"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
) -> List[Dict[str, Any]]:
    """Get optimization history for agent"""

    try:
        query = select(PerformanceOptimization).where(PerformanceOptimization.agent_id == agent_id)

        if status:
            query = query.where(PerformanceOptimization.status == status)
        if target_metric:
            query = query.where(PerformanceOptimization.target_metric == PerformanceMetric(target_metric))

        optimizations = session.execute(query.order_by(PerformanceOptimization.created_at.desc()).limit(limit)).all()

        return [
            {
                "optimization_id": optimization.optimization_id,
                "agent_id": optimization.agent_id,
                "optimization_type": optimization.optimization_type,
                "target_metric": optimization.target_metric.value,
                "status": optimization.status,
                "baseline_performance": optimization.baseline_performance,
                "optimized_performance": optimization.optimized_performance,
                "baseline_cost": optimization.baseline_cost,
                "optimized_cost": optimization.optimized_cost,
                "performance_improvement": optimization.performance_improvement,
                "resource_savings": optimization.resource_savings,
                "cost_savings": optimization.cost_savings,
                "overall_efficiency_gain": optimization.overall_efficiency_gain,
                "optimization_duration": optimization.optimization_duration,
                "iterations_required": optimization.iterations_required,
                "convergence_achieved": optimization.convergence_achieved,
                "created_at": optimization.created_at.isoformat(),
                "completed_at": optimization.completed_at.isoformat() if optimization.completed_at else None,
            }
            for optimization in optimizations
        ]

    except Exception as e:
        logger.error(f"Error getting optimization history for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/capabilities", response_model=CapabilityResponse)
async def create_capability(
    capability_request: CapabilityRequest, session: Annotated[Session, Depends(get_session)]
) -> CapabilityResponse:
    """Create agent capability"""

    try:
        capability_id = f"cap_{uuid4().hex[:8]}"

        capability = AgentCapability(
            capability_id=capability_id,
            agent_id=capability_request.agent_id,
            capability_name=capability_request.capability_name,
            capability_type=capability_request.capability_type,
            domain_area=capability_request.domain_area,
            skill_level=capability_request.skill_level,
            specialization_areas=capability_request.specialization_areas,
            proficiency_score=min(1.0, capability_request.skill_level / 10.0),
            created_at=datetime.now(timezone.utc),
        )

        session.add(capability)
        session.commit()
        session.refresh(capability)

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
        logger.error(f"Error creating capability: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/capabilities/{agent_id}")
async def get_agent_capabilities(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    capability_type: Optional[str] = Query(default=None, description="Filter by capability type"),
    domain_area: Optional[str] = Query(default=None, description="Filter by domain area"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
) -> List[Dict[str, Any]]:
    """Get agent capabilities"""

    try:
        query = select(AgentCapability).where(AgentCapability.agent_id == agent_id)

        if capability_type:
            query = query.where(AgentCapability.capability_type == capability_type)
        if domain_area:
            query = query.where(AgentCapability.domain_area == domain_area)

        capabilities = session.execute(query.order_by(AgentCapability.skill_level.desc()).limit(limit)).all()

        return [
            {
                "capability_id": capability.capability_id,
                "agent_id": capability.agent_id,
                "capability_name": capability.capability_name,
                "capability_type": capability.capability_type,
                "domain_area": capability.domain_area,
                "skill_level": capability.skill_level,
                "proficiency_score": capability.proficiency_score,
                "experience_years": capability.experience_years,
                "success_rate": capability.success_rate,
                "average_quality": capability.average_quality,
                "learning_rate": capability.learning_rate,
                "adaptation_speed": capability.adaptation_speed,
                "specialization_areas": capability.specialization_areas,
                "sub_capabilities": capability.sub_capabilities,
                "tool_proficiency": capability.tool_proficiency,
                "certified": capability.certified,
                "certification_level": capability.certification_level,
                "status": capability.status,
                "acquired_at": capability.acquired_at.isoformat(),
                "last_improved": capability.last_improved.isoformat() if capability.last_improved else None,
            }
            for capability in capabilities
        ]

    except Exception as e:
        logger.error(f"Error getting capabilities for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/performance-summary")
async def get_performance_summary(
    session: Annotated[Session, Depends(get_session)],
    agent_ids: List[str] = Query(default=[], description="List of agent IDs"),
    metric: Optional[str] = Query(default="overall_score", description="Metric to summarize"),
    period: str = Query(default="7d", description="Time period"),
) -> Dict[str, Any]:
    """Get performance summary for agents"""

    try:
        if not agent_ids:
            # Get all agents if none specified
            profiles = session.execute(select(AgentPerformanceProfile)).all()
            agent_ids = [p.agent_id for p in profiles]

        summaries = []

        for agent_id in agent_ids:
            profile = session.execute(
                select(AgentPerformanceProfile).where(AgentPerformanceProfile.agent_id == agent_id)
            ).first()

            if profile:
                summaries.append(
                    {
                        "agent_id": agent_id,
                        "overall_score": profile.overall_score,
                        "performance_metrics": profile.performance_metrics,
                        "resource_efficiency": profile.resource_efficiency,
                        "cost_per_task": profile.cost_per_task,
                        "throughput": profile.throughput,
                        "average_latency": profile.average_latency,
                        "specialization_areas": profile.specialization_areas,
                        "last_assessed": profile.last_assessed.isoformat() if profile.last_assessed else None,
                    }
                )

        # Calculate summary statistics
        if summaries:
            overall_scores = [s["overall_score"] for s in summaries]
            avg_score = sum(overall_scores) / len(overall_scores)

            return {
                "period": period,
                "agent_count": len(summaries),
                "average_score": avg_score,
                "top_performers": sorted(summaries, key=lambda x: x["overall_score"], reverse=True)[:10],
                "performance_distribution": {
                    "excellent": len([s for s in summaries if s["overall_score"] >= 80]),
                    "good": len([s for s in summaries if 60 <= s["overall_score"] < 80]),
                    "average": len([s for s in summaries if 40 <= s["overall_score"] < 60]),
                    "below_average": len([s for s in summaries if s["overall_score"] < 40]),
                },
                "specialization_distribution": self.calculate_specialization_distribution(summaries),
            }
        else:
            return {
                "period": period,
                "agent_count": 0,
                "average_score": 0.0,
                "top_performers": [],
                "performance_distribution": {},
                "specialization_distribution": {},
            }

    except Exception as e:
        logger.error(f"Error getting performance summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def calculate_specialization_distribution(summaries: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate specialization distribution"""

    distribution = {}

    for summary in summaries:
        for area in summary["specialization_areas"]:
            distribution[area] = distribution.get(area, 0) + 1

    return distribution


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check for agent performance service"""

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "services": {
            "meta_learning_engine": "operational",
            "resource_manager": "operational",
            "performance_optimizer": "operational",
            "performance_service": "operational",
        },
    }
