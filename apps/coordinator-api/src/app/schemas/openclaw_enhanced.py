"""
OpenClaw Enhanced Pydantic Schemas - Phase 6.6
Request and response models for advanced OpenClaw integration features
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SkillType(StrEnum):
    """Agent skill types"""

    INFERENCE = "inference"
    TRAINING = "training"
    DATA_PROCESSING = "data_processing"
    VERIFICATION = "verification"
    CUSTOM = "custom"


class ExecutionMode(StrEnum):
    """Agent execution modes"""

    LOCAL = "local"
    AITBC_OFFLOAD = "aitbc_offload"
    HYBRID = "hybrid"


class CoordinationAlgorithm(StrEnum):
    """Agent coordination algorithms"""

    DISTRIBUTED_CONSENSUS = "distributed_consensus"
    CENTRAL_COORDINATION = "central_coordination"


class OptimizationStrategy(StrEnum):
    """Hybrid execution optimization strategies"""

    PERFORMANCE = "performance"
    COST = "cost"
    BALANCED = "balanced"


# Request Models
class SkillRoutingRequest(BaseModel):
    """Request for agent skill routing"""

    skill_type: SkillType = Field(..., description="Type of skill required")
    requirements: dict[str, Any] = Field(..., description="Skill requirements")
    performance_optimization: bool = Field(default=True, description="Enable performance optimization")


class JobOffloadingRequest(BaseModel):
    """Request for intelligent job offloading"""

    job_data: dict[str, Any] = Field(..., description="Job data and requirements")
    cost_optimization: bool = Field(default=True, description="Enable cost optimization")
    performance_analysis: bool = Field(default=True, description="Enable performance analysis")


class AgentCollaborationRequest(BaseModel):
    """Request for agent collaboration"""

    task_data: dict[str, Any] = Field(..., description="Task data and requirements")
    agent_ids: list[str] = Field(..., description="List of agent IDs to coordinate")
    coordination_algorithm: CoordinationAlgorithm = Field(
        default=CoordinationAlgorithm.DISTRIBUTED_CONSENSUS, description="Coordination algorithm"
    )


class HybridExecutionRequest(BaseModel):
    """Request for hybrid execution optimization"""

    execution_request: dict[str, Any] = Field(..., description="Execution request data")
    optimization_strategy: OptimizationStrategy = Field(
        default=OptimizationStrategy.PERFORMANCE, description="Optimization strategy"
    )


class EdgeDeploymentRequest(BaseModel):
    """Request for edge deployment"""

    agent_id: str = Field(..., description="Agent ID to deploy")
    edge_locations: list[str] = Field(..., description="Edge locations for deployment")
    deployment_config: dict[str, Any] = Field(..., description="Deployment configuration")


class EdgeCoordinationRequest(BaseModel):
    """Request for edge-to-cloud coordination"""

    edge_deployment_id: str = Field(..., description="Edge deployment ID")
    coordination_config: dict[str, Any] = Field(..., description="Coordination configuration")


class EcosystemDevelopmentRequest(BaseModel):
    """Request for ecosystem development"""

    ecosystem_config: dict[str, Any] = Field(..., description="Ecosystem configuration")


# Response Models
class SkillRoutingResponse(BaseModel):
    """Response for agent skill routing"""

    selected_agent: dict[str, Any] = Field(..., description="Selected agent details")
    routing_strategy: str = Field(..., description="Routing strategy used")
    expected_performance: float = Field(..., description="Expected performance score")
    estimated_cost: float = Field(..., description="Estimated cost per hour")


class JobOffloadingResponse(BaseModel):
    """Response for intelligent job offloading"""

    should_offload: bool = Field(..., description="Whether job should be offloaded")
    job_size: dict[str, Any] = Field(..., description="Job size analysis")
    cost_analysis: dict[str, Any] = Field(..., description="Cost-benefit analysis")
    performance_prediction: dict[str, Any] = Field(..., description="Performance prediction")
    fallback_mechanism: str = Field(..., description="Fallback mechanism")


class AgentCollaborationResponse(BaseModel):
    """Response for agent collaboration"""

    coordination_method: str = Field(..., description="Coordination method used")
    selected_coordinator: str = Field(..., description="Selected coordinator agent ID")
    consensus_reached: bool = Field(..., description="Whether consensus was reached")
    task_distribution: dict[str, str] = Field(..., description="Task distribution among agents")
    estimated_completion_time: float = Field(..., description="Estimated completion time in seconds")


class HybridExecutionResponse(BaseModel):
    """Response for hybrid execution optimization"""

    execution_mode: str = Field(..., description="Execution mode")
    strategy: dict[str, Any] = Field(..., description="Optimization strategy")
    resource_allocation: dict[str, Any] = Field(..., description="Resource allocation")
    performance_tuning: dict[str, Any] = Field(..., description="Performance tuning parameters")
    expected_improvement: str = Field(..., description="Expected improvement description")


class EdgeDeploymentResponse(BaseModel):
    """Response for edge deployment"""

    deployment_id: str = Field(..., description="Deployment ID")
    agent_id: str = Field(..., description="Agent ID")
    edge_locations: list[str] = Field(..., description="Deployed edge locations")
    deployment_results: list[dict[str, Any]] = Field(..., description="Deployment results per location")
    status: str = Field(..., description="Deployment status")


class EdgeCoordinationResponse(BaseModel):
    """Response for edge-to-cloud coordination"""

    coordination_id: str = Field(..., description="Coordination ID")
    edge_deployment_id: str = Field(..., description="Edge deployment ID")
    synchronization: dict[str, Any] = Field(..., description="Synchronization status")
    load_balancing: dict[str, Any] = Field(..., description="Load balancing configuration")
    failover: dict[str, Any] = Field(..., description="Failover configuration")
    status: str = Field(..., description="Coordination status")


class EcosystemDevelopmentResponse(BaseModel):
    """Response for ecosystem development"""

    ecosystem_id: str = Field(..., description="Ecosystem ID")
    developer_tools: dict[str, Any] = Field(..., description="Developer tools information")
    marketplace: dict[str, Any] = Field(..., description="Marketplace information")
    community: dict[str, Any] = Field(..., description="Community information")
    partnerships: dict[str, Any] = Field(..., description="Partnership information")
    status: str = Field(..., description="Ecosystem status")
