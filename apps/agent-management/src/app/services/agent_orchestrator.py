"""
Agent Orchestrator Service for hermes Autonomous Economics
Implements multi-agent coordination and sub-task management
"""
import asyncio
from aitbc import get_logger
logger = get_logger(__name__)
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from .bid_strategy_engine import BidResult  # type: ignore[import-not-found]
from .task_decomposition import GPU_Tier, SubTask, SubTaskStatus, TaskDecomposition  # type: ignore[import-not-found]
class OrchestratorStatus(StrEnum):
    """Orchestrator status"""
    IDLE = 'idle'
    PLANNING = 'planning'
    EXECUTING = 'executing'
    MONITORING = 'monitoring'
    FAILED = 'failed'
    COMPLETED = 'completed'

class AgentStatus(StrEnum):
    """Agent status"""
    AVAILABLE = 'available'
    BUSY = 'busy'
    OFFLINE = 'offline'
    MAINTENANCE = 'maintenance'

class ResourceType(StrEnum):
    """Resource types"""
    GPU = 'gpu'
    CPU = 'cpu'
    MEMORY = 'memory'
    STORAGE = 'storage'

@dataclass
class AgentCapability:
    """Agent capability definition"""
    agent_id: str
    supported_task_types: list[str]
    gpu_tier: GPU_Tier
    max_concurrent_tasks: int
    current_load: int
    performance_score: float
    cost_per_hour: float
    reliability_score: float
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class ResourceAllocation:
    """Resource allocation for an agent"""
    agent_id: str
    sub_task_id: str
    resource_type: ResourceType
    allocated_amount: int
    allocated_at: datetime
    expected_duration: float
    actual_duration: float | None = None
    cost: float | None = None

@dataclass
class AgentAssignment:
    """Assignment of sub-task to agent"""
    sub_task_id: str
    agent_id: str
    assigned_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: SubTaskStatus = SubTaskStatus.PENDING
    bid_result: BidResult | None = None
    resource_allocations: list[ResourceAllocation] = field(default_factory=list)
    error_message: str | None = None
    retry_count: int = 0

@dataclass
class OrchestrationPlan:
    """Complete orchestration plan for a task"""
    task_id: str
    decomposition: TaskDecomposition
    agent_assignments: list[AgentAssignment]
    execution_timeline: dict[str, datetime]
    resource_requirements: dict[ResourceType, int]
    estimated_cost: float
    confidence_score: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

