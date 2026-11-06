"""
Advanced Agent Performance API Endpoints
REST API for meta-learning, resource optimization, and performance enhancement
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlmodel import Session, col, select

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....auth import AuthDep
from ....contexts.agent_identity.domain.agent_identity import AgentIdentity
from ....contexts.infrastructure.domain.user import Wallet
from ....storage import get_session
from ..domain.agent_performance import (
    LearningStrategy,
    OptimizationTarget,
    PerformanceMetric,
    ResourceAllocation,
)
from ..services.performance import (
    AgentPerformanceService,
    MetaLearningEngine,
    PerformanceOptimizer,
    ResourceManager,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/agent-performance", tags=["agent-performance"])


# PI-API-016: these handlers used to run on AuthLevel.ANY with no ownership
# checks — any JWT could read/write performance state for arbitrary agent_ids
# and deallocate other tenants' ResourceAllocation rows. Ownership resolves
# through AgentIdentity (agent_id -> owner_address -> caller wallets), the
# same model agent-identity routes use (#1070). Admin and api_key callers
# (role=admin) bypass; meta-learning models carry no owner dimension and are
# admin-only.
def _caller_wallets(session: Session, user: dict[str, Any]) -> set[str]:
    """Wallet addresses the authenticated caller controls (users.id -> wallets)."""
    sub = str(user.get("sub") or "")
    if not sub:
        return set()
    return {str(w.address).lower() for w in session.exec(select(Wallet).where(Wallet.user_id == sub)).all() if w.address}


def _is_admin(user: dict[str, Any]) -> bool:
    return user.get("role") == "admin"


def _require_agent_access(session: Session, user: dict[str, Any], agent_id: str) -> None:
    """Caller must be admin or control the wallet owning this agent's identity."""
    if _is_admin(user):
        return
    identity = session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)).first()
    if identity is not None and str(identity.owner_address).lower() in _caller_wallets(session, user):
        return
    raise HTTPException(status_code=403, detail="not the agent owner")


def _require_admin(user: dict[str, Any]) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="admin role required")


