"""
Training Router - AI model training API endpoints

Provides:
- Training job creation
- Progress monitoring
- Model checkpointing
- Training logs

v0.5.0: State is now backed by Redis (with in-memory fallback).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.redis_state import RedisStateManager
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

# Only enable mock endpoints if debug mode or explicit flag is set
if not (settings.debug or settings.enable_mock_training):
    # Create empty router for production
    router = APIRouter(prefix="/training", tags=["training"])
else:
    router = APIRouter(prefix="/training", tags=["training"])

    # Redis-backed state (falls back to in-memory if Redis unavailable)
    _state = RedisStateManager.get_instance_sync()
    _NAMESPACE = "training"

    class CreateTrainingRequest(BaseModel):
        """Request to create training job"""

        model_type: str = Field(..., min_length=1, max_length=50, description="Type of model: llm, vision, audio, etc.")
        dataset_id: str = Field(..., min_length=1)
        hyperparameters: dict[str, Any] | None = None
        epochs: int = Field(default=10, ge=1, le=1000)
        gpu_count: int = Field(default=1, ge=0, le=8)
        memory_gb: int = Field(default=16, ge=4, le=128)

        @field_validator("model_type")
        @classmethod
        def validate_model_type(cls, v: str) -> str:
            valid_types = {"llm", "vision", "audio", "multimodal", "reinforcement"}
            if v.lower() not in valid_types:
                raise ValueError(f"model_type must be one of: {', '.join(valid_types)}")
            return v.lower()

    class UpdateProgressRequest(BaseModel):
        """Request to update training progress"""

        job_id: str
        epoch: int
        step: int
        loss: float
        accuracy: float
        validation_loss: float = 0.0

    class CompleteTrainingRequest(BaseModel):
        """Request to complete training"""

        job_id: str
        final_accuracy: float
        final_loss: float
        model_path: str

    @router.post("/jobs")
    async def create_training_job(request: Request, req: CreateTrainingRequest) -> dict[str, Any]:
        """Create a new training job"""
        job_counter = await _state.incr(_NAMESPACE, "counter")
        job_id = f"job_{job_counter}"

        job = {
            "job_id": job_id,
            "model_type": req.model_type,
            "dataset_id": req.dataset_id,
            "hyperparameters": req.hyperparameters or {},
            "epochs": req.epochs,
            "gpu_count": req.gpu_count,
            "memory_gb": req.memory_gb,
            "status": "pending",
            "current_epoch": 0,
            "current_step": 0,
            "loss": 0.0,
            "accuracy": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }

        await _state.hset(_NAMESPACE, job_id, job)
        return {"job_id": job_id, "status": "created"}


@router.get("/jobs/{job_id}")
async def get_training_job(job_id: str) -> dict[str, Any]:
    """Get training job status"""
    job = await _state.hget(_NAMESPACE, job_id)
    if job is None:
        return {"error": "Job not found", "job_id": job_id}
    return job


@router.get("/jobs")
async def list_training_jobs() -> dict[str, list[dict[str, Any]]]:
    """List all training jobs"""
    jobs = await _state.hgetall(_NAMESPACE)
    return {"jobs": list(jobs.values())}


@router.post("/jobs/{job_id}/progress")
async def update_progress(job_id: str, req: UpdateProgressRequest) -> dict[str, str]:
    """Update training progress"""
    job = await _state.hget(_NAMESPACE, job_id)
    if job is None:
        return {"error": "Job not found", "job_id": job_id}

    job["current_epoch"] = req.epoch
    job["current_step"] = req.step
    job["loss"] = req.loss
    job["accuracy"] = req.accuracy
    job["validation_loss"] = req.validation_loss
    job["status"] = "training"
    job["updated_at"] = datetime.now(UTC).isoformat()

    await _state.hset(_NAMESPACE, job_id, job)
    return {"job_id": job_id, "status": "progress_updated"}


@router.post("/jobs/{job_id}/complete")
async def complete_training(job_id: str, req: CompleteTrainingRequest) -> dict[str, str]:
    """Mark training job as complete"""
    job = await _state.hget(_NAMESPACE, job_id)
    if job is None:
        return {"error": "Job not found", "job_id": job_id}

    job["status"] = "completed"
    job["final_accuracy"] = req.final_accuracy
    job["final_loss"] = req.final_loss
    job["model_path"] = req.model_path
    job["completed_at"] = datetime.now(UTC).isoformat()

    await _state.hset(_NAMESPACE, job_id, job)
    return {"job_id": job_id, "status": "completed"}


@router.delete("/jobs/{job_id}")
async def delete_training_job(job_id: str) -> dict[str, str]:
    """Delete a training job"""
    job = await _state.hget(_NAMESPACE, job_id)
    if job is None:
        return {"error": "Job not found", "job_id": job_id}

    await _state.hdel(_NAMESPACE, job_id)
    return {"job_id": job_id, "status": "deleted"}
