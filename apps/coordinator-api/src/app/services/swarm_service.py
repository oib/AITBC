"""
Swarm Service - Compute clustering and orchestration

Provides:
- Cluster formation and management
- Task distribution across nodes
- Node health monitoring
- Load balancing
- Failover handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class NodeStatus(Enum):
    """Status of a swarm node"""

    online = "online"
    offline = "offline"
    busy = "busy"
    maintenance = "maintenance"
    degraded = "degraded"


class TaskStatus(Enum):
    """Status of a distributed task"""

    pending = "pending"
    assigned = "assigned"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


@dataclass
class SwarmNode:
    """A node in the compute swarm"""

    node_id: str
    address: str
    capabilities: list[str]
    status: NodeStatus
    last_heartbeat: datetime
    cpu_cores: int
    memory_gb: int
    gpu_count: int
    tasks_completed: int = 0
    tasks_failed: int = 0
    load_percentage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "resources": {"cpu_cores": self.cpu_cores, "memory_gb": self.memory_gb, "gpu_count": self.gpu_count},
            "metrics": {
                "tasks_completed": self.tasks_completed,
                "tasks_failed": self.tasks_failed,
                "load_percentage": self.load_percentage,
            },
            "last_heartbeat": self.last_heartbeat.isoformat(),
        }


@dataclass
class SwarmTask:
    """A distributed task in the swarm"""

    task_id: str
    task_type: str
    payload: dict[str, Any]
    status: TaskStatus
    assigned_node: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "assigned_node": self.assigned_node,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class SwarmCluster:
    """A cluster of compute nodes"""

    cluster_id: str
    name: str
    description: str
    created_at: datetime
    nodes: set[str] = field(default_factory=set)
    tasks: list[str] = field(default_factory=list)

    def to_dict(self, node_service: Any) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "node_count": len(self.nodes),
            "task_count": len(self.tasks),
            "nodes": [node_service.get_node(n).to_dict() if node_service.get_node(n) else {"node_id": n} for n in self.nodes],
            "status": "active" if self.nodes else "empty",
        }


class SwarmService:
    """
    Swarm - Compute clustering and orchestration.

    Manages:
    - Node registration and health monitoring
    - Task distribution and load balancing
    - Cluster formation
    - Fault tolerance and retry logic
    """

    HEARTBEAT_TIMEOUT_SECONDS = 60
    MAX_RETRIES = 3

    def __init__(self, session: Any = None) -> None:
        self._nodes: dict[str, SwarmNode] = {}
        self._tasks: dict[str, SwarmTask] = {}
        self._clusters: dict[str, SwarmCluster] = {}
        self._task_counter = 0
        self._cluster_counter = 0
        self.session = session

    def register_node(
        self, node_id: str, address: str, capabilities: list[str], cpu_cores: int = 4, memory_gb: int = 16, gpu_count: int = 0
    ) -> SwarmNode:
        """
        Register a compute node with the swarm.

        Args:
            node_id: Unique node identifier
            address: Node network address
            capabilities: List of capabilities (e.g., ['gpu', 'ai'])
            cpu_cores: Number of CPU cores
            memory_gb: Memory in GB
            gpu_count: Number of GPUs

        Returns:
            Registered node
        """
        node = SwarmNode(
            node_id=node_id,
            address=address,
            capabilities=capabilities,
            status=NodeStatus.online,
            last_heartbeat=datetime.now(UTC),
            cpu_cores=cpu_cores,
            memory_gb=memory_gb,
            gpu_count=gpu_count,
        )
        self._nodes[node_id] = node
        logger.info("Node registered with swarm: %s (%s)", node_id, address)
        return node

    def heartbeat(self, node_id: str) -> bool:
        """
        Update node heartbeat.

        Args:
            node_id: Node sending heartbeat

        Returns:
            True if node is recognized
        """
        if node_id not in self._nodes:
            return False
        node = self._nodes[node_id]
        node.last_heartbeat = datetime.now(UTC)
        if node.status == NodeStatus.offline:
            node.status = NodeStatus.online
            logger.info("Node back online: %s", node_id)
        return True

    def submit_task(
        self, task_type: str, payload: dict[str, Any], required_capabilities: list[str] | None = None, priority: int = 1
    ) -> SwarmTask:
        """
        Submit a task to the swarm for distribution.

        Args:
            task_type: Type of task (e.g., 'ai_inference', 'training')
            payload: Task data/payload
            required_capabilities: Capabilities required by node
            priority: Task priority (1-10, higher = more important)

        Returns:
            Created task
        """
        self._task_counter += 1
        task_id = f"TASK-{self._task_counter:08d}"
        task = SwarmTask(
            task_id=task_id, task_type=task_type, payload=payload, status=TaskStatus.pending, max_retries=self.MAX_RETRIES
        )
        assigned = self._assign_task(task, required_capabilities)
        self._tasks[task_id] = task
        if assigned:
            logger.info("Task %s assigned to %s", task_id, task.assigned_node)
        else:
            logger.info("Task %s queued (no available nodes)", task_id)
        return task

    def _assign_task(self, task: SwarmTask, required_capabilities: list[str] | None = None) -> bool:
        """
        Assign a task to an available node.

        Uses load balancing - picks least loaded capable node.
        """
        candidates = []
        for node in self._nodes.values():
            if node.status not in [NodeStatus.online, NodeStatus.busy]:
                continue
            last_seen = (datetime.now(UTC) - node.last_heartbeat).total_seconds()
            if last_seen > self.HEARTBEAT_TIMEOUT_SECONDS:
                node.status = NodeStatus.offline
                continue
            if required_capabilities:
                if not all(cap in node.capabilities for cap in required_capabilities):
                    continue
            candidates.append(node)
        if not candidates:
            return False
        candidates.sort(key=lambda n: n.load_percentage)
        selected = candidates[0]
        task.assigned_node = selected.node_id
        task.status = TaskStatus.assigned
        selected.load_percentage = min(100, selected.load_percentage + 10)
        return True

    def report_task_status(
        self, task_id: str, node_id: str, status: str, result: dict[str, Any] | None = None, error: str | None = None
    ) -> bool:
        """
        Report task status update from a node.

        Args:
            task_id: Task being reported on
            node_id: Node reporting status
            status: New status
            result: Task result (if completed)
            error: Error message (if failed)

        Returns:
            True if update accepted
        """
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        if task.assigned_node != node_id:
            return False
        try:
            new_status = TaskStatus(status)
        except ValueError:
            return False
        task.status = new_status
        if new_status == TaskStatus.running:
            task.started_at = datetime.now(UTC)
        elif new_status == TaskStatus.completed:
            task.completed_at = datetime.now(UTC)
            task.result = result
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.tasks_completed += 1
                node.load_percentage = max(0, node.load_percentage - 10)
        elif new_status == TaskStatus.failed:
            task.error = error
            task.retry_count += 1
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.tasks_failed += 1
                node.load_percentage = max(0, node.load_percentage - 10)
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.pending
                task.assigned_node = None
                logger.info("Task %s queued for retry (%s/%s)", task_id, task.retry_count, task.max_retries)
        logger.info("Task %s status: %s (from %s)", task_id, status, node_id)
        return True

    def create_cluster(self, name: str, description: str = "", node_ids: list[str] | None = None) -> SwarmCluster:
        """Create a new compute cluster"""
        self._cluster_counter += 1
        cluster_id = f"CLUSTER-{self._cluster_counter:04d}"
        cluster = SwarmCluster(
            cluster_id=cluster_id,
            name=name,
            description=description,
            created_at=datetime.now(UTC),
            nodes=set(node_ids) if node_ids else set(),
        )
        self._clusters[cluster_id] = cluster
        logger.info("Cluster created: %s with %s nodes", cluster_id, len(cluster.nodes))
        return cluster

    def add_node_to_cluster(self, cluster_id: str, node_id: str) -> bool:
        """Add a node to a cluster"""
        if cluster_id not in self._clusters:
            return False
        if node_id not in self._nodes:
            return False
        self._clusters[cluster_id].nodes.add(node_id)
        return True

    def get_node(self, node_id: str) -> SwarmNode | None:
        """Get node by ID"""
        return self._nodes.get(node_id)

    def get_task(self, task_id: str) -> SwarmTask | None:
        """Get task by ID"""
        return self._tasks.get(task_id)

    def get_cluster(self, cluster_id: str) -> SwarmCluster | None:
        """Get cluster by ID"""
        return self._clusters.get(cluster_id)

    def list_nodes(self, status: str | None = None, capability: str | None = None) -> list[SwarmNode]:
        """List nodes with optional filters"""
        nodes = list(self._nodes.values())
        if status:
            nodes = [n for n in nodes if n.status.value == status]
        if capability:
            nodes = [n for n in nodes if capability in n.capabilities]
        return nodes

    def list_tasks(self, status: str | None = None, node_id: str | None = None) -> list[SwarmTask]:
        """List tasks with optional filters"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        if node_id:
            tasks = [t for t in tasks if t.assigned_node == node_id]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def list_clusters(self) -> list[SwarmCluster]:
        """List all clusters"""
        return list(self._clusters.values())

    def get_stats(self) -> dict[str, Any]:
        """Get swarm statistics"""
        now = datetime.now(UTC)
        for node in self._nodes.values():
            last_seen = (now - node.last_heartbeat).total_seconds()
            if last_seen > self.HEARTBEAT_TIMEOUT_SECONDS:
                if node.status == NodeStatus.online:
                    node.status = NodeStatus.offline
                    logger.warning("Node marked offline: %s", node.node_id)
        online_nodes = len([n for n in self._nodes.values() if n.status == NodeStatus.online])
        total_tasks = len(self._tasks)
        completed_tasks = len([t for t in self._tasks.values() if t.status == TaskStatus.completed])
        failed_tasks = len([t for t in self._tasks.values() if t.status == TaskStatus.failed])
        pending_tasks = len([t for t in self._tasks.values() if t.status == TaskStatus.pending])
        return {
            "nodes": {"total": len(self._nodes), "online": online_nodes, "offline": len(self._nodes) - online_nodes},
            "tasks": {"total": total_tasks, "completed": completed_tasks, "failed": failed_tasks, "pending": pending_tasks},
            "clusters": len(self._clusters),
            "avg_load": sum(n.load_percentage for n in self._nodes.values()) / len(self._nodes) if self._nodes else 0,
        }


_swarm_service: SwarmService | None = None


def get_swarm_service() -> SwarmService:
    """Get global swarm service"""
    global _swarm_service
    if _swarm_service is None:
        _swarm_service = SwarmService()
    return _swarm_service
