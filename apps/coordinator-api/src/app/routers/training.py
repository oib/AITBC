"""
Training Router - AI model training API endpoints

Provides:
- Training job creation
- Progress monitoring
- Model checkpointing
- Training logs
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from app.config import settings

# Only enable mock endpoints if debug mode or explicit flag is set
if not (settings.debug or settings.enable_mock_training):
    # Create empty router for production
    router = APIRouter(prefix="/training", tags=["training"])
else:
    router = APIRouter(prefix="/training", tags=["training"])

    # In-memory state for mock data
    _mock_jobs: dict[str, dict[str, Any]] = {}
    _job_counter = 0


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
    global _job_counter
    _job_counter += 1
    job_id = f"job_{_job_counter}"

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
        "created_at": "2024-01-01T00:00:00Z",
    }

    _mock_jobs[job_id] = job
    return {"job_id": job_id, "status": "created"}


@router.get("/jobs/{job_id}")
async def get_training_job(job_id: str) -> dict[str, Any]:
    """Get training job status"""
    if job_id not in _mock_jobs:
        return {"error": "Job not found", "job_id": job_id}
    return _mock_jobs[job_id]


@router.get("/jobs")
async def list_training_jobs() -> dict[str, list[dict[str, Any]]]:
    """List all training jobs"""
    return {"jobs": list(_mock_jobs.values())}


@router.post("/jobs/{job_id}/progress")
async def update_progress(job_id: str, req: UpdateProgressRequest) -> dict[str, str]:
    """Update training progress"""
    if job_id not in _mock_jobs:
        return {"error": "Job not found", "job_id": job_id}

    _mock_jobs[job_id]["current_epoch"] = req.epoch
    _mock_jobs[job_id]["current_step"] = req.step
    _mock_jobs[job_id]["loss"] = req.loss
    _mock_jobs[job_id]["accuracy"] = req.accuracy
    _mock_jobs[job_id]["validation_loss"] = req.validation_loss
    _mock_jobs[job_id]["status"] = "training"

    return {"job_id": job_id, "status": "progress_updated"}


@router.post("/jobs/{job_id}/complete")
async def complete_training(job_id: str, req: CompleteTrainingRequest) -> dict[str, str]:
    """Mark training job as complete"""
    if job_id not in _mock_jobs:
        return {"error": "Job not found", "job_id": job_id}

    _mock_jobs[job_id]["status"] = "completed"
    _mock_jobs[job_id]["final_accuracy"] = req.final_accuracy
    _mock_jobs[job_id]["final_loss"] = req.final_loss
    _mock_jobs[job_id]["model_path"] = req.model_path

    return {"job_id": job_id, "status": "completed"}


@router.delete("/jobs/{job_id}")
async def delete_training_job(job_id: str) -> dict[str, str]:
    """Delete a training job"""
    if job_id not in _mock_jobs:
        return {"error": "Job not found", "job_id": job_id}

    del _mock_jobs[job_id]
    return {"job_id": job_id, "status": "deleted"}