class PerformanceProfileRequest(BaseModel):
    """Request model for performance profile creation"""

    agent_id: str
    agent_type: str = Field(default="agent")
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
    cost_per_task: Decimal
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
    request: Request,
    profile_request: PerformanceProfileRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> PerformanceProfileResponse:
    """Create agent performance profile"""
    _require_agent_access(session, user, profile_request.agent_id)
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
        logger.error("Error creating performance profile: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/profiles/{agent_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_performance_profile(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Get agent performance profile"""
    _require_agent_access(session, user, agent_id)
    performance_service = AgentPerformanceService(session)
    try:
        profile = await performance_service.get_comprehensive_profile(agent_id)
        if "error" in profile:
            raise HTTPException(status_code=404, detail=profile["error"])
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting performance profile for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/profiles/{agent_id}/metrics")
@rate_limit(rate=20, per=60)
async def update_performance_metrics(
    request: Request,
    agent_id: str,
    metrics: dict[str, float],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    task_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update agent performance metrics"""
    _require_agent_access(session, user, agent_id)
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
        logger.error("Error updating performance metrics for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/meta-learning/models", response_model=MetaLearningResponse)
@rate_limit(rate=20, per=60)
async def create_meta_learning_model(
    request: Request,
    model_request: MetaLearningRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> MetaLearningResponse:
    """Create meta-learning model"""
    _require_admin(user)
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
        logger.error("Error creating meta-learning model: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/meta-learning/models/{model_id}/adapt")
@rate_limit(rate=20, per=60)
async def adapt_model_to_task(
    request: Request,
    model_id: str,
    task_data: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    adaptation_steps: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Adapt meta-learning model to new task"""
    _require_admin(user)
    meta_learning_engine = MetaLearningEngine()
    try:
        results = await meta_learning_engine.adapt_to_new_task(
            session=session,
            model_id=model_id,
            task_data=task_data,
            adaptation_steps=adaptation_steps,
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error adapting meta-learning model: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


def _allocation_response(allocation: ResourceAllocation) -> ResourceAllocationResponse:
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
        allocated_at=allocation.allocated_at.isoformat() if allocation.allocated_at else "",
    )


@router.post("/resources/allocate", response_model=ResourceAllocationResponse)
@rate_limit(rate=20, per=60)
async def allocate_resources(
    request: Request,
    allocation_request: ResourceAllocationRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> ResourceAllocationResponse:
    """Allocate resources for agent task"""
    _require_agent_access(session, user, allocation_request.agent_id)
    resource_manager = ResourceManager()
    try:
        allocation = await resource_manager.allocate_resources(
            session=session,
            agent_id=allocation_request.agent_id,
            task_requirements=allocation_request.task_requirements,
            optimization_target=allocation_request.optimization_target,
        )
        return _allocation_response(allocation)
    except Exception as e:
        logger.error("Error allocating resources: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/resources", response_model=list[ResourceAllocationResponse])
@rate_limit(rate=60, per=60)
def list_resource_allocations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ResourceAllocationResponse]:
    """List resource allocations, optionally filtered by agent or status"""
    try:
        stmt = select(ResourceAllocation).order_by(desc(ResourceAllocation.created_at)).limit(limit)  # type: ignore[arg-type]
        if not _is_admin(user):
            # Non-admin callers only see allocations for agents they own.
            wallets = _caller_wallets(session, user)
            owned_ids = (
                {
                    i.agent_id
                    for i in session.exec(
                        select(AgentIdentity).where(func.lower(col(AgentIdentity.owner_address)).in_(wallets))
                    ).all()
                }
                if wallets
                else set()
            )
            stmt = stmt.where(col(ResourceAllocation.agent_id).in_(owned_ids)) if owned_ids else stmt.where(False)
        if agent_id:
            _require_agent_access(session, user, agent_id)
            stmt = stmt.where(ResourceAllocation.agent_id == agent_id)
        if status:
            stmt = stmt.where(ResourceAllocation.status == status)
        rows = session.execute(stmt).scalars().all()
        return [_allocation_response(row) for row in rows]
    except Exception as e:
        logger.error("Error listing resource allocations: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/resources/{allocation_id}/deallocate", response_model=ResourceAllocationResponse)
@rate_limit(rate=20, per=60)
def deallocate_resource(
    request: Request,
    allocation_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> ResourceAllocationResponse:
    """Release a resource allocation"""
    try:
        row = session.execute(
            select(ResourceAllocation).where(ResourceAllocation.allocation_id == allocation_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Allocation {allocation_id} not found")
        _require_agent_access(session, user, row.agent_id)
        if row.status in ("released", "completed", "failed"):
            raise HTTPException(status_code=409, detail=f"Allocation {allocation_id} is already {row.status}")
        now = datetime.now(UTC)
        row.status = "released"
        row.completed_at = now
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        logger.info("Released allocation %s for agent %s", allocation_id, row.agent_id)
        return _allocation_response(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deallocating resource %s: %s", allocation_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/optimize", response_model=PerformanceOptimizationResponse)
@rate_limit(rate=20, per=60)
async def optimize_performance(
    request: Request,
    optimization_request: PerformanceOptimizationRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> PerformanceOptimizationResponse:
    """Optimize agent performance"""
    _require_agent_access(session, user, optimization_request.agent_id)
    optimizer = PerformanceOptimizer()
    try:
        optimization = await optimizer.optimize_agent_performance(
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
        logger.error("Error optimizing performance: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/capabilities", response_model=CapabilityResponse)
@rate_limit(rate=20, per=60)
async def create_capability(
    request: Request,
    capability_request: CapabilityRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> CapabilityResponse:
    """Create agent capability"""
    _require_agent_access(session, user, capability_request.agent_id)
    performance_service = AgentPerformanceService(session)
    try:
        capability = await performance_service.create_capability(
            session=session,
            agent_id=capability_request.agent_id,
            capability_name=capability_request.capability_name,
            capability_type=capability_request.capability_type,
            domain_area=capability_request.domain_area,
            skill_level=capability_request.skill_level,
            specialization_areas=capability_request.specialization_areas,
        )
        return CapabilityResponse(
            capability_id=capability.capability_id,
            agent_id=capability.agent_id,
            capability_name=capability.capability_name,
            capability_type=capability.capability_type,
            domain_area=capability.domain_area,
            skill_level=capability.skill_level,
            proficiency_score=capability.proficiency_score,
            specialization_areas=capability.specializations,
            status=capability.status,  # type: ignore[attr-defined]
            created_at=capability.created_at.isoformat(),
        )
    except Exception as e:
        logger.error("Error creating capability: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/capabilities/{agent_id}", response_model=list[CapabilityResponse])
@rate_limit(rate=200, per=60)
async def list_agent_capabilities(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> list[CapabilityResponse]:
    """List all capabilities for an agent"""
    _require_agent_access(session, user, agent_id)
    performance_service = AgentPerformanceService(session)
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
                specialization_areas=cap.specializations,
                status=cap.status,  # type: ignore[attr-defined]
                created_at=cap.created_at.isoformat(),
            )
            for cap in capabilities
        ]
    except Exception as e:
        logger.error("Error listing capabilities for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/analytics/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_performance_analytics(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    period_days: int = 30,
) -> dict[str, Any]:
    """Get performance analytics for an agent"""
    _require_agent_access(session, user, agent_id)
    performance_service = AgentPerformanceService(session)
    try:
        analytics = await performance_service.get_performance_analytics(agent_id, period_days)
        return analytics
    except Exception as e:
        logger.error("Error getting performance analytics for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e
