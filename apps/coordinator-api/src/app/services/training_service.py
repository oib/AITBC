"""
Training Service - AI model training management

Provides:
- Training job management
- Progress tracking
- Model checkpointing
- Distributed training coordination
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

class TrainingStatus(Enum):
    """Training job status"""
    pending = 'pending'
    queued = 'queued'
    running = 'running'
    paused = 'paused'
    completed = 'completed'
    failed = 'failed'
    cancelled = 'cancelled'

@dataclass
class TrainingJob:
    """AI training job"""
    job_id: str
    model_type: str
    dataset_id: str
    hyperparameters: dict[str, Any]
    status: TrainingStatus
    gpu_count: int
    memory_gb: int
    current_epoch: int = 0
    total_epochs: int = 10
    current_step: int = 0
    total_steps: int = 1000
    loss: float = 0.0
    accuracy: float = 0.0
    validation_loss: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_checkpoint: str | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'job_id': self.job_id, 'model_type': self.model_type, 'dataset_id': self.dataset_id, 'hyperparameters': self.hyperparameters, 'status': self.status.value, 'resources': {'gpu_count': self.gpu_count, 'memory_gb': self.memory_gb}, 'progress': {'current_epoch': self.current_epoch, 'total_epochs': self.total_epochs, 'current_step': self.current_step, 'total_steps': self.total_steps, 'percentage': self.current_epoch / self.total_epochs * 100 if self.total_epochs > 0 else 0}, 'metrics': {'loss': self.loss, 'accuracy': self.accuracy, 'validation_loss': self.validation_loss}, 'timestamps': {'created': self.created_at.isoformat(), 'started': self.started_at.isoformat() if self.started_at else None, 'completed': self.completed_at.isoformat() if self.completed_at else None}, 'model_checkpoint': self.model_checkpoint, 'log_count': len(self.logs)}

class TrainingService:
    """
    AI model training service.
    
    Manages:
    - Training job lifecycle
    - Resource allocation
    - Progress tracking
    - Model checkpointing
    """

    def __init__(self, session: Any=None) -> None:
        self._jobs: dict[str, TrainingJob] = {}
        self._job_counter = 0
        self._active_jobs: set = set()
        self._max_concurrent = 3
        self.session = session

    def create_training_job(self, model_type: str, dataset_id: str, hyperparameters: dict[str, Any] | None=None, epochs: int=10, gpu_count: int=1, memory_gb: int=16) -> TrainingJob:
        """
        Create a new training job.
        
        Args:
            model_type: Type of model to train (e.g., 'llm', 'vision')
            dataset_id: Dataset to train on
            hyperparameters: Training hyperparameters
            epochs: Number of training epochs
            gpu_count: GPUs required
            memory_gb: Memory required
        
        Returns:
            Created training job
        """
        self._job_counter += 1
        job_id = f'TRAIN-{self._job_counter:06d}'
        estimated_steps = 1000
        job = TrainingJob(job_id=job_id, model_type=model_type, dataset_id=dataset_id, hyperparameters=hyperparameters or {'learning_rate': 0.001, 'batch_size': 32, 'optimizer': 'adam'}, status=TrainingStatus.pending, gpu_count=gpu_count, memory_gb=memory_gb, total_epochs=epochs, total_steps=estimated_steps * epochs)
        self._jobs[job_id] = job
        logger.info('Training job created: %s (%s on %s)', job_id, model_type, dataset_id)
        if len(self._active_jobs) < self._max_concurrent:
            self.start_training(job_id)
        else:
            job.status = TrainingStatus.queued
            logger.info('Training job %s queued (max concurrent reached)', job_id)
        return job

    def start_training(self, job_id: str) -> TrainingJob:
        """Start a training job"""
        if job_id not in self._jobs:
            raise ValueError(f'Job {job_id} not found')
        job = self._jobs[job_id]
        if job.status not in [TrainingStatus.pending, TrainingStatus.queued]:
            raise ValueError(f'Cannot start job with status: {job.status.value}')
        job.status = TrainingStatus.running
        job.started_at = datetime.now(UTC)
        self._active_jobs.add(job_id)
        logger.info('Training started: %s', job_id)
        return job

    def update_progress(self, job_id: str, epoch: int, step: int, loss: float, accuracy: float, validation_loss: float=0.0) -> TrainingJob:
        """Update training progress"""
        if job_id not in self._jobs:
            raise ValueError(f'Job {job_id} not found')
        job = self._jobs[job_id]
        if job.status != TrainingStatus.running:
            raise ValueError(f'Job is not running: {job.status.value}')
        job.current_epoch = epoch
        job.current_step = step
        job.loss = loss
        job.accuracy = accuracy
        job.validation_loss = validation_loss
        log_entry = f'Epoch {epoch}/{job.total_epochs}, Step {step}, Loss: {loss:.4f}, Acc: {accuracy:.2%}'
        job.logs.append(log_entry)
        if epoch >= job.total_epochs:
            self.complete_training(job_id)
        return job

    def complete_training(self, job_id: str, checkpoint_url: str | None=None) -> TrainingJob:
        """Mark training as complete"""
        if job_id not in self._jobs:
            raise ValueError(f'Job {job_id} not found')
        job = self._jobs[job_id]
        job.status = TrainingStatus.completed
        job.completed_at = datetime.now(UTC)
        job.model_checkpoint = checkpoint_url or f'checkpoint://{job_id}/final'
        job.current_epoch = job.total_epochs
        if job_id in self._active_jobs:
            self._active_jobs.remove(job_id)
        self._process_queue()
        logger.info('Training completed: %s', job_id)
        return job

    def fail_training(self, job_id: str, error: str) -> TrainingJob:
        """Mark training as failed"""
        if job_id not in self._jobs:
            raise ValueError(f'Job {job_id} not found')
        job = self._jobs[job_id]
        job.status = TrainingStatus.failed
        job.logs.append(f'ERROR: {error}')
        if job_id in self._active_jobs:
            self._active_jobs.remove(job_id)
        self._process_queue()
        logger.info('Training failed: %s - %s', job_id, error)
        return job

    def cancel_training(self, job_id: str) -> TrainingJob:
        """Cancel a training job"""
        if job_id not in self._jobs:
            raise ValueError(f'Job {job_id} not found')
        job = self._jobs[job_id]
        if job.status == TrainingStatus.completed:
            raise ValueError('Cannot cancel completed job')
        job.status = TrainingStatus.cancelled
        if job_id in self._active_jobs:
            self._active_jobs.remove(job_id)
        self._process_queue()
        logger.info('Training cancelled: %s', job_id)
        return job

    def _process_queue(self) -> None:
        """Process queued jobs"""
        for job_id, job in self._jobs.items():
            if job.status == TrainingStatus.queued:
                if len(self._active_jobs) < self._max_concurrent:
                    self.start_training(job_id)
                break

    def get_job(self, job_id: str) -> TrainingJob | None:
        """Get training job by ID"""
        return self._jobs.get(job_id)

    def list_jobs(self, status: str | None=None, model_type: str | None=None) -> list[TrainingJob]:
        """List training jobs with filters"""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        if model_type:
            jobs = [j for j in jobs if j.model_type == model_type]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def get_job_logs(self, job_id: str, limit: int=100) -> list[str]:
        """Get training logs"""
        job = self._jobs.get(job_id)
        if not job:
            return []
        return job.logs[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get training statistics"""
        total = len(self._jobs)
        running = len([j for j in self._jobs.values() if j.status == TrainingStatus.running])
        completed = len([j for j in self._jobs.values() if j.status == TrainingStatus.completed])
        failed = len([j for j in self._jobs.values() if j.status == TrainingStatus.failed])
        queued = len([j for j in self._jobs.values() if j.status == TrainingStatus.queued])
        return {'total_jobs': total, 'running': running, 'completed': completed, 'failed': failed, 'queued': queued, 'max_concurrent': self._max_concurrent, 'active_slots': len(self._active_jobs)}
_training_service: TrainingService | None = None

def get_training_service() -> TrainingService:
    """Get global training service"""
    global _training_service
    if _training_service is None:
        _training_service = TrainingService()
    return _training_service
