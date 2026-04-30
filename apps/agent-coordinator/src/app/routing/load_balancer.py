"""
Load Balancer for Agent Distribution and Task Assignment
"""

import asyncio
import json
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from enum import Enum
import statistics
import uuid
from collections import defaultdict, deque

from aitbc import get_logger
from .agent_discovery import AgentRegistry, AgentInfo, AgentStatus, AgentType
from ..protocols.message_types import TaskMessage, create_task_message
from ..protocols.communication import AgentMessage, MessageType, Priority

logger = get_logger(__name__)

class LoadBalancingStrategy(str, Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LEAST_RESPONSE_TIME = "least_response_time"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    RESOURCE_BASED = "resource_based"
    CAPABILITY_BASED = "capability_based"
    PREDICTIVE = "predictive"
    CONSISTENT_HASH = "consistent_hash"

class TaskPriority(str, Enum):
    """Task priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"

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
    last_updated: datetime = field(default_factory=datetime.now(datetime.UTC))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "active_connections": self.active_connections,
            "pending_tasks": self.pending_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "avg_response_time": self.avg_response_time,
            "last_updated": self.last_updated.isoformat()
        }

@dataclass
class TaskAssignment:
    """Task assignment record"""
    task_id: str
    agent_id: str
    assigned_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "pending"
    response_time: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "assigned_at": self.assigned_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "response_time": self.response_time,
            "success": self.success,
            "error_message": self.error_message
        }

@dataclass
class AgentWeight:
    """Agent weight for load balancing"""
    agent_id: str
    weight: float = 1.0
    capacity: int = 100
    performance_score: float = 1.0
    reliability_score: float = 1.0
    last_updated: datetime = field(default_factory=datetime.now(datetime.UTC))

class LoadBalancer:
    """Advanced load balancer for agent distribution"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.strategy = LoadBalancingStrategy.LEAST_CONNECTIONS
        self.agent_weights: Dict[str, AgentWeight] = {}
        self.agent_metrics: Dict[str, LoadMetrics] = {}
        self.task_assignments: Dict[str, TaskAssignment] = {}
        self.assignment_history: deque = deque(maxlen=1000)
        self.round_robin_index = 0
        self.consistent_hash_ring: Dict[int, str] = {}
        self.prediction_models: Dict[str, Any] = {}
        
        # Statistics
        self.total_assignments = 0
        self.successful_assignments = 0
        self.failed_assignments = 0
        
    def set_strategy(self, strategy: LoadBalancingStrategy):
        """Set load balancing strategy"""
        self.strategy = strategy
        logger.info(f"Load balancing strategy changed to: {strategy.value}")
    
    def set_agent_weight(self, agent_id: str, weight: float, capacity: int = 100):
        """Set agent weight and capacity"""
        self.agent_weights[agent_id] = AgentWeight(
            agent_id=agent_id,
            weight=weight,
            capacity=capacity
        )
        logger.info(f"Set weight for agent {agent_id}: {weight}, capacity: {capacity}")
    
    def update_agent_metrics(self, agent_id: str, metrics: LoadMetrics):
        """Update agent load metrics"""
        self.agent_metrics[agent_id] = metrics
        self.agent_metrics[agent_id].last_updated = datetime.now(datetime.UTC)
        
        # Update performance score based on metrics
        self._update_performance_score(agent_id, metrics)
    
    def _update_performance_score(self, agent_id: str, metrics: LoadMetrics):
        """Update agent performance score based on metrics"""
        if agent_id not in self.agent_weights:
            self.agent_weights[agent_id] = AgentWeight(agent_id=agent_id)
        
        weight = self.agent_weights[agent_id]
        
        # Calculate performance score (0.0 to 1.0)
        performance_factors = []
        
        # CPU usage factor (lower is better)
        cpu_factor = max(0.0, 1.0 - metrics.cpu_usage)
        performance_factors.append(cpu_factor)
        
        # Memory usage factor (lower is better)
        memory_factor = max(0.0, 1.0 - metrics.memory_usage)
        performance_factors.append(memory_factor)
        
        # Response time factor (lower is better)
        if metrics.avg_response_time > 0:
            response_factor = max(0.0, 1.0 - (metrics.avg_response_time / 10.0))  # 10s max
            performance_factors.append(response_factor)
        
        # Success rate factor (higher is better)
        total_tasks = metrics.completed_tasks + metrics.failed_tasks
        if total_tasks > 0:
            success_rate = metrics.completed_tasks / total_tasks
            performance_factors.append(success_rate)
        
        # Update performance score
        if performance_factors:
            weight.performance_score = statistics.mean(performance_factors)
        
        # Update reliability score
        if total_tasks > 10:  # Only update after enough tasks
            weight.reliability_score = success_rate
    
    async def assign_task(self, task_data: Dict[str, Any], requirements: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Assign task to best available agent"""
        try:
            # Find eligible agents
            eligible_agents = await self._find_eligible_agents(task_data, requirements)
            
            if not eligible_agents:
                logger.warning("No eligible agents found for task assignment")
                return None
            
            # Select best agent based on strategy
            selected_agent = await self._select_agent(eligible_agents, task_data)
            
            if not selected_agent:
                logger.warning("No agent selected for task assignment")
                return None
            
            # Create task assignment
            task_id = str(uuid.uuid4())
            assignment = TaskAssignment(
                task_id=task_id,
                agent_id=selected_agent,
                assigned_at=datetime.now(datetime.UTC)
            )
            
            # Record assignment
            self.task_assignments[task_id] = assignment
            self.assignment_history.append(assignment)
            self.total_assignments += 1
            
            # Update agent metrics
            if selected_agent not in self.agent_metrics:
                self.agent_metrics[selected_agent] = LoadMetrics()
            
            self.agent_metrics[selected_agent].pending_tasks += 1
            
            logger.info(f"Task {task_id} assigned to agent {selected_agent}")
            return selected_agent
            
        except Exception as e:
            logger.error(f"Error assigning task: {e}")
            self.failed_assignments += 1
            return None
    
    async def complete_task(self, task_id: str, success: bool, response_time: Optional[float] = None, error_message: Optional[str] = None):
        """Mark task as completed"""
        try:
            if task_id not in self.task_assignments:
                logger.warning(f"Task assignment {task_id} not found")
                return
            
            assignment = self.task_assignments[task_id]
            assignment.completed_at = datetime.now(datetime.UTC)
            assignment.status = "completed"
            assignment.success = success
            assignment.response_time = response_time
            assignment.error_message = error_message
            
            # Update agent metrics
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
                
                # Update average response time
                if response_time:
                    total_completed = metrics.completed_tasks + metrics.failed_tasks
                    if total_completed > 0:
                        metrics.avg_response_time = (
                            (metrics.avg_response_time * (total_completed - 1) + response_time) / total_completed
                        )
            
            logger.info(f"Task {task_id} completed by agent {assignment.agent_id}, success: {success}")
            
        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}")
    
    async def _find_eligible_agents(self, task_data: Dict[str, Any], requirements: Optional[Dict[str, Any]] = None) -> List[str]:
        """Find eligible agents for task"""
        try:
            # Build discovery query
            query = {"status": AgentStatus.ACTIVE}
            
            if requirements:
                if "agent_type" in requirements:
                    query["agent_type"] = requirements["agent_type"]
                
                if "capabilities" in requirements:
                    query["capabilities"] = requirements["capabilities"]
                
                if "services" in requirements:
                    query["services"] = requirements["services"]
                
                if "min_health_score" in requirements:
                    query["min_health_score"] = requirements["min_health_score"]
            
            # Discover agents
            agents = await self.registry.discover_agents(query)
            
            # Filter by capacity and load
            eligible_agents = []
            for agent in agents:
                agent_id = agent.agent_id
                
                # Check capacity
                if agent_id in self.agent_weights:
                    weight = self.agent_weights[agent_id]
                    current_load = self._get_agent_load(agent_id)
                    
                    if current_load < weight.capacity:
                        eligible_agents.append(agent_id)
                else:
                    # Default capacity check
                    metrics = self.agent_metrics.get(agent_id, LoadMetrics())
                    if metrics.pending_tasks < 100:  # Default capacity
                        eligible_agents.append(agent_id)
            
            return eligible_agents
            
        except Exception as e:
            logger.error(f"Error finding eligible agents: {e}")
            return []
    
    def _get_agent_load(self, agent_id: str) -> int:
        """Get current load for agent"""
        metrics = self.agent_metrics.get(agent_id, LoadMetrics())
        return metrics.active_connections + metrics.pending_tasks
    
    async def _select_agent(self, eligible_agents: List[str], task_data: Dict[str, Any]) -> Optional[str]:
        """Select best agent based on current strategy"""
        if not eligible_agents:
            return None
        
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin_selection(eligible_agents)
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_selection(eligible_agents)
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
    
    def _round_robin_selection(self, agents: List[str]) -> str:
        """Round-robin agent selection"""
        agent = agents[self.round_robin_index % len(agents)]
        self.round_robin_index += 1
        return agent
    
    def _least_connections_selection(self, agents: List[str]) -> str:
        """Select agent with least connections"""
        min_connections = float('inf')
        selected_agent = None
        
        for agent_id in agents:
            metrics = self.agent_metrics.get(agent_id, LoadMetrics())
            connections = metrics.active_connections
            
            if connections < min_connections:
                min_connections = connections
                selected_agent = agent_id
        
        return selected_agent or agents[0]
    
    def _least_response_time_selection(self, agents: List[str]) -> str:
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
    
    def _weighted_round_robin_selection(self, agents: List[str]) -> str:
        """Weighted round-robin selection"""
        # Calculate total weight
        total_weight = 0
        for agent_id in agents:
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            total_weight += weight.weight
        
        if total_weight == 0:
            return agents[0]
        
        # Select agent based on weight
        current_weight = self.round_robin_index % total_weight
        accumulated_weight = 0
        
        for agent_id in agents:
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            accumulated_weight += weight.weight
            
            if current_weight < accumulated_weight:
                self.round_robin_index += 1
                return agent_id
        
        return agents[0]
    
    def _resource_based_selection(self, agents: List[str]) -> str:
        """Resource-based selection considering CPU and memory"""
        best_score = -1
        selected_agent = None
        
        for agent_id in agents:
            metrics = self.agent_metrics.get(agent_id, LoadMetrics())
            
            # Calculate resource score (lower usage is better)
            cpu_score = max(0, 100 - metrics.cpu_usage)
            memory_score = max(0, 100 - metrics.memory_usage)
            resource_score = (cpu_score + memory_score) / 2
            
            # Apply performance weight
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            final_score = resource_score * weight.performance_score
            
            if final_score > best_score:
                best_score = final_score
                selected_agent = agent_id
        
        return selected_agent or agents[0]
    
    def _capability_based_selection(self, agents: List[str], task_data: Dict[str, Any]) -> str:
        """Capability-based selection considering task requirements"""
        required_capabilities = task_data.get("required_capabilities", [])
        
        if not required_capabilities:
            return agents[0]
        
        best_score = -1
        selected_agent = None
        
        for agent_id in agents:
            agent_info = self.registry.agents.get(agent_id)
            if not agent_info:
                continue
            
            # Calculate capability match score
            agent_capabilities = set(agent_info.capabilities)
            required_set = set(required_capabilities)
            
            if required_set.issubset(agent_capabilities):
                # Perfect match
                capability_score = 1.0
            else:
                # Partial match
                intersection = required_set.intersection(agent_capabilities)
                capability_score = len(intersection) / len(required_set)
            
            # Apply performance weight
            weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
            final_score = capability_score * weight.performance_score
            
            if final_score > best_score:
                best_score = final_score
                selected_agent = agent_id
        
        return selected_agent or agents[0]
    
    def _predictive_selection(self, agents: List[str], task_data: Dict[str, Any]) -> str:
        """Predictive selection using historical performance"""
        task_type = task_data.get("task_type", "unknown")
        
        # Calculate predicted performance for each agent
        best_score = -1
        selected_agent = None
        
        for agent_id in agents:
            # Get historical performance for this task type
            score = self._calculate_predicted_score(agent_id, task_type)
            
            if score > best_score:
                best_score = score
                selected_agent = agent_id
        
        return selected_agent or agents[0]
    
    def _calculate_predicted_score(self, agent_id: str, task_type: str) -> float:
        """Calculate predicted performance score for agent"""
        # Simple prediction based on recent performance
        weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
        
        # Base score from performance and reliability
        base_score = (weight.performance_score + weight.reliability_score) / 2
        
        # Adjust based on recent assignments
        recent_assignments = [a for a in self.assignment_history if a.agent_id == agent_id][-10:]
        if recent_assignments:
            success_rate = sum(1 for a in recent_assignments if a.success) / len(recent_assignments)
            base_score = base_score * 0.7 + success_rate * 0.3
        
        return base_score
    
    def _consistent_hash_selection(self, agents: List[str], task_data: Dict[str, Any]) -> str:
        """Consistent hash selection for sticky routing"""
        # Create hash key from task data
        hash_key = json.dumps(task_data, sort_keys=True)
        hash_value = int(hashlib.sha256(hash_key.encode()).hexdigest(), 16)
        
        # Build hash ring if not exists
        if not self.consistent_hash_ring:
            self._build_hash_ring(agents)
        
        # Find agent on hash ring
        for hash_pos in sorted(self.consistent_hash_ring.keys()):
            if hash_value <= hash_pos:
                return self.consistent_hash_ring[hash_pos]
        
        # Wrap around
        return self.consistent_hash_ring[min(self.consistent_hash_ring.keys())]
    
    def _build_hash_ring(self, agents: List[str]):
        """Build consistent hash ring"""
        self.consistent_hash_ring = {}
        
        for agent_id in agents:
            # Create multiple virtual nodes for better distribution
            for i in range(100):
                virtual_key = f"{agent_id}:{i}"
                hash_value = int(hashlib.sha256(virtual_key.encode()).hexdigest(), 16)
                self.consistent_hash_ring[hash_value] = agent_id
    
    def get_load_balancing_stats(self) -> Dict[str, Any]:
        """Get load balancing statistics"""
        return {
            "strategy": self.strategy.value,
            "total_assignments": self.total_assignments,
            "successful_assignments": self.successful_assignments,
            "failed_assignments": self.failed_assignments,
            "success_rate": self.successful_assignments / max(1, self.total_assignments),
            "active_agents": len(self.agent_metrics),
            "agent_weights": len(self.agent_weights),
            "avg_agent_load": statistics.mean([self._get_agent_load(a) for a in self.agent_metrics]) if self.agent_metrics else 0
        }
    
    def get_agent_stats(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed statistics for a specific agent"""
        if agent_id not in self.agent_metrics:
            return None
        
        metrics = self.agent_metrics[agent_id]
        weight = self.agent_weights.get(agent_id, AgentWeight(agent_id=agent_id))
        
        # Get recent assignments
        recent_assignments = [a for a in self.assignment_history if a.agent_id == agent_id][-10:]
        
        return {
            "agent_id": agent_id,
            "metrics": metrics.to_dict(),
            "weight": {
                "weight": weight.weight,
                "capacity": weight.capacity,
                "performance_score": weight.performance_score,
                "reliability_score": weight.reliability_score
            },
            "recent_assignments": [a.to_dict() for a in recent_assignments],
            "current_load": self._get_agent_load(agent_id)
        }

class TaskDistributor:
    """Task distributor with advanced load balancing"""
    
    def __init__(self, load_balancer: LoadBalancer):
        self.load_balancer = load_balancer
        self.task_queue = asyncio.Queue()
        self.priority_queues = {
            TaskPriority.URGENT: asyncio.Queue(),
            TaskPriority.CRITICAL: asyncio.Queue(),
            TaskPriority.HIGH: asyncio.Queue(),
            TaskPriority.NORMAL: asyncio.Queue(),
            TaskPriority.LOW: asyncio.Queue()
        }
        self.distribution_stats = {
            "tasks_distributed": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_distribution_time": 0.0
        }
        
    async def submit_task(self, task_data: Dict[str, Any], priority: TaskPriority = TaskPriority.NORMAL, requirements: Optional[Dict[str, Any]] = None):
        """Submit task for distribution"""
        task_info = {
            "task_data": task_data,
            "priority": priority,
            "requirements": requirements,
            "submitted_at": datetime.now(datetime.UTC)
        }
        
        await self.priority_queues[priority].put(task_info)
        logger.info(f"Task submitted with priority {priority.value}")
    
    async def start_distribution(self):
        """Start task distribution loop"""
        while True:
            try:
                # Check queues in priority order
                task_info = None
                
                for priority in [TaskPriority.URGENT, TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
                    queue = self.priority_queues[priority]
                    try:
                        task_info = queue.get_nowait()
                        break
                    except asyncio.QueueEmpty:
                        continue
                
                if task_info:
                    await self._distribute_task(task_info)
                else:
                    await asyncio.sleep(0.01)  # Small delay if no tasks
                    
            except Exception as e:
                logger.error(f"Error in distribution loop: {e}")
                await asyncio.sleep(1)
    
    async def _distribute_task(self, task_info: Dict[str, Any]):
        """Distribute a single task"""
        start_time = datetime.now(datetime.UTC)
        
        try:
            # Assign task
            agent_id = await self.load_balancer.assign_task(
                task_info["task_data"],
                task_info["requirements"]
            )
            
            if agent_id:
                # Create task message
                task_message = create_task_message(
                    sender_id="task_distributor",
                    receiver_id=agent_id,
                    task_type=task_info["task_data"].get("task_type", "unknown"),
                    task_data=task_info["task_data"]
                )
                
                # Send task to agent (implementation depends on communication system)
                # await self._send_task_to_agent(agent_id, task_message)
                
                self.distribution_stats["tasks_distributed"] += 1
                
                # Simulate task completion (in real implementation, this would be event-driven)
                asyncio.create_task(self._simulate_task_completion(task_info, agent_id))
                
            else:
                logger.warning(f"Failed to distribute task: no suitable agent found")
                self.distribution_stats["tasks_failed"] += 1
                
        except Exception as e:
            logger.error(f"Error distributing task: {e}")
            self.distribution_stats["tasks_failed"] += 1
        
        finally:
            # Update distribution time
            distribution_time = (datetime.now(datetime.UTC) - start_time).total_seconds()
            total_distributed = self.distribution_stats["tasks_distributed"]
            self.distribution_stats["avg_distribution_time"] = (
                (self.distribution_stats["avg_distribution_time"] * (total_distributed - 1) + distribution_time) / total_distributed
                if total_distributed > 0 else distribution_time
            )
    
    async def _simulate_task_completion(self, task_info: Dict[str, Any], agent_id: str):
        """Simulate task completion (for testing)"""
        # Simulate task processing time
        processing_time = 1.0 + (hash(task_info["task_data"].get("task_id", "")) % 5)
        await asyncio.sleep(processing_time)
        
        # Mark task as completed
        success = hash(agent_id) % 10 > 1  # 90% success rate
        await self.load_balancer.complete_task(
            task_info["task_data"].get("task_id", str(uuid.uuid4())),
            success,
            processing_time
        )
        
        if success:
            self.distribution_stats["tasks_completed"] += 1
        else:
            self.distribution_stats["tasks_failed"] += 1
    
    def get_distribution_stats(self) -> Dict[str, Any]:
        """Get distribution statistics"""
        return {
            **self.distribution_stats,
            "load_balancer_stats": self.load_balancer.get_load_balancing_stats(),
            "queue_sizes": {
                priority.value: queue.qsize()
                for priority, queue in self.priority_queues.items()
            }
        }

# Example usage
async def example_usage():
    """Example of how to use the load balancer"""
    
    # Create registry and load balancer
    registry = AgentRegistry()
    await registry.start()
    
    load_balancer = LoadBalancer(registry)
    load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    
    # Create task distributor
    distributor = TaskDistributor(load_balancer)
    
    # Submit some tasks
    for i in range(10):
        await distributor.submit_task({
            "task_id": f"task-{i}",
            "task_type": "data_processing",
            "data": f"sample_data_{i}"
        }, TaskPriority.NORMAL)
    
    # Start distribution (in real implementation, this would run in background)
    # await distributor.start_distribution()
    
    await registry.stop()

if __name__ == "__main__":
    asyncio.run(example_usage())
