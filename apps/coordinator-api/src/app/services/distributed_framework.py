"""
Distributed Agent Processing Framework
Implements a scalable, fault-tolerant framework for distributed AI agent tasks across the AITBC network.
"""

import asyncio
import uuid
import time
import json
import hashlib
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime
from enum import Enum

from aitbc import get_logger

logger = get_logger(__name__)

class TaskStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"

class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    OVERLOADED = "overloaded"

class DistributedTask:
    def __init__(
        self, 
        task_id: str, 
        agent_id: str, 
        payload: Dict[str, Any],
        priority: int = 1,
        requires_gpu: bool = False,
        timeout_ms: int = 30000,
        max_retries: int = 3
    ):
        self.task_id = task_id or f"dt_{uuid.uuid4().hex[:12]}"
        self.agent_id = agent_id
        self.payload = payload
        self.priority = priority
        self.requires_gpu = requires_gpu
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        
        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.scheduled_at = None
        self.started_at = None
        self.completed_at = None
        
        self.assigned_worker_id = None
        self.result = None
        self.error = None
        self.retries = 0
        
        # Calculate content hash for caching/deduplication
        content = json.dumps(payload, sort_keys=True)
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()

class WorkerNode:
    def __init__(
        self, 
        worker_id: str, 
        capabilities: List[str], 
        has_gpu: bool = False,
        max_concurrent_tasks: int = 4
    ):
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.has_gpu = has_gpu
        self.max_concurrent_tasks = max_concurrent_tasks
        
        self.status = WorkerStatus.IDLE
        self.active_tasks = []
        self.last_heartbeat = time.time()
        self.total_completed = 0
        self.performance_score = 1.0  # 0.0 to 1.0 based on success rate and speed

