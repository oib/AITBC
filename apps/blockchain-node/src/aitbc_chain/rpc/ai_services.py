"""AI Services RPC endpoints for AITBC blockchain"""

from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import uuid

from ..database import session_scope
from ..metrics import metrics_registry
from .router import router


class AIJobRequest(BaseModel):
    """AI job submission request"""
    wallet_address: str = Field(..., description="Client wallet address")
    job_type: str = Field(..., description="Type of AI job (text, image, training, etc.)")
    prompt: str = Field(..., description="AI prompt or task description")
    payment: float = Field(..., ge=0, description="Payment in AIT")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Additional job parameters")

class AIJobResponse(BaseModel):
    """AI job response"""
    job_id: str
    status: str
    wallet_address: str
    job_type: str
    payment: float
    created_at: datetime
    estimated_completion: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None

# In-memory storage for demo (in production, use database)
_ai_jobs: List[Dict[str, Any]] = [
    {
        "job_id": "job_demo_001",
        "wallet_address": "ait1demo_client_123...",
        "job_type": "text",
        "prompt": "Generate a summary of blockchain technology",
        "payment": 100.0,
        "status": "completed",
        "created_at": (datetime.now() - timedelta(hours=1)).isoformat(),
        "completed_at": (datetime.now() - timedelta(minutes=30)).isoformat(),
        "result": {
            "output": "Blockchain is a distributed ledger technology...",
            "tokens_used": 150,
            "processing_time": "2.5 minutes"
        }
    },
    {
        "job_id": "job_demo_002",
        "wallet_address": "ait1demo_client_456...",
        "job_type": "image",
        "prompt": "Create an image of a futuristic blockchain city",
        "payment": 250.0,
        "status": "processing",
        "created_at": (datetime.now() - timedelta(minutes=15)).isoformat(),
        "estimated_completion": (datetime.now() + timedelta(minutes=10)).isoformat()
    }
]

@router.post("/ai/submit", summary="Submit AI job", tags=["ai"])
async def ai_submit_job(request: AIJobRequest) -> Dict[str, Any]:
    """Submit a new AI job for processing"""
    try:
        metrics_registry.increment("rpc_ai_submit_total")
        
        # Generate unique job ID
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        
        # Calculate estimated completion time
        estimated_completion = datetime.now() + timedelta(minutes=30)
        
        # Create new job
        new_job = {
            "job_id": job_id,
            "wallet_address": request.wallet_address,
            "job_type": request.job_type,
            "prompt": request.prompt,
            "payment": request.payment,
            "parameters": request.parameters or {},
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "estimated_completion": estimated_completion.isoformat()
        }
        
        # Add to storage
        _ai_jobs.append(new_job)
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "AI job submitted successfully",
            "estimated_completion": estimated_completion.isoformat(),
            "wallet_address": request.wallet_address,
            "payment": request.payment,
            "job_type": request.job_type
        }
        
    except Exception as e:
        metrics_registry.increment("rpc_ai_submit_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/jobs", summary="List AI jobs", tags=["ai"])
async def ai_list_jobs(wallet_address: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    """Get list of AI jobs, optionally filtered by wallet address or status"""
    try:
        metrics_registry.increment("rpc_ai_list_total")
        
        # Filter jobs
        filtered_jobs = _ai_jobs.copy()
        
        if wallet_address:
            filtered_jobs = [job for job in filtered_jobs if job.get("wallet_address") == wallet_address]
        
        if status:
            filtered_jobs = [job for job in filtered_jobs if job.get("status") == status]
        
        # Sort by creation time (newest first)
        filtered_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {
            "jobs": filtered_jobs,
            "total": len(filtered_jobs),
            "filters": {
                "wallet_address": wallet_address,
                "status": status
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        metrics_registry.increment("rpc_ai_list_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/job/{job_id}", summary="Get AI job by ID", tags=["ai"])
async def ai_get_job(job_id: str) -> Dict[str, Any]:
    """Get a specific AI job by ID"""
    try:
        metrics_registry.increment("rpc_ai_get_total")
        
        # Find job
        for job in _ai_jobs:
            if job.get("job_id") == job_id:
                return {
                    "job": job,
                    "found": True
                }
        
        raise HTTPException(status_code=404, detail="Job not found")
        
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai/job/{job_id}/cancel", summary="Cancel AI job", tags=["ai"])
async def ai_cancel_job(job_id: str) -> Dict[str, Any]:
    """Cancel an AI job"""
    try:
        metrics_registry.increment("rpc_ai_cancel_total")
        
        # Find and update job
        for job in _ai_jobs:
            if job.get("job_id") == job_id:
                current_status = job.get("status")
                if current_status in ["completed", "cancelled"]:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Cannot cancel job with status: {current_status}"
                    )
                
                job["status"] = "cancelled"
                job["cancelled_at"] = datetime.now().isoformat()
                
                return {
                    "job_id": job_id,
                    "status": "cancelled",
                    "message": "AI job cancelled successfully"
                }
        
        raise HTTPException(status_code=404, detail="Job not found")
        
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_cancel_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/stats", summary="AI service statistics", tags=["ai"])
async def ai_stats() -> Dict[str, Any]:
    """Get AI service statistics"""
    try:
        metrics_registry.increment("rpc_ai_stats_total")
        
        total_jobs = len(_ai_jobs)
        status_counts = {}
        type_counts = {}
        total_revenue = 0.0
        
        for job in _ai_jobs:
            # Count by status
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count by type
            job_type = job.get("job_type", "unknown")
            type_counts[job_type] = type_counts.get(job_type, 0) + 1
            
            # Sum revenue for completed jobs
            if status == "completed":
                total_revenue += job.get("payment", 0.0)
        
        return {
            "total_jobs": total_jobs,
            "status_breakdown": status_counts,
            "type_breakdown": type_counts,
            "total_revenue": total_revenue,
            "average_payment": total_revenue / max(1, status_counts.get("completed", 0)),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        metrics_registry.increment("rpc_ai_stats_errors_total")
        raise HTTPException(status_code=500, detail=str(e))
