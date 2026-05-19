"""
Training Router - AI model training API endpoints

Provides:
- Training job creation
- Progress monitoring
- Model checkpointing
- Training logs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.training_service import get_training_service, TrainingStatus
from ..rate_limiting import rate_limit


router = APIRouter(prefix="/training", tags=["training"])


class CreateTrainingRequest(BaseModel):
    """Request to create training job"""
    model_type: str = Field(..., description="Type of model: llm, vision, audio, etc.")
    dataset_id: str
    hyperparameters: Optional[Dict[str, Any]] = None
    epochs: int = Field(default=10, ge=1, le=1000)
    gpu_count: int = Field(default=1, ge=0, le=8)
    memory_gb: int = Field(default=16, ge=4, le=128)


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
    checkpoint_url: Optional[str] = None


@router.post("/jobs", summary="Create training job")
@rate_limit(rate=10, per=3600)
async def create_training(
    request: Request,
    req: CreateTrainingRequest
) -> Dict[str, Any]:
    """Create a new AI model training job"""
    try:
        service = get_training_service()
        
        job = service.create_training_job(
            model_type=req.model_type,
            dataset_id=req.dataset_id,
            hyperparameters=req.hyperparameters,
            epochs=req.epochs,
            gpu_count=req.gpu_count,
            memory_gb=req.memory_gb
        )
        
        return {
            "success": True,
            "job": job.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create training job: {str(e)}"
        )


@router.get("/jobs/{job_id}", summary="Get training job")
@rate_limit(rate=100, per=60)
async def get_training(
    request: Request,
    job_id: str
) -> Dict[str, Any]:
    """Get training job details"""
    try:
        service = get_training_service()
        
        job = service.get_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Training job {job_id} not found"
            )
        
        return job.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job: {str(e)}"
        )


@router.get("/jobs", summary="List training jobs")
@rate_limit(rate=50, per=60)
async def list_trainings(
    request: Request,
    status: Optional[str] = None,
    model_type: Optional[str] = None
) -> Dict[str, Any]:
    """List all training jobs with optional filters"""
    try:
        service = get_training_service()
        
        jobs = service.list_jobs(status=status, model_type=model_type)
        
        return {
            "jobs": [j.to_dict() for j in jobs],
            "count": len(jobs),
            "filters": {
                "status": status,
                "model_type": model_type
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}"
        )


@router.post("/jobs/{job_id}/start", summary="Start training")
@rate_limit(rate=20, per=60)
async def start_training(
    request: Request,
    job_id: str
) -> Dict[str, Any]:
    """Start a pending training job"""
    try:
        service = get_training_service()
        
        job = service.start_training(job_id)
        
        return {
            "success": True,
            "job": job.to_dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {str(e)}"
        )


@router.post("/progress", summary="Update training progress")
@rate_limit(rate=200, per=60)
async def update_progress(
    request: Request,
    req: UpdateProgressRequest
) -> Dict[str, Any]:
    """Update training progress (called by training workers)"""
    try:
        service = get_training_service()
        
        job = service.update_progress(
            job_id=req.job_id,
            epoch=req.epoch,
            step=req.step,
            loss=req.loss,
            accuracy=req.accuracy,
            validation_loss=req.validation_loss
        )
        
        return {
            "success": True,
            "job": job.to_dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update progress: {str(e)}"
        )


@router.post("/jobs/{job_id}/complete", summary="Complete training")
@rate_limit(rate=20, per=60)
async def complete_training(
    request: Request,
    job_id: str,
    checkpoint_url: Optional[str] = None
) -> Dict[str, Any]:
    """Mark training as complete"""
    try:
        service = get_training_service()
        
        job = service.complete_training(job_id, checkpoint_url)
        
        return {
            "success": True,
            "job": job.to_dict(),
            "message": "Training completed successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete training: {str(e)}"
        )


@router.post("/jobs/{job_id}/cancel", summary="Cancel training")
@rate_limit(rate=10, per=60)
async def cancel_training(
    request: Request,
    job_id: str
) -> Dict[str, Any]:
    """Cancel a training job"""
    try:
        service = get_training_service()
        
        job = service.cancel_training(job_id)
        
        return {
            "success": True,
            "job": job.to_dict(),
            "message": "Training cancelled"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel training: {str(e)}"
        )


@router.get("/jobs/{job_id}/logs", summary="Get training logs")
@rate_limit(rate=50, per=60)
async def get_logs(
    request: Request,
    job_id: str,
    limit: int = 100
) -> Dict[str, Any]:
    """Get training job logs"""
    try:
        service = get_training_service()
        
        logs = service.get_job_logs(job_id, limit=limit)
        
        return {
            "job_id": job_id,
            "logs": logs,
            "count": len(logs)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get logs: {str(e)}"
        )


@router.get("/stats", summary="Training statistics")
@rate_limit(rate=30, per=60)
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get training platform statistics"""
    try:
        service = get_training_service()
        
        return service.get_stats()
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/health", summary="Health check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check training service health"""
    try:
        service = get_training_service()
        stats = service.get_stats()
        
        return {
            "status": "healthy",
            "total_jobs": stats["total_jobs"],
            "running": stats["running"],
            "max_concurrent": stats["max_concurrent"]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
