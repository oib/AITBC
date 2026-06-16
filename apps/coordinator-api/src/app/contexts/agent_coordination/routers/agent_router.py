"""
AI Agent API Router for Verifiable AI Agent Orchestration
Provides REST API endpoints for agent workflow management and execution
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlmodel import Session, select

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ....deps import require_admin_key
from ....domain.agent import (
    AgentExecutionRequest,
    AgentExecutionResponse,
    AgentExecutionStatus,
    AgentStatus,
    AgentWorkflowCreate,
    AgentWorkflowUpdate,
    AIAgentWorkflow,
)
from ....services.agent_coordination.agent_service import AIAgentOrchestrator
from ....storage import get_session

logger = get_logger(__name__)

router = APIRouter(tags=["AI Agents"])


@router.post("/workflows", response_model=AIAgentWorkflow)
async def create_workflow(
    workflow_data: AgentWorkflowCreate,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> AIAgentWorkflow:  # type: ignore[arg-type]
    """Create a new AI agent workflow"""
    try:
        workflow = AIAgentWorkflow(owner_id=current_user, **workflow_data.dict())
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        logger.info("Created agent workflow: %s", workflow.id)
        return workflow
    except Exception as e:
        logger.error("Failed to create workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workflows", response_model=list[AIAgentWorkflow])
async def list_workflows(
    owner_id: str | None,
    is_public: bool | None,
    tags: list[str] | None,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> list[AIAgentWorkflow]:  # type: ignore[arg-type]
    """List agent workflows with filtering"""
    try:
        query = select(AIAgentWorkflow)
        if owner_id:
            query = query.where(AIAgentWorkflow.owner_id == owner_id)
        elif not is_public:
            query = query.where((AIAgentWorkflow.owner_id == current_user.id) | AIAgentWorkflow.is_public)  # type: ignore[attr-defined]
        if is_public is not None:
            query = query.where(AIAgentWorkflow.is_public == is_public)
        if tags:
            for tag in tags:
                query = query.where(AIAgentWorkflow.tags.contains([tag]))  # type: ignore[attr-defined]
        workflows = session.execute(query).all()
        return workflows  # type: ignore[return-value]
    except Exception as e:
        logger.error("Failed to list workflows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workflows/{workflow_id}", response_model=AIAgentWorkflow)
@rate_limit(rate=200, per=60)
async def get_workflow(
    workflow_id: str,
    request: Request,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> AIAgentWorkflow:  # type: ignore[arg-type]
    """Get a specific agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user and (not workflow.is_public):
            raise HTTPException(status_code=403, detail="Access denied")
        return workflow
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/workflows/{workflow_id}", response_model=AIAgentWorkflow)
@rate_limit(rate=100, per=60)
async def update_workflow(
    workflow_id: str,
    workflow_data: AgentWorkflowUpdate,
    request: Request,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> AIAgentWorkflow:  # type: ignore[arg-type]
    """Update an agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user.id:  # type: ignore[attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        update_data = workflow_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(workflow, field, value)
        workflow.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(workflow)
        logger.info("Updated agent workflow: %s", workflow.id)
        return workflow
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> dict[str, str]:  # type: ignore[arg-type]
    """Delete an agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user.id:  # type: ignore[attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        session.delete(workflow)
        session.commit()
        logger.info("Deleted agent workflow: %s", workflow_id)
        return {"message": "Workflow deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/workflows/{workflow_id}/execute", response_model=AgentExecutionResponse)
async def execute_workflow(
    workflow_id: str,
    execution_request: AgentExecutionRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> AgentExecutionResponse:  # type: ignore[arg-type]
    """Execute an AI agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user.id and (not workflow.is_public):  # type: ignore[attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        request = AgentExecutionRequest(
            workflow_id=workflow_id,
            inputs=execution_request.inputs,
            verification_level=execution_request.verification_level or workflow.verification_level,
            max_execution_time=execution_request.max_execution_time or workflow.max_execution_time,
            max_cost_budget=execution_request.max_cost_budget or workflow.max_cost_budget,
        )
        from app.services.agent_coordination.coordinator_client import CoordinatorClient  # type: ignore[import-not-found]

        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)  # type: ignore[arg-type]
        response = await orchestrator.execute_workflow(request, current_user.id)  # type: ignore[attr-defined]
        logger.info("Started agent execution: %s", response.execution_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}/status", response_model=AgentExecutionStatus)
async def get_execution_status(
    execution_id: str,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> AgentExecutionStatus:  # type: ignore[arg-type]
    """Get execution status"""
    try:
        from app.services.agent_coordination.agent_service import AIAgentOrchestrator  # type: ignore[import-not-found]
        from app.services.agent_coordination.coordinator_client import CoordinatorClient

        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)
        status = await orchestrator.get_execution_status(execution_id)
        workflow = session.get(AIAgentWorkflow, status.workflow_id)
        if workflow.owner_id != current_user.id:  # type: ignore[union-attr, attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        return status  # type: ignore[no-any-return]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get execution status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions", response_model=list[AgentExecutionStatus])
async def list_executions(
    workflow_id: str | None,
    status: AgentStatus | None,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> list[AgentExecutionStatus]:  # type: ignore[arg-type]
    """List agent executions with filtering"""
    try:
        from app.domain.agent import AgentExecution  # type: ignore[import-not-found]

        query = select(AgentExecution)
        if workflow_id:
            workflow = session.get(AIAgentWorkflow, workflow_id)
            if not workflow or workflow.owner_id != current_user.id:  # type: ignore[attr-defined]
                raise HTTPException(status_code=403, detail="Access denied")
            query = query.where(AgentExecution.workflow_id == workflow_id)
        if status:
            query = query.where(AgentExecution.status == status)
        executions = session.execute(query.offset(offset).limit(limit)).all()
        return executions  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list executions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    execution_id: str,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Cancel a workflow execution"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user.id:  # type: ignore[attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        from app.services.agent_coordination.coordinator_client import CoordinatorClient  # type: ignore[import-not-found]

        coordinator_client = CoordinatorClient()
        from app.services.agent_coordination.agent_service import AIAgentOrchestrator  # type: ignore[import-not-found]

        orchestrator = AIAgentOrchestrator(session, coordinator_client)
        result = await orchestrator.cancel_execution(execution_id)
        logger.info("Cancelled workflow execution: %s", execution_id)
        return result  # type: ignore[no-any-return]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workflows/{workflow_id}/executions", response_model=list[AgentExecutionStatus])
async def list_workflow_executions(
    workflow_id: str,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(Annotated[Session, Depends(get_session)])],
    current_user: Annotated[str, Depends(require_admin_key())],
) -> list[AgentExecutionStatus]:  # type: ignore[arg-type]
    """List executions for a specific workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user.id and (not workflow.is_public):  # type: ignore[attr-defined]
            raise HTTPException(status_code=403, detail="Access denied")
        from app.domain.agent import AgentExecution  # type: ignore[import-not-found]

        query = select(AgentExecution).where(AgentExecution.workflow_id == workflow_id)
        executions = session.execute(query.offset(offset).limit(limit)).all()
        return executions  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list workflow executions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
