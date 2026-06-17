"""
Workflow Router for AITBC Agent Coordinator
Provides API endpoints for workflow management and execution
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger

from ..workflow import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent/workflows", tags=["workflows"])


class CreateWorkflowRequest(BaseModel):
    """Request to create a workflow"""

    name: str = Field(..., description="Workflow name")
    description: str = Field(default="", description="Workflow description")
    steps: list[dict[str, Any]] = Field(..., description="Workflow steps")
    created_by: str = Field(default="", description="Creator identifier")


class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow"""

    input_parameters: dict[str, Any] = Field(default_factory=dict, description="Input parameters for workflow")


class WorkflowResponse(BaseModel):
    """Workflow response"""

    workflow_id: str
    name: str
    description: str
    steps: list[dict[str, Any]]
    created_at: str
    created_by: str


class ExecutionResponse(BaseModel):
    """Workflow execution response"""

    execution_id: str
    workflow_id: str
    status: str
    current_step_index: int
    results: dict[str, Any]
    error: str | None
    started_at: str
    completed_at: str | None
    steps: list[dict[str, Any]]


@router.post("", summary="Create workflow", response_model=WorkflowResponse)
async def create_workflow(request: Request, req: CreateWorkflowRequest) -> dict[str, Any]:
    """Create a new workflow definition"""
    try:
        orchestrator = get_orchestrator()
        workflow = await orchestrator.create_workflow(
            name=req.name, steps=req.steps, created_by=req.created_by, description=req.description
        )
        return workflow.to_dict()
    except Exception as e:
        logger.error("Error creating workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{workflow_id}/execute", summary="Execute workflow", response_model=ExecutionResponse)
async def execute_workflow(request: Request, workflow_id: str, req: ExecuteWorkflowRequest) -> dict[str, Any]:
    """Execute a workflow"""
    try:
        orchestrator = get_orchestrator()
        execution = await orchestrator.execute_workflow(workflow_id=workflow_id, input_parameters=req.input_parameters)
        return execution.to_dict()
    except ValueError as e:
        logger.error("Workflow not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error executing workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{workflow_id}/status", summary="Get workflow status")
async def get_workflow_status(request: Request, workflow_id: str) -> dict[str, Any]:
    """Get workflow execution status"""
    try:
        orchestrator = get_orchestrator()
        executions = await orchestrator.list_executions(workflow_id=workflow_id)
        if not executions:
            raise HTTPException(status_code=404, detail="No executions found for this workflow")
        latest_execution = max(executions, key=lambda e: e.started_at)
        return latest_execution.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting workflow status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("", summary="List workflows")
async def list_workflows(request: Request) -> dict[str, Any]:
    """List all workflow definitions"""
    try:
        orchestrator = get_orchestrator()
        workflows = await orchestrator.list_workflows()
        return {"workflows": [wf.to_dict() for wf in workflows], "count": len(workflows)}
    except Exception as e:
        logger.error("Error listing workflows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions", summary="List executions")
async def list_executions(request: Request, workflow_id: str | None = None) -> dict[str, Any]:
    """List workflow executions"""
    try:
        orchestrator = get_orchestrator()
        executions = await orchestrator.list_executions(workflow_id=workflow_id or "")
        return {"executions": [exec.to_dict() for exec in executions], "count": len(executions)}
    except Exception as e:
        logger.error("Error listing executions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/executions/{execution_id}/cancel", summary="Cancel execution")
async def cancel_execution(request: Request, execution_id: str) -> dict[str, Any]:
    """Cancel a workflow execution"""
    try:
        orchestrator = get_orchestrator()
        success = await orchestrator.cancel_execution(execution_id)
        if not success:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {"status": "cancelled", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error cancelling execution: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
