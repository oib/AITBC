"""
Load Balancer for Agent Distribution and Task Assignment
"""
import asyncio
import hashlib
import json
import statistics
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from aitbc import get_logger

from ..protocols.communication import AgentMessage
from ..protocols.message_types import create_task_message
from .agent_discovery import AgentRegistry, AgentStatus

logger = get_logger(__name__)

class LoadBalancingStrategy(StrEnum):
    """Load balancing strategies"""
    ROUND_ROBIN = 'round_robin'
    LEAST_CONNECTIONS = 'least_connections'
    LEAST_RESPONSE_TIME = 'least_response_time'
    WEIGHTED_ROUND_ROBIN = 'weighted_round_robin'
    RESOURCE_BASED = 'resource_based'
    CAPABILITY_BASED = 'capability_based'
    PREDICTIVE = 'predictive'
    CONSISTENT_HASH = 'consistent_hash'

class TaskPriority(StrEnum):
    """Task priority levels"""
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    CRITICAL = 'critical'
    URGENT = 'urgent'

@dataclass
class LoadMetrics:
    """Agent load metrics"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    active_connections: int = 0
    pending_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_response_time: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {'cpu_usage': self.cpu_usage, 'memory_usage': self.memory_usage, 'active_connections': self.active_connections, 'pending_tasks': self.pending_tasks, 'completed_tasks': self.completed_tasks, 'failed_tasks': self.failed_tasks, 'avg_response_time': self.avg_response_time, 'last_updated': self.last_updated.isoformat()}

@dataclass
class TaskAssignment:
    """Task assignment record"""
    task_id: str
    agent_id: str
    assigned_at: datetime
    completed_at: datetime | None = None
    status: str = 'pending'
    response_time: float | None = None
    success: bool = False
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {'task_id': self.task_id, 'agent_id': self.agent_id, 'assigned_at': self.assigned_at.isoformat(), 'completed_at': self.completed_at.isoformat() if self.completed_at else None, 'status': self.status, 'response_time': self.response_time, 'success': self.success, 'error_message': self.error_message}

@dataclass
class AgentWeight:
    """Agent weight for load balancing"""
    agent_id: str
    weight: float = 1.0
    capacity: int = 100
    performance_score: float = 1.0
    reliability_score: float = 1.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

class LoadBalancer:
    """Advanced load balancer for agent distribution"""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.strategy = LoadBalancingStrategy.LEAST_CONNECTIONS
        self.agent_weights: dict[str, AgentWeight] = {}
        self.agent_metrics: dict[str, LoadMetrics] = {}
        self.task_assignments: dict[str, TaskAssignment] = {}
        self.assignment_history: deque[Any] = deque(maxlen=1000)
        self.round_robin_index = 0
        self.consistent_hash_ring: dict[int, str] = {}
        self.prediction_models: dict[str, Any] = {}
        self.total_assignments = 0
        self.successful_assignments = 0
        self.failed_assignments = 0

    def set_strategy(self, strategy: LoadBalancingStrategy) -> None:
        """Set load balancing strategy"""
        self.strategy = strategy
        logger.info('Load balancing strategy changed to: %s', strategy.value)

    def set_agent_weight(self, agent_id: str, weight: float, capacity: int = 100) -> None:
        """Set agent weight and capacity"""
        self.agent_weights[agent_id] = AgentWeight(agent_id=agent_id, weight=weight, capacity=capacity)
        logger.info('Set weight for agent %s: %s, capacity: %s', agent_id, weight, capacity)

    def update_agent_metrics(self, agent_id: str, metrics: LoadMetrics) -> None:
        """Update agent load metrics"""
        self.agent_metrics[agent_id] = metrics
        self.agent_metrics[agent_id].last_updated = datetime.now(UTC)
        self._update_performance_score(agent_id, metrics)

    def _update_performance_score(self, agent_id: str, metrics: LoadMetrics) -> None:
        """Update agent performance score based on metrics"""
        if agent_id not in self.agent_weights:
            self.agent_weights[agent_id] = AgentWeight(agent_id=agent_id)
        weight = self.agent_weights[agent_id]
        performance_factors = []
        cpu_factor = max(0.0, 1.0 - metrics.cpu_usage)
        performance_factors.append(cpu_factor)
        memory_factor = max(0.0, 1.0 - metrics.memory_usage)
        performance_factors.append(memory_factor)
        if metrics.avg_response_time > 0:
            response_factor = max(0.0, 1.0 - metrics.avg_response_time / 10.0)
            performance_factors.append(response_factor)
        total_tasks = metrics.completed_tasks + metrics.failed_tasks
        if total_tasks > 0:
            success_rate = metrics.completed_tasks / total_tasks
            performance_factors.append(success_rate)
        if performance_factors:
            weight.performance_score = statistics.mean(performance_factors)
        if total_tasks > 10:
            weight.reliability_score = success_rate

    async def assign_task(self, task_data: dict[str, Any], requirements: dict[str, Any] | None = None) -> str | None:
        """Assign task to best available agent"""
        try:
            eligible_agents = await self._find_eligible_agents(task_data, requirements)
            if not eligible_agents:
                logger.warning('No eligible agents found for task assignment')
                return None
            selected_agent = await self._select_agent(eligible_agents, task_data)
            if not selected_agent:
                logger.warning('No agent selected for task assignment')
                return None
            task_id = str(uuid.uuid4())
            assignment = TaskAssignment(task_id=task_id, agent_id=selected_agent, assigned_at=datetime.now(UTC))
            self.task_assignments[task_id] = assignment
            self.assignment_history.append(assignment)
            self.total_assignments += 1
            if selected_agent not in self.agent_metrics:
                self.agent_metrics[selected_agent] = LoadMetrics()
            self.agent_metrics[selected_agent].pending_tasks += 1
            logger.info('Task %s assigned to agent %s', task_id, selected_agent)
            return selected_agent
        except Exception as e:
            logger.error('Error assigning task: %s', e)
            self.failed_assignments += 1
            return None

    async def complete_task(self, task_id: str, success: bool, response_time: float | None = None, error_message: str | None = None) -> None:
        """Mark task as completed"""
        try:
            if task_id not in self.task_assignments:
                logger.warning('Task assignment %s not found', task_id)
                return
            assignment = self.task_assignments[task_id]
            assignment.completed_at = datetime.now(UTC)
            assignment.status = 'completed'
            assignment.success = success
            assignment.response_time = response_time
            assignment.error_message = error_message
            agent_id = assignment.agent_id
            if agent_id in self.agent_metrics:
                metrics = self.agent_metrics[agent_id]
                metrics.pending_tasks = max(0, metrics.pending_tasks - 1)
                if success:
                    metrics.completed_tasks += 1
                    self.successful_assignments += 1
                else:
                    metrics.failed_tasks += 1
                    self.failed_assignments += 1
                if response_time:
                    total_completed = metrics.completed_tasks + metrics.failed_tasks
                    if total_completed > 0:
                        metrics.avg_response_time = (metrics.avg_response_time * (total_completed - 1) + response_time) / total_completed
            logger.info('Task %s completed by agent %s, success: %s', task_id, assignment.agent_id, success)
        except Exception as e:
            logger.error('Error completing task %s: %s', task_id, e)

    async def _find_eligible_agents(self, task_data: dict[str, Any], requirements: dict[str, Any] | None = None) -> list[str]:
        """Find eligible agents for task"""
        logger.warning('=' * 60)
        logger.warning('DEBUG: _find_eligible_agents() CALLED - NEW CODE LOADED')
        logger.warning('=' * 60)
        try:
            query = {'status': AgentStatus.ACTIVE}
            if requirements:
                if 'agent_type' in requirements:
                    query['agent_type'] = requirements['agent_type']
                if 'capabilities' in requirements:
                    query['capabilities'] = requirements['capabilities']
                if 'services' in requirements:
                    query['services'] = requirements['services']
                if 'min_health_score' in requirements:
                    query['min_health_score'] = requirements['min_health_score']
            agents = await self.registry.discover_agents(query)
            logger.info('Found %s agents from registry with query %s', len(agents), query)
            eligible_agents = []
            for agent in agents:
                agent_id = agent.agent_id
                logger.info('Checking agent %s for eligibility', agent_id)
                if agent_id in self.agent_weights:
                    weight = self.agent_weights[agent_id]
                    current_load = self._get_agent_load(agent_id)
                    logger.info('Agent %s: in agent_weights, load=%s, capacity=%s', agent_id, current_load, weight.capacity)
                    if current_load < weight.capacity:
                        eligible_agents.append(agent_id)
                else:
                    metrics = self.agent_metrics.get(agent_id, LoadMetrics())
                    logger.info('Agent %s: not in agent_weights, pending_tasks=%s', agent_id, metrics.pending_tasks)
                    if metrics.pending_tasks < 100:
                        eligible_agents.append(agent_id)
            logger.info('Eligible agents after filtering: %s', eligible_agents)
            logger.warning('=' * 60)
            logger.warning('DEBUG: RETURNING %s ELIGIBLE AGENTS', len(eligible_agents))
            logger.warning('=' * 60)
            return eligible_agents
        except Exception as e:
            logger.error('Error finding eligible agents: %s', e)
            return []

    def _get_agent_load(self, agent_id: str) -> int:
        """Get current load for agent"""
        metrics = self.agent_metrics.get(agent_id, LoadMetrics())
        return metrics.active_connections + metrics.pending_tasks

    async def _select_agent(self, eligible_agents: list[str], task_data: dict[str, Any]) -> str | None:
        """Select best agent based on current strategy"""
        if not eligible_agents:
            return None
        logger.warning('DEBUG: _select_agent called with %s eligible agents: %s', len(eligible_agents), eligible_agents)
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            selection = self._round_robin_selection(eligible_agents)
            logger.warning('DEBUG: Round robin selected: %s', selection)
            return selection
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            selection = self._least_connections_selection(eligible_agents)
            logger.warning('DEBUG: Least connections selected: %s', selection)
            return selection
        elif self.strategy == LoadBalancingStrategy.LEAST_RESPONSE_TIME:
            return self._least_response_time_selection(eligible_agents)
        elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_selection(eligible_agents)
        elif self.strategy == LoadBalancingStrategy.RESOURCE_BASED:
            return self._resource_based_selection(eligible_agents)
        elif self.strategy == LoadBalancingStrategy.CAPABILITY_BASED:
            return self._capability_based_selection(eligible_agents, task_data)
        elif self.strategy == LoadBalancingStrategy.PREDICTIVE:
            return self._predictive_selection(eligible_agents, task_data)
        elif self.strategy == LoadBalancingStrategy.CONSISTENT_HASH:
            return self._consistent_hash_selection(eligible_agents, task_data)
        else:
            return eligible_agents[0]

    def _round_robin_selection(self, agents: list[str]) -> str:
        """Round-robin agent selection"""
        agent = agents[self.round_robin_index % len(agents)]
        self.round_robin_index += 1
        return agent

    def _least_connections_selection(self, agents: list[str]) -> str:
        """Select agent with least connections"""
        min_connections = float('inf')
        selected_agent = None
        for agent_id in agents:
            metrics = self.agent_metrics.get(agent_id, LoadMetrics())
            connections = metrics.pending_tasks
            if connections < min_connections:
                min_connections = connections
                selected_agent = agent_id
        return selected_agent or agents[0]

    def _least_response_time_selection(self, agents: list[str]) -> str:
        """Select agent with least average response time"""
        min_response_time = float('inf')
        selected_agent = None
        for agent_id in agents:
            metrics = self.agent_metrics.get(agent_id, LoadMetrics())
            response_time = metrics.avg_response_time
            if response_time < min_response_time:
                min_response_time = response_time
                selected_agent = agent_id
        return selected_agent or agents[0]

    def _weighted_round_robin_selection(self, agents: list[str]) -> str:
        """Weighted round-robin selection"""
        total_weight = 0.0
        for agent_id in agents:
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            total_weight += weight.weight
        if total_weight == 0:
            return agents[0]
        current_weight = self.round_robin_index % total_weight
        accumulated_weight = 0.0
        for agent_id in agents:
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            accumulated_weight += weight.weight
            if current_weight < accumulated_weight:
                self.round_robin_index += 1
                return agent_id
        return agents[0]

    def _resource_based_selection(self, agents: list[str]) -> str:
        """Resource-based selection considering CPU and memory"""
        best_score = -1.0
        selected_agent = None
        for agent_id in agents:
            metrics = self.agent_metrics.get(agent_id, LoadMetrics())
            cpu_score = max(0, 100 - metrics.cpu_usage)
            memory_score = max(0, 100 - metrics.memory_usage)
            resource_score = (cpu_score + memory_score) / 2
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            final_score = resource_score * weight.performance_score
            if final_score > best_score:
                best_score = final_score
                selected_agent = agent_id
        return selected_agent or agents[0]

    def _capability_based_selection(self, agents: list[str], task_data: dict[str, Any]) -> str:
        """Capability-based selection considering task requirements"""
        required_capabilities = task_data.get('required_capabilities', [])
        if not required_capabilities:
            return agents[0]
        best_score = -1.0
        selected_agent = None
        for agent_id in agents:
            agent_info = self.registry.agents.get(agent_id)
            if not agent_info:
                continue
            agent_capabilities = set(agent_info.capabilities)
            required_set = set(required_capabilities)
            if required_set.issubset(agent_capabilities):
                capability_score = 1.0
            else:
                intersection = required_set.intersection(agent_capabilities)
                capability_score = len(intersection) / len(required_set)
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            final_score = capability_score * weight.performance_score
            if final_score > best_score:
                best_score = final_score
                selected_agent = agent_id
        return selected_agent or agents[0]

    def _predictive_selection(self, agents: list[str], task_data: dict[str, Any]) -> str:
        """Predictive selection using historical performance"""
        task_type = task_data.get('task_type', 'unknown')
        best_score = -1.0
        selected_agent = None
        for agent_id in agents:
            score = self._calculate_predicted_score(agent_id, task_type)
            if score > best_score:
                best_score = score
                selected_agent = agent_id
        return selected_agent or agents[0]

    def _calculate_predicted_score(self, agent_id: str, task_type: str) -> float:
        """Calculate predicted performance score for agent"""
        weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
        base_score = (weight.performance_score + weight.reliability_score) / 2
        recent_assignments = [a for a in self.assignment_history if a.agent_id == agent_id][-10:]
        if recent_assignments:
            success_rate = sum(1 for a in recent_assignments if a.success) / len(recent_assignments)
            base_score = base_score * 0.7 + success_rate * 0.3
        return base_score

    def _consistent_hash_selection(self, agents: list[str], task_data: dict[str, Any]) -> str:
        """Consistent hash selection for sticky routing"""
        hash_key = json.dumps(task_data, sort_keys=True)
        hash_value = int(hashlib.sha256(hash_key.encode()).hexdigest(), 16)
        if not self.consistent_hash_ring:
            self._build_hash_ring(agents)
        for hash_pos in sorted(self.consistent_hash_ring.keys()):
            if hash_value <= hash_pos:
                return self.consistent_hash_ring[hash_pos]
        return self.consistent_hash_ring[min(self.consistent_hash_ring.keys())]

    def _build_hash_ring(self, agents: list[str]) -> None:
        """Build consistent hash ring"""
        self.consistent_hash_ring = {}
        for agent_id in agents:
            for i in range(100):
                virtual_key = f'{agent_id}:{i}'
                hash_value = int(hashlib.sha256(virtual_key.encode()).hexdigest(), 16)
                self.consistent_hash_ring[hash_value] = agent_id

    def get_load_balancing_stats(self) -> dict[str, Any]:
        """Get load balancing statistics"""
        return {'strategy': self.strategy.value, 'total_assignments': self.total_assignments, 'successful_assignments': self.successful_assignments, 'failed_assignments': self.failed_assignments, 'success_rate': self.successful_assignments / max(1, self.total_assignments), 'active_agents': len(self.agent_metrics), 'agent_weights': len(self.agent_weights), 'avg_agent_load': statistics.mean([self._get_agent_load(a) for a in self.agent_metrics]) if self.agent_metrics else 0}

    def get_agent_stats(self, agent_id: str) -> dict[str, Any] | None:
        """Get detailed statistics for a specific agent"""
        if agent_id not in self.agent_metrics:
            return None
        metrics = self.agent_metrics[agent_id]
        weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
        recent_assignments = [a for a in self.assignment_history if a.agent_id == agent_id][-10:]
        return {'agent_id': agent_id, 'metrics': metrics.to_dict(), 'weight': {'weight': weight.weight, 'capacity': weight.capacity, 'performance_score': weight.performance_score, 'reliability_score': weight.reliability_score}, 'recent_assignments': [a.to_dict() for a in recent_assignments], 'current_load': self._get_agent_load(agent_id)}

class TaskDistributor:
    """Task distributor with advanced load balancing"""

    def __init__(self, load_balancer: LoadBalancer) -> None:
        self.load_balancer = load_balancer
        self.task_queue: asyncio.Queue[Any] = asyncio.Queue()
        self.priority_queues: dict[TaskPriority, asyncio.Queue[Any]] = {TaskPriority.URGENT: asyncio.Queue(), TaskPriority.CRITICAL: asyncio.Queue(), TaskPriority.HIGH: asyncio.Queue(), TaskPriority.NORMAL: asyncio.Queue(), TaskPriority.LOW: asyncio.Queue()}
        self.distribution_stats = {'tasks_distributed': 0, 'tasks_completed': 0, 'tasks_failed': 0, 'avg_distribution_time': 0.0}

    async def submit_task(self, task_data: dict[str, Any], priority: TaskPriority = TaskPriority.NORMAL, requirements: dict[str, Any] | None = None) -> None:
        """Submit task for distribution"""
        task_info = {'task_data': task_data, 'priority': priority, 'requirements': requirements, 'submitted_at': datetime.now(UTC)}
        await self.priority_queues[priority].put(task_info)
        logger.info('Task submitted with priority %s', priority.value)

    async def start_distribution(self) -> None:
        """Start task distribution loop"""
        logger.warning('=' * 60)
        logger.warning('DEBUG: TASK DISTRIBUTION LOOP STARTED')
        logger.warning('=' * 60)
        while True:
            try:
                task_info = None
                for priority in [TaskPriority.URGENT, TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
                    queue = self.priority_queues[priority]
                    try:
                        task_info = queue.get_nowait()
                        logger.info('Got task from %s queue', priority.value)
                        break
                    except asyncio.QueueEmpty:
                        continue
                if task_info:
                    await self._distribute_task(task_info)
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.error('Error in distribution loop: %s', e)
                await asyncio.sleep(1)

    async def _distribute_task(self, task_info: dict[str, Any]) -> None:
        """Distribute a single task"""
        start_time = datetime.now(UTC)
        try:
            agent_id = await self.load_balancer.assign_task(task_info['task_data'], task_info['requirements'])
            if agent_id:
                task_message = create_task_message(sender_id='task_distributor', receiver_id=agent_id, task_type=task_info['task_data'].get('task_type', 'unknown'), task_data=task_info['task_data'])
                send_success = await self._send_task_to_agent(agent_id, task_message)
                if send_success:
                    self.distribution_stats['tasks_distributed'] += 1
                else:
                    logger.warning('Failed to send task to agent %s', agent_id)
                    self.distribution_stats['tasks_failed'] += 1
            else:
                logger.warning('Failed to distribute task: no suitable agent found')
                self.distribution_stats['tasks_failed'] += 1
        except Exception as e:
            logger.error('Error distributing task: %s', e)
            self.distribution_stats['tasks_failed'] += 1
        finally:
            distribution_time = (datetime.now(UTC) - start_time).total_seconds()
            total_distributed = self.distribution_stats['tasks_distributed']
            self.distribution_stats['avg_distribution_time'] = (self.distribution_stats['avg_distribution_time'] * (total_distributed - 1) + distribution_time) / total_distributed if total_distributed > 0 else distribution_time

    async def _send_task_to_agent(self, agent_id: str, task_message: AgentMessage) -> bool:
        """Send task to agent via HTTP"""
        try:
            agent_info = await self.load_balancer.registry.get_agent_by_id(agent_id)
            if not agent_info:
                logger.error('Agent %s not found in registry', agent_id)
                return False
            http_endpoint = agent_info.endpoints.get('http')
            if not http_endpoint:
                logger.error('Agent %s has no HTTP endpoint', agent_id)
                return False
            message_dict = task_message.to_dict()

            def convert_datetime(obj: Any) -> str | dict[str, Any] | list[Any] | Any:
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                return obj
            message_dict['payload'] = convert_datetime(message_dict['payload'])
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(f'{http_endpoint}/tasks/execute', json=message_dict)
                if response.status_code in (200, 201, 202):
                    logger.info('Task sent successfully to agent %s', agent_id)
                    return True
                else:
                    logger.error('Failed to send task to agent %s: %s', agent_id, response.status_code)
                    return False
        except Exception as e:
            logger.error('Error sending task to agent %s: %s', agent_id, e)
            return False

    async def _simulate_task_completion(self, task_info: dict[str, Any], agent_id: str) -> None:
        """Simulate task completion (for testing)"""
        processing_time = 1.0 + hash(task_info['task_data'].get('task_id', '')) % 5
        await asyncio.sleep(processing_time)
        success = hash(agent_id) % 10 > 1
        await self.load_balancer.complete_task(task_info['task_data'].get('task_id', str(uuid.uuid4())), success, processing_time)
        if success:
            self.distribution_stats['tasks_completed'] += 1
        else:
            self.distribution_stats['tasks_failed'] += 1

    def get_distribution_stats(self) -> dict[str, Any]:
        """Get distribution statistics"""
        return {**self.distribution_stats, 'load_balancer_stats': self.load_balancer.get_load_balancing_stats(), 'queue_sizes': {priority.value: queue.qsize() for priority, queue in self.priority_queues.items()}}

    def get_queue_sizes(self) -> dict[str, int]:
        """Get sizes of all priority queues"""
        return {priority.value: queue.qsize() for priority, queue in self.priority_queues.items()}

    async def clear_queue(self, priority: TaskPriority) -> int:
        """Clear all tasks from a priority queue"""
        queue = self.priority_queues[priority]
        cleared_count = 0
        while not queue.empty():
            try:
                queue.get_nowait()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break
        logger.info('Cleared %s tasks from %s queue', cleared_count, priority.value)
        return cleared_count

async def example_usage() -> None:
    """Example of how to use the load balancer"""
    registry = AgentRegistry()
    await registry.start()
    load_balancer = LoadBalancer(registry)
    load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    distributor = TaskDistributor(load_balancer)
    for i in range(10):
        await distributor.submit_task({'task_id': f'task-{i}', 'task_type': 'data_processing', 'data': f'sample_data_{i}'}, TaskPriority.NORMAL)
    await registry.stop()
if __name__ == '__main__':
    asyncio.run(example_usage())

