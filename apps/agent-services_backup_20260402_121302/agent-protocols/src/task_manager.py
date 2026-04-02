"""
Task Manager for AITBC Agents
Handles task creation, assignment, and tracking
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

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
        created_by: Optional[str] = None
    ):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.assigned_to = assigned_to
        self.priority = priority
        self.created_by = created_by or assigned_to
        self.status = TaskStatus.PENDING
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.completed_at = None
        self.result = None
        self.error = None

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
        created_by: Optional[str] = None
    ) -> Task:
        """Create a new task"""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            title=title,
            description=description,
            assigned_to=assigned_to,
            priority=priority,
            created_by=created_by
        )
        
        self.tasks[task_id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        return self.tasks.get(task_id)
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update task status"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        task.status = status
        task.updated_at = datetime.utcnow()
        
        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.utcnow()
            task.result = result
        elif status == TaskStatus.FAILED:
            task.error = error
        
        return True
    
    def get_tasks_by_agent(self, agent_id: str) -> List[Task]:
        """Get all tasks assigned to an agent"""
        return [
            task for task in self.tasks.values()
            if task.assigned_to == agent_id
        ]
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks with a specific status"""
        return [
            task for task in self.tasks.values()
            if task.status == status
        ]
    
    def get_overdue_tasks(self, hours: int = 24) -> List[Task]:
        """Get tasks that are overdue"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        return [
            task for task in self.tasks.values()
            if task.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS] and
            task.created_at < cutoff_time
        ]