class AgentOrchestrator:
    """Multi-agent orchestration service"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.status = OrchestratorStatus.IDLE
        self.agent_capabilities: dict[str, AgentCapability] = {}
        self.agent_status: dict[str, AgentStatus] = {}
        self.active_plans: dict[str, OrchestrationPlan] = {}
        self.completed_plans: list[OrchestrationPlan] = []
        self.failed_plans: list[OrchestrationPlan] = []
        self.resource_allocations: dict[str, list[ResourceAllocation]] = {}
        self.resource_utilization: dict[ResourceType, float] = {}
        self.orchestration_metrics = {'total_tasks': 0, 'successful_tasks': 0, 'failed_tasks': 0, 'average_execution_time': 0.0, 'average_cost': 0.0, 'agent_utilization': 0.0}
        self.max_concurrent_plans = config.get('max_concurrent_plans', 10)
        self.assignment_timeout = config.get('assignment_timeout', 300)
        self.monitoring_interval = config.get('monitoring_interval', 30)
        self.retry_limit = config.get('retry_limit', 3)

    async def initialize(self) -> None:
        """Initialize the orchestrator"""
        logger.info('Initializing Agent Orchestrator')
        await self._load_agent_capabilities()
        asyncio.create_task(self._monitor_executions())
        asyncio.create_task(self._update_agent_status())
        logger.info('Agent Orchestrator initialized')

    async def orchestrate_task(self, task_id: str, decomposition: TaskDecomposition, budget_limit: float | None=None, deadline: datetime | None=None) -> OrchestrationPlan:
        """Orchestrate execution of a decomposed task"""
        try:
            logger.info('Orchestrating task %s with %s sub-tasks', task_id, len(decomposition.sub_tasks))
            if len(self.active_plans) >= self.max_concurrent_plans:
                raise Exception('Orchestrator at maximum capacity')
            self.status = OrchestratorStatus.PLANNING
            plan = await self._create_orchestration_plan(task_id, decomposition, budget_limit, deadline)
            await self._execute_assignments(plan)
            self.active_plans[task_id] = plan
            self.status = OrchestratorStatus.MONITORING
            self.orchestration_metrics['total_tasks'] += 1
            logger.info('Task %s orchestration plan created and started', task_id)
            return plan
        except Exception as e:
            logger.error('Failed to orchestrate task %s: %s', task_id, e)
            self.status = OrchestratorStatus.FAILED
            raise

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get status of orchestrated task"""
        if task_id not in self.active_plans:
            return {'status': 'not_found'}
        plan = self.active_plans[task_id]
        status_counts = {}
        for status in SubTaskStatus:
            status_counts[status.value] = 0
        completed_count = 0
        failed_count = 0
        for assignment in plan.agent_assignments:
            status_counts[assignment.status.value] += 1
            if assignment.status == SubTaskStatus.COMPLETED:
                completed_count += 1
            elif assignment.status == SubTaskStatus.FAILED:
                failed_count += 1
        total_sub_tasks = len(plan.agent_assignments)
        if completed_count == total_sub_tasks:
            overall_status = 'completed'
        elif failed_count > 0:
            overall_status = 'failed'
        elif completed_count > 0:
            overall_status = 'in_progress'
        else:
            overall_status = 'pending'
        return {'status': overall_status, 'progress': completed_count / total_sub_tasks if total_sub_tasks > 0 else 0, 'completed_sub_tasks': completed_count, 'failed_sub_tasks': failed_count, 'total_sub_tasks': total_sub_tasks, 'estimated_cost': plan.estimated_cost, 'actual_cost': await self._calculate_actual_cost(plan), 'started_at': plan.created_at.isoformat(), 'assignments': [{'sub_task_id': a.sub_task_id, 'agent_id': a.agent_id, 'status': a.status.value, 'assigned_at': a.assigned_at.isoformat(), 'started_at': a.started_at.isoformat() if a.started_at else None, 'completed_at': a.completed_at.isoformat() if a.completed_at else None} for a in plan.agent_assignments]}

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel task orchestration"""
        if task_id not in self.active_plans:
            return False
        plan = self.active_plans[task_id]
        for assignment in plan.agent_assignments:
            if assignment.status in [SubTaskStatus.PENDING, SubTaskStatus.IN_PROGRESS]:
                assignment.status = SubTaskStatus.CANCELLED
                await self._release_agent_resources(assignment.agent_id, assignment.sub_task_id)
        self.failed_plans.append(plan)
        del self.active_plans[task_id]
        logger.info('Task %s cancelled', task_id)
        return True

    async def retry_failed_sub_tasks(self, task_id: str) -> list[str]:
        """Retry failed sub-tasks"""
        if task_id not in self.active_plans:
            return []
        plan = self.active_plans[task_id]
        retried_tasks = []
        for assignment in plan.agent_assignments:
            if assignment.status == SubTaskStatus.FAILED and assignment.retry_count < self.retry_limit:
                assignment.status = SubTaskStatus.PENDING
                assignment.started_at = None
                assignment.completed_at = None
                assignment.error_message = None
                assignment.retry_count += 1
                await self._release_agent_resources(assignment.agent_id, assignment.sub_task_id)
                await self._assign_sub_task(assignment.sub_task_id, plan)
                retried_tasks.append(assignment.sub_task_id)
                logger.info('Retrying sub-task %s (attempt %s)', assignment.sub_task_id, assignment.retry_count + 1)
        return retried_tasks

    async def register_agent(self, capability: AgentCapability) -> None:
        """Register a new agent"""
        self.agent_capabilities[capability.agent_id] = capability
        self.agent_status[capability.agent_id] = AgentStatus.AVAILABLE
        logger.info('Registered agent %s', capability.agent_id)

    async def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status"""
        if agent_id in self.agent_status:
            self.agent_status[agent_id] = status
            logger.info('Updated agent %s status to %s', agent_id, status)

    async def get_available_agents(self, task_type: str, gpu_tier: GPU_Tier) -> list[AgentCapability]:
        """Get available agents for task"""
        available_agents = []
        for agent_id, capability in self.agent_capabilities.items():
            if self.agent_status.get(agent_id) == AgentStatus.AVAILABLE and task_type in capability.supported_task_types and (capability.gpu_tier == gpu_tier) and (capability.current_load < capability.max_concurrent_tasks):
                available_agents.append(capability)
        available_agents.sort(key=lambda x: x.performance_score, reverse=True)
        return available_agents

    async def get_orchestration_metrics(self) -> dict[str, Any]:
        """Get orchestration performance metrics"""
        return {'orchestrator_status': self.status.value, 'active_plans': len(self.active_plans), 'completed_plans': len(self.completed_plans), 'failed_plans': len(self.failed_plans), 'registered_agents': len(self.agent_capabilities), 'available_agents': len([s for s in self.agent_status.values() if s == AgentStatus.AVAILABLE]), 'metrics': self.orchestration_metrics, 'resource_utilization': self.resource_utilization}

    async def _create_orchestration_plan(self, task_id: str, decomposition: TaskDecomposition, budget_limit: float | None, deadline: datetime | None) -> OrchestrationPlan:
        """Create detailed orchestration plan"""
        assignments = []
        execution_timeline = {}
        resource_requirements = dict.fromkeys(ResourceType, 0)
        total_cost = 0.0
        for stage_idx, stage_sub_tasks in enumerate(decomposition.execution_plan):
            stage_start = datetime.now(UTC) + timedelta(hours=stage_idx * 2)
            for sub_task_id in stage_sub_tasks:
                sub_task = next((st for st in decomposition.sub_tasks if st.sub_task_id == sub_task_id))
                assignment = AgentAssignment(sub_task_id=sub_task_id, agent_id='', assigned_at=datetime.now(UTC))
                assignments.append(assignment)
                resource_requirements[ResourceType.GPU] += 1
                resource_requirements[ResourceType.MEMORY] += sub_task.requirements.memory_requirement
                execution_timeline[sub_task_id] = stage_start
        confidence_score = await self._calculate_plan_confidence(decomposition, budget_limit, deadline)
        return OrchestrationPlan(task_id=task_id, decomposition=decomposition, agent_assignments=assignments, execution_timeline=execution_timeline, resource_requirements=resource_requirements, estimated_cost=total_cost, confidence_score=confidence_score)

    async def _execute_assignments(self, plan: OrchestrationPlan) -> None:
        """Execute agent assignments"""
        for assignment in plan.agent_assignments:
            await self._assign_sub_task(assignment.sub_task_id, plan)

    async def _assign_sub_task(self, sub_task_id: str, plan: OrchestrationPlan) -> None:
        """Assign sub-task to suitable agent"""
        sub_task = next((st for st in plan.decomposition.sub_tasks if st.sub_task_id == sub_task_id))
        available_agents = await self.get_available_agents(sub_task.requirements.task_type.value, sub_task.requirements.gpu_tier)
        if not available_agents:
            raise Exception(f'No available agents for sub-task {sub_task_id}')
        best_agent = await self._select_best_agent(available_agents, sub_task)
        assignment = next((a for a in plan.agent_assignments if a.sub_task_id == sub_task_id))
        assignment.agent_id = best_agent.agent_id
        assignment.status = SubTaskStatus.ASSIGNED
        self.agent_capabilities[best_agent.agent_id].current_load += 1
        self.agent_status[best_agent.agent_id] = AgentStatus.BUSY
        await self._allocate_resources(best_agent.agent_id, sub_task_id, sub_task.requirements)
        logger.info('Assigned sub-task %s to agent %s', sub_task_id, best_agent.agent_id)

    async def _select_best_agent(self, available_agents: list[AgentCapability], sub_task: SubTask) -> AgentCapability:
        """Select best agent for sub-task"""
        scored_agents = []
        for agent in available_agents:
            score = 0.0
            score += agent.performance_score * 0.4
            cost_efficiency = min(1.0, 0.05 / agent.cost_per_hour)
            score += cost_efficiency * 0.3
            score += agent.reliability_score * 0.2
            load_factor = 1.0 - agent.current_load / agent.max_concurrent_tasks
            score += load_factor * 0.1
            scored_agents.append((agent, score))
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        return scored_agents[0][0]

    async def _allocate_resources(self, agent_id: str, sub_task_id: str, requirements: Any) -> None:
        """Allocate resources for sub-task"""
        allocations = []
        gpu_allocation = ResourceAllocation(agent_id=agent_id, sub_task_id=sub_task_id, resource_type=ResourceType.GPU, allocated_amount=1, allocated_at=datetime.now(UTC), expected_duration=requirements.estimated_duration)
        allocations.append(gpu_allocation)
        memory_allocation = ResourceAllocation(agent_id=agent_id, sub_task_id=sub_task_id, resource_type=ResourceType.MEMORY, allocated_amount=requirements.memory_requirement, allocated_at=datetime.now(UTC), expected_duration=requirements.estimated_duration)
        allocations.append(memory_allocation)
        if agent_id not in self.resource_allocations:
            self.resource_allocations[agent_id] = []
        self.resource_allocations[agent_id].extend(allocations)

    async def _release_agent_resources(self, agent_id: str, sub_task_id: str) -> None:
        """Release resources from agent"""
        if agent_id in self.resource_allocations:
            self.resource_allocations[agent_id] = [alloc for alloc in self.resource_allocations[agent_id] if alloc.sub_task_id != sub_task_id]
        if agent_id in self.agent_capabilities:
            self.agent_capabilities[agent_id].current_load = max(0, self.agent_capabilities[agent_id].current_load - 1)
            if self.agent_capabilities[agent_id].current_load == 0:
                self.agent_status[agent_id] = AgentStatus.AVAILABLE

    async def _monitor_executions(self) -> None:
        """Monitor active executions"""
        while True:
            try:
                completed_tasks = []
                failed_tasks = []
                for task_id, plan in list(self.active_plans.items()):
                    all_completed = all((a.status == SubTaskStatus.COMPLETED for a in plan.agent_assignments))
                    any_failed = any((a.status == SubTaskStatus.FAILED for a in plan.agent_assignments))
                    if all_completed:
                        completed_tasks.append(task_id)
                    elif any_failed:
                        all_failed_exhausted = all((a.status == SubTaskStatus.FAILED and a.retry_count >= self.retry_limit for a in plan.agent_assignments if a.status == SubTaskStatus.FAILED))
                        if all_failed_exhausted:
                            failed_tasks.append(task_id)
                for task_id in completed_tasks:
                    plan = self.active_plans[task_id]
                    self.completed_plans.append(plan)
                    del self.active_plans[task_id]
                    self.orchestration_metrics['successful_tasks'] += 1
                    logger.info('Task %s completed successfully', task_id)
                for task_id in failed_tasks:
                    plan = self.active_plans[task_id]
                    self.failed_plans.append(plan)
                    del self.active_plans[task_id]
                    self.orchestration_metrics['failed_tasks'] += 1
                    logger.info('Task %s failed', task_id)
                await self._update_resource_utilization()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error('Error in execution monitoring: %s', e)
                await asyncio.sleep(60)

    async def _update_agent_status(self) -> None:
        """Update agent status periodically"""
        while True:
            try:
                for agent_id in self.agent_capabilities.keys():
                    capability = self.agent_capabilities[agent_id]
                    time_since_update = datetime.now(UTC) - capability.last_updated
                    if time_since_update > timedelta(minutes=5):
                        if self.agent_status[agent_id] != AgentStatus.OFFLINE:
                            self.agent_status[agent_id] = AgentStatus.OFFLINE
                            logger.warning('Agent %s marked as offline', agent_id)
                    elif self.agent_status[agent_id] == AgentStatus.OFFLINE:
                        self.agent_status[agent_id] = AgentStatus.AVAILABLE
                        logger.info('Agent %s back online', agent_id)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error('Error updating agent status: %s', e)
                await asyncio.sleep(60)

    async def _update_resource_utilization(self) -> None:
        """Update resource utilization metrics"""
        total_resources = dict.fromkeys(ResourceType, 0)
        used_resources = dict.fromkeys(ResourceType, 0)
        for capability in self.agent_capabilities.values():
            total_resources[ResourceType.GPU] += capability.max_concurrent_tasks
        for allocations in self.resource_allocations.values():
            for allocation in allocations:
                used_resources[allocation.resource_type] += allocation.allocated_amount
        for resource_type in ResourceType:
            total = total_resources[resource_type]
            used = used_resources[resource_type]
            self.resource_utilization[resource_type] = used / total if total > 0 else 0.0

    async def _calculate_plan_confidence(self, decomposition: TaskDecomposition, budget_limit: float | None, deadline: datetime | None) -> float:
        """Calculate confidence in orchestration plan"""
        confidence = decomposition.confidence_score
        if budget_limit and decomposition.estimated_total_cost > budget_limit:
            confidence *= 0.7
        if deadline:
            time_to_deadline = (deadline - datetime.now(UTC)).total_seconds() / 3600
            if time_to_deadline < decomposition.estimated_total_duration:
                confidence *= 0.6
        available_agents = len([s for s in self.agent_status.values() if s == AgentStatus.AVAILABLE])
        total_agents = len(self.agent_capabilities)
        if total_agents > 0:
            availability_ratio = available_agents / total_agents
            confidence *= 0.5 + availability_ratio * 0.5
        return float(max(0.1, min(0.95, confidence)))

    async def _calculate_actual_cost(self, plan: OrchestrationPlan) -> float:
        """Calculate actual cost of orchestration"""
        actual_cost = 0.0
        for assignment in plan.agent_assignments:
            if assignment.agent_id in self.agent_capabilities:
                agent = self.agent_capabilities[assignment.agent_id]
                duration = assignment.actual_duration or 1.0  # type: ignore[attr-defined]
                cost = agent.cost_per_hour * duration
                actual_cost += cost
        return actual_cost

    async def _load_agent_capabilities(self) -> None:
        """Load agent capabilities from storage"""
        mock_agents = [AgentCapability(agent_id='agent_001', supported_task_types=['text_processing', 'data_analysis'], gpu_tier=GPU_Tier.MID_RANGE_GPU, max_concurrent_tasks=3, current_load=0, performance_score=0.85, cost_per_hour=0.05, reliability_score=0.92), AgentCapability(agent_id='agent_002', supported_task_types=['image_processing', 'model_inference'], gpu_tier=GPU_Tier.HIGH_END_GPU, max_concurrent_tasks=2, current_load=0, performance_score=0.92, cost_per_hour=0.09, reliability_score=0.88), AgentCapability(agent_id='agent_003', supported_task_types=['compute_intensive', 'model_training'], gpu_tier=GPU_Tier.PREMIUM_GPU, max_concurrent_tasks=1, current_load=0, performance_score=0.96, cost_per_hour=0.15, reliability_score=0.95)]
        for agent in mock_agents:
            await self.register_agent(agent)