class DistributedProcessingCoordinator:
    """
    Coordinates distributed task execution across available worker nodes.
    Implements advanced scheduling, fault tolerance, and load balancing.
    """
    
    def __init__(self):
        self.tasks: Dict[str, DistributedTask] = {}
        self.workers: Dict[str, WorkerNode] = {}
        self.task_queue = asyncio.PriorityQueue()
        
        # Result cache (content_hash -> result)
        self.result_cache: Dict[str, Any] = {}
        
        self.is_running = False
        self._scheduler_task = None
        self._monitor_task = None
        
    async def start(self):
        """Start the coordinator background tasks"""
        if self.is_running:
            return
            
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduling_loop())
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Distributed Processing Coordinator started")
        
    async def stop(self):
        """Stop the coordinator gracefully"""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        logger.info("Distributed Processing Coordinator stopped")
        
    def register_worker(self, worker_id: str, capabilities: List[str], has_gpu: bool = False, max_tasks: int = 4):
        """Register a new worker node in the cluster"""
        if worker_id not in self.workers:
            self.workers[worker_id] = WorkerNode(worker_id, capabilities, has_gpu, max_tasks)
            logger.info(f"Registered new worker node: {worker_id} (GPU: {has_gpu})")
        else:
            # Update existing worker
            worker = self.workers[worker_id]
            worker.capabilities = capabilities
            worker.has_gpu = has_gpu
            worker.max_concurrent_tasks = max_tasks
            worker.last_heartbeat = time.time()
            if worker.status == WorkerStatus.OFFLINE:
                worker.status = WorkerStatus.IDLE
                
    def heartbeat(self, worker_id: str, metrics: Optional[Dict[str, Any]] = None):
        """Record a heartbeat from a worker node"""
        if worker_id in self.workers:
            worker = self.workers[worker_id]
            worker.last_heartbeat = time.time()
            
            # Update status based on metrics if provided
            if metrics:
                cpu_load = metrics.get('cpu_load', 0.0)
                if cpu_load > 0.9 or len(worker.active_tasks) >= worker.max_concurrent_tasks:
                    worker.status = WorkerStatus.OVERLOADED
                elif len(worker.active_tasks) > 0:
                    worker.status = WorkerStatus.BUSY
                else:
                    worker.status = WorkerStatus.IDLE

    async def submit_task(self, task: DistributedTask) -> str:
        """Submit a new task to the distributed framework"""
        # Check cache first
        if task.content_hash in self.result_cache:
            task.status = TaskStatus.COMPLETED
            task.result = self.result_cache[task.content_hash]
            task.completed_at = time.time()
            self.tasks[task.task_id] = task
            logger.debug(f"Task {task.task_id} fulfilled from cache")
            return task.task_id
            
        self.tasks[task.task_id] = task
        # Priority Queue uses lowest number first, so we invert user priority
        queue_priority = 100 - min(task.priority, 100)
        
        await self.task_queue.put((queue_priority, task.created_at, task.task_id))
        logger.debug(f"Task {task.task_id} queued with priority {task.priority}")
        
        return task.task_id
        
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status and result of a task"""
        if task_id not in self.tasks:
            return None
            
        task = self.tasks[task_id]
        
        response = {
            'task_id': task.task_id,
            'status': task.status,
            'created_at': task.created_at
        }
        
        if task.status == TaskStatus.COMPLETED:
            response['result'] = task.result
            response['completed_at'] = task.completed_at
            response['duration_ms'] = int((task.completed_at - (task.started_at or task.created_at)) * 1000)
        elif task.status in [TaskStatus.FAILED, TaskStatus.TIMEOUT]:
            response['error'] = str(task.error)
            
        if task.assigned_worker_id:
            response['worker_id'] = task.assigned_worker_id
            
        return response

    async def _scheduling_loop(self):
        """Background task that assigns queued tasks to available workers"""
        while self.is_running:
            try:
                # Get next task from queue (blocks until available)
                if self.task_queue.empty():
                    await asyncio.sleep(0.1)
                    continue
                    
                priority, _, task_id = await self.task_queue.get()
                
                if task_id not in self.tasks:
                    self.task_queue.task_done()
                    continue
                    
                task = self.tasks[task_id]
                
                # If task was cancelled while in queue
                if task.status != TaskStatus.PENDING and task.status != TaskStatus.RETRYING:
                    self.task_queue.task_done()
                    continue
                    
                # Find best worker
                best_worker = self._find_best_worker(task)
                
                if best_worker:
                    await self._assign_task(task, best_worker)
                else:
                    # No worker available right now, put back in queue with slight delay
                    # Use a background task to not block the scheduling loop
                    asyncio.create_task(self._requeue_delayed(priority, task))
                    
                self.task_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduling loop: {e}")
                await asyncio.sleep(1.0)
                
    async def _requeue_delayed(self, priority: int, task: DistributedTask):
        """Put a task back in the queue after a short delay"""
        await asyncio.sleep(0.5)
        if self.is_running and task.status in [TaskStatus.PENDING, TaskStatus.RETRYING]:
            await self.task_queue.put((priority, task.created_at, task.task_id))

    def _find_best_worker(self, task: DistributedTask) -> Optional[WorkerNode]:
        """Find the optimal worker for a task based on requirements and load"""
        candidates = []
        
        for worker in self.workers.values():
            # Skip offline or overloaded workers
            if worker.status in [WorkerStatus.OFFLINE, WorkerStatus.OVERLOADED]:
                continue
                
            # Skip if worker is at capacity
            if len(worker.active_tasks) >= worker.max_concurrent_tasks:
                continue
                
            # Check GPU requirement
            if task.requires_gpu and not worker.has_gpu:
                continue
                
            # Required capability check could be added here
            
            # Calculate score for worker
            score = worker.performance_score * 100
            
            # Penalize slightly based on current load to balance distribution
            load_factor = len(worker.active_tasks) / worker.max_concurrent_tasks
            score -= (load_factor * 20)
            
            # Prefer GPU workers for GPU tasks, penalize GPU workers for CPU tasks 
            # to keep them free for GPU workloads
            if worker.has_gpu and not task.requires_gpu:
                score -= 30
                
            candidates.append((score, worker))
            
        if not candidates:
            return None
            
        # Return worker with highest score
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def _assign_task(self, task: DistributedTask, worker: WorkerNode):
        """Assign a task to a specific worker"""
        task.status = TaskStatus.SCHEDULED
        task.assigned_worker_id = worker.worker_id
        task.scheduled_at = time.time()
        
        worker.active_tasks.append(task.task_id)
        if len(worker.active_tasks) >= worker.max_concurrent_tasks:
            worker.status = WorkerStatus.OVERLOADED
        elif worker.status == WorkerStatus.IDLE:
            worker.status = WorkerStatus.BUSY
            
        logger.debug(f"Assigned task {task.task_id} to worker {worker.worker_id}")
        
        # In a real system, this would make an RPC/network call to the worker
        # Here we simulate the network dispatch asynchronously
        asyncio.create_task(self._simulate_worker_execution(task, worker))

    async def _simulate_worker_execution(self, task: DistributedTask, worker: WorkerNode):
        """Simulate the execution on the remote worker node"""
        task.status = TaskStatus.PROCESSING
        task.started_at = time.time()
        
        try:
            # Simulate processing time based on task complexity
            # Real implementation would await the actual RPC response
            complexity = task.payload.get('complexity', 1.0)
            base_time = 0.5
            
            if worker.has_gpu and task.requires_gpu:
                # GPU processes faster
                processing_time = base_time * complexity * 0.2
            else:
                processing_time = base_time * complexity
                
            # Simulate potential network/node failure
            if worker.performance_score < 0.5 and time.time() % 10 < 1:
                raise ConnectionError("Worker node network failure")
                
            await asyncio.sleep(processing_time)
            
            # Success
            self.report_task_success(task.task_id, {"result_data": "simulated_success", "processed_by": worker.worker_id})
            
        except Exception as e:
            self.report_task_failure(task.task_id, str(e))

    def report_task_success(self, task_id: str, result: Any):
        """Called by a worker when a task completes successfully"""
        if task_id not in self.tasks:
            return
            
        task = self.tasks[task_id]
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
            return # Already finished
            
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = time.time()
        
        # Cache the result
        self.result_cache[task.content_hash] = result
        
        # Update worker metrics
        if task.assigned_worker_id and task.assigned_worker_id in self.workers:
            worker = self.workers[task.assigned_worker_id]
            if task_id in worker.active_tasks:
                worker.active_tasks.remove(task_id)
            worker.total_completed += 1
            # Increase performance score slightly (max 1.0)
            worker.performance_score = min(1.0, worker.performance_score + 0.01)
            
            if len(worker.active_tasks) < worker.max_concurrent_tasks and worker.status == WorkerStatus.OVERLOADED:
                worker.status = WorkerStatus.BUSY
            if len(worker.active_tasks) == 0:
                worker.status = WorkerStatus.IDLE
                
        logger.info(f"Task {task_id} completed successfully")

    def report_task_failure(self, task_id: str, error: str):
        """Called when a task fails execution"""
        if task_id not in self.tasks:
            return
            
        task = self.tasks[task_id]
        
        # Update worker metrics
        if task.assigned_worker_id and task.assigned_worker_id in self.workers:
            worker = self.workers[task.assigned_worker_id]
            if task_id in worker.active_tasks:
                worker.active_tasks.remove(task_id)
            # Decrease performance score heavily on failure
            worker.performance_score = max(0.1, worker.performance_score - 0.05)
            
        # Handle retry logic
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.RETRYING
            task.assigned_worker_id = None
            task.error = f"Attempt {task.retries} failed: {error}"
            
            logger.warning(f"Task {task_id} failed, scheduling retry {task.retries}/{task.max_retries}")
            
            # Put back in queue with slightly lower priority
            queue_priority = (100 - min(task.priority, 100)) + (task.retries * 5)
            asyncio.create_task(self.task_queue.put((queue_priority, time.time(), task.task_id)))
        else:
            task.status = TaskStatus.FAILED
            task.error = f"Max retries exceeded. Final error: {error}"
            task.completed_at = time.time()
            logger.error(f"Task {task_id} failed permanently")

    async def _health_monitor_loop(self):
        """Background task that monitors worker health and task timeouts"""
        while self.is_running:
            try:
                current_time = time.time()
                
                # 1. Check worker health
                for worker_id, worker in self.workers.items():
                    # If no heartbeat for 60 seconds, mark offline
                    if current_time - worker.last_heartbeat > 60.0:
                        if worker.status != WorkerStatus.OFFLINE:
                            logger.warning(f"Worker {worker_id} went offline (missed heartbeats)")
                            worker.status = WorkerStatus.OFFLINE
                            
                            # Re-queue all active tasks for this worker
                            for task_id in worker.active_tasks:
                                if task_id in self.tasks:
                                    self.report_task_failure(task_id, "Worker node disconnected")
                            worker.active_tasks.clear()
                            
                # 2. Check task timeouts
                for task_id, task in self.tasks.items():
                    if task.status in [TaskStatus.SCHEDULED, TaskStatus.PROCESSING]:
                        start_time = task.started_at or task.scheduled_at
                        if start_time and (current_time - start_time) * 1000 > task.timeout_ms:
                            logger.warning(f"Task {task_id} timed out")
                            self.report_task_failure(task_id, f"Execution timed out after {task.timeout_ms}ms")
                            
                await asyncio.sleep(5.0)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(5.0)

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get the overall status of the distributed cluster"""
        total_workers = len(self.workers)
        active_workers = sum(1 for w in self.workers.values() if w.status != WorkerStatus.OFFLINE)
        gpu_workers = sum(1 for w in self.workers.values() if w.has_gpu and w.status != WorkerStatus.OFFLINE)
        
        pending_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        processing_tasks = sum(1 for t in self.tasks.values() if t.status in [TaskStatus.SCHEDULED, TaskStatus.PROCESSING])
        completed_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in self.tasks.values() if t.status in [TaskStatus.FAILED, TaskStatus.TIMEOUT])
        
        # Calculate cluster utilization
        total_capacity = sum(w.max_concurrent_tasks for w in self.workers.values() if w.status != WorkerStatus.OFFLINE)
        current_load = sum(len(w.active_tasks) for w in self.workers.values() if w.status != WorkerStatus.OFFLINE)
        
        utilization = (current_load / total_capacity * 100) if total_capacity > 0 else 0
        
        return {
            "cluster_health": "healthy" if active_workers > 0 else "offline",
            "nodes": {
                "total": total_workers,
                "active": active_workers,
                "with_gpu": gpu_workers
            },
            "tasks": {
                "pending": pending_tasks,
                "processing": processing_tasks,
                "completed": completed_tasks,
                "failed": failed_tasks
            },
            "performance": {
                "utilization_percent": round(utilization, 2),
                "cache_size": len(self.result_cache)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
