"""
Task Manager for AITBC Agents
Handles task creation, assignment, and tracking
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Task status enumeration"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority enumeration"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task:
    """Task representation"""

    def __init__(
        self,
        task_id: str,
        title: str,
        description: str,
        assigned_to: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        created_by: str | None = None,
    ):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.assigned_to = assigned_to
        self.priority = priority
        self.created_by = created_by or assigned_to
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.completed_at: datetime | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None


class TaskManager:
    """Task manager for agent coordination"""

    def __init__(self):
        self.tasks = {}
        self.task_history = []

    def create_task(
        self,
        title: str,
        description: str,
        assigned_to: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        created_by: str | None = None,
    ) -> Task:
        """Create a new task"""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            title=title,
            description=description,
            assigned_to=assigned_to,
            priority=priority,
            created_by=created_by,
        )

        self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID"""
        return self.tasks.get(task_id)

    def update_task_status(
        self, task_id: str, status: TaskStatus, result: dict[str, Any] | None = None, error: str | None = None
    ) -> bool:
        """Update task status"""
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = status
        task.updated_at = datetime.now(UTC)

        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now(UTC)
            task.result = result
        elif status == TaskStatus.FAILED:
            task.error = error

        return True

    def get_tasks_by_agent(self, agent_id: str) -> list[Task]:
        """Get all tasks assigned to an agent"""
        return [task for task in self.tasks.values() if task.assigned_to == agent_id]

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Get all tasks with a specific status"""
        return [task for task in self.tasks.values() if task.status == status]

    def get_overdue_tasks(self, hours: int = 24) -> list[Task]:
        """Get tasks that are overdue"""
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
        return [
            task
            for task in self.tasks.values()
            if task.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS] and task.created_at < cutoff_time
        ]
