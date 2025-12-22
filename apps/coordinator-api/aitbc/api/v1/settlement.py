"""
API endpoints for cross-chain settlements
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
import asyncio

from ...settlement.hooks import SettlementHook
from ...settlement.manager import BridgeManager
from ...settlement.bridges.base import SettlementResult
from ...auth import get_api_key
from ...models.job import Job

router = APIRouter(prefix="/settlement", tags=["settlement"])


class CrossChainSettlementRequest(BaseModel):
    """Request model for cross-chain settlement"""
    job_id: str = Field(..., description="ID of the job to settle")
    target_chain_id: int = Field(..., description="Target blockchain chain ID")
    bridge_name: Optional[str] = Field(None, description="Specific bridge to use")
    priority: str = Field("cost", description="Settlement priority: 'cost' or 'speed'")
    privacy_level: Optional[str] = Field(None, description="Privacy level: 'basic' or 'enhanced'")
    use_zk_proof: bool = Field(False, description="Use zero-knowledge proof for privacy")


class SettlementEstimateRequest(BaseModel):
    """Request model for settlement cost estimation"""
    job_id: str = Field(..., description="ID of the job")
    target_chain_id: int = Field(..., description="Target blockchain chain ID")
    bridge_name: Optional[str] = Field(None, description="Specific bridge to use")


class BatchSettlementRequest(BaseModel):
    """Request model for batch settlement"""
    job_ids: List[str] = Field(..., description="List of job IDs to settle")
    target_chain_id: int = Field(..., description="Target blockchain chain ID")
    bridge_name: Optional[str] = Field(None, description="Specific bridge to use")


class SettlementResponse(BaseModel):
    """Response model for settlement operations"""
    message_id: str = Field(..., description="Settlement message ID")
    status: str = Field(..., description="Settlement status")
    transaction_hash: Optional[str] = Field(None, description="Transaction hash")
    bridge_name: str = Field(..., description="Bridge used")
    estimated_completion: Optional[str] = Field(None, description="Estimated completion time")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class CostEstimateResponse(BaseModel):
    """Response model for cost estimates"""
    bridge_costs: Dict[str, Dict[str, Any]] = Field(..., description="Costs by bridge")
    recommended_bridge: str = Field(..., description="Recommended bridge")
    total_estimates: Dict[str, float] = Field(..., description="Min/Max/Average costs")


def get_settlement_hook() -> SettlementHook:
    """Dependency injection for settlement hook"""
    # This would be properly injected in the app setup
    from ...main import settlement_hook
    return settlement_hook


def get_bridge_manager() -> BridgeManager:
    """Dependency injection for bridge manager"""
    # This would be properly injected in the app setup
    from ...main import bridge_manager
    return bridge_manager


@router.post("/cross-chain", response_model=SettlementResponse)
async def initiate_cross_chain_settlement(
    request: CrossChainSettlementRequest,
    background_tasks: BackgroundTasks,
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """
    Initiate cross-chain settlement for a completed job
    
    This endpoint settles job receipts and payments across different blockchains
    using various bridge protocols (LayerZero, Chainlink CCIP, etc.).
    """
    try:
        # Validate job exists and is completed
        job = await Job.get(request.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if not job.completed:
            raise HTTPException(status_code=400, detail="Job is not completed")
        
        if job.cross_chain_settlement_id:
            raise HTTPException(
                status_code=409, 
                detail=f"Job already has settlement {job.cross_chain_settlement_id}"
            )
        
        # Initiate settlement
        settlement_options = {}
        if request.use_zk_proof:
            settlement_options["privacy_level"] = request.privacy_level or "basic"
            settlement_options["use_zk_proof"] = True
        
        result = await settlement_hook.initiate_manual_settlement(
            job_id=request.job_id,
            target_chain_id=request.target_chain_id,
            bridge_name=request.bridge_name,
            options=settlement_options
        )
        
        # Add background task to monitor settlement
        background_tasks.add_task(
            monitor_settlement_completion,
            result.message_id,
            request.job_id
        )
        
        return SettlementResponse(
            message_id=result.message_id,
            status=result.status.value,
            transaction_hash=result.transaction_hash,
            bridge_name=result.transaction_hash and await get_bridge_from_tx(result.transaction_hash),
            estimated_completion=estimate_completion_time(result.status),
            error_message=result.error_message
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Settlement failed: {str(e)}")


@router.get("/{message_id}/status", response_model=SettlementResponse)
async def get_settlement_status(
    message_id: str,
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """Get the current status of a cross-chain settlement"""
    try:
        result = await settlement_hook.get_settlement_status(message_id)
        
        # Get job info if available
        job_id = None
        if result.transaction_hash:
            job_id = await get_job_id_from_settlement(message_id)
        
        return SettlementResponse(
            message_id=message_id,
            status=result.status.value,
            transaction_hash=result.transaction_hash,
            bridge_name=job_id and await get_bridge_from_job(job_id),
            estimated_completion=estimate_completion_time(result.status),
            error_message=result.error_message
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/estimate-cost", response_model=CostEstimateResponse)
async def estimate_settlement_cost(
    request: SettlementEstimateRequest,
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """Estimate the cost of cross-chain settlement"""
    try:
        # Get cost estimates
        estimates = await settlement_hook.estimate_settlement_cost(
            job_id=request.job_id,
            target_chain_id=request.target_chain_id,
            bridge_name=request.bridge_name
        )
        
        # Calculate totals and recommendations
        valid_estimates = {
            name: cost for name, cost in estimates.items()
            if 'error' not in cost
        }
        
        if not valid_estimates:
            raise HTTPException(
                status_code=400,
                detail="No bridges available for this settlement"
            )
        
        # Find cheapest option
        cheapest_bridge = min(valid_estimates.items(), key=lambda x: x[1]['total'])
        
        # Calculate statistics
        costs = [est['total'] for est in valid_estimates.values()]
        total_estimates = {
            "min": min(costs),
            "max": max(costs),
            "average": sum(costs) / len(costs)
        }
        
        return CostEstimateResponse(
            bridge_costs=estimates,
            recommended_bridge=cheapest_bridge[0],
            total_estimates=total_estimates
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Estimation failed: {str(e)}")


@router.post("/batch", response_model=List[SettlementResponse])
async def batch_settle(
    request: BatchSettlementRequest,
    background_tasks: BackgroundTasks,
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """Settle multiple jobs in a batch"""
    try:
        # Validate all jobs exist and are completed
        jobs = []
        for job_id in request.job_ids:
            job = await Job.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            if not job.completed:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Job {job_id} is not completed"
                )
            jobs.append(job)
        
        # Process batch settlement
        results = []
        for job in jobs:
            try:
                result = await settlement_hook.initiate_manual_settlement(
                    job_id=job.id,
                    target_chain_id=request.target_chain_id,
                    bridge_name=request.bridge_name
                )
                
                # Add monitoring task
                background_tasks.add_task(
                    monitor_settlement_completion,
                    result.message_id,
                    job.id
                )
                
                results.append(SettlementResponse(
                    message_id=result.message_id,
                    status=result.status.value,
                    transaction_hash=result.transaction_hash,
                    bridge_name=result.transaction_hash and await get_bridge_from_tx(result.transaction_hash),
                    estimated_completion=estimate_completion_time(result.status),
                    error_message=result.error_message
                ))
                
            except Exception as e:
                results.append(SettlementResponse(
                    message_id="",
                    status="failed",
                    transaction_hash=None,
                    bridge_name="",
                    estimated_completion=None,
                    error_message=str(e)
                ))
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch settlement failed: {str(e)}")


@router.get("/bridges", response_model=Dict[str, Any])
async def list_supported_bridges(
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """List all supported bridges and their capabilities"""
    try:
        return await settlement_hook.list_supported_bridges()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list bridges: {str(e)}")


@router.get("/chains", response_model=Dict[str, List[int]])
async def list_supported_chains(
    settlement_hook: SettlementHook = Depends(get_settlement_hook)
):
    """List all supported chains by bridge"""
    try:
        return await settlement_hook.list_supported_chains()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list chains: {str(e)}")


@router.post("/{message_id}/refund")
async def refund_settlement(
    message_id: str,
    bridge_manager: BridgeManager = Depends(get_bridge_manager)
):
    """Attempt to refund a failed settlement"""
    try:
        result = await bridge_manager.refund_failed_settlement(message_id)
        
        return {
            "message_id": message_id,
            "status": result.status.value,
            "refund_transaction": result.transaction_hash,
            "error_message": result.error_message
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refund failed: {str(e)}")


@router.get("/job/{job_id}/settlements")
async def get_job_settlements(
    job_id: str,
    bridge_manager: BridgeManager = Depends(get_bridge_manager)
):
    """Get all cross-chain settlements for a job"""
    try:
        # Validate job exists
        job = await Job.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get settlements from storage
        settlements = await bridge_manager.storage.get_settlements_by_job(job_id)
        
        return {
            "job_id": job_id,
            "settlements": settlements,
            "total_count": len(settlements)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settlements: {str(e)}")


# Helper functions
async def monitor_settlement_completion(message_id: str, job_id: str):
    """Background task to monitor settlement completion"""
    settlement_hook = get_settlement_hook()
    
    # Monitor for up to 1 hour
    max_wait = 3600
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < max_wait:
        result = await settlement_hook.get_settlement_status(message_id)
        
        # Update job status
        job = await Job.get(job_id)
        if job:
            job.cross_chain_settlement_status = result.status.value
            await job.save()
        
        # If completed or failed, stop monitoring
        if result.status.value in ['completed', 'failed']:
            break
        
        # Wait before checking again
        await asyncio.sleep(30)


def estimate_completion_time(status) -> Optional[str]:
    """Estimate completion time based on status"""
    if status.value == 'completed':
        return None
    elif status.value == 'pending':
        return "5-10 minutes"
    elif status.value == 'in_progress':
        return "2-5 minutes"
    else:
        return None


async def get_bridge_from_tx(tx_hash: str) -> str:
    """Get bridge name from transaction hash"""
    # This would look up the bridge from the transaction
    # For now, return placeholder
    return "layerzero"


async def get_bridge_from_job(job_id: str) -> str:
    """Get bridge name from job"""
    # This would look up the bridge from the job
    # For now, return placeholder
    return "layerzero"


async def get_job_id_from_settlement(message_id: str) -> Optional[str]:
    """Get job ID from settlement message ID"""
    # This would look up the job ID from storage
    # For now, return None
    return None
