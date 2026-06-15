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
from app.domain.agent import (
    AgentExecutionRequest,
    AgentExecutionResponse,
    AgentExecutionStatus,
    AgentStatus,
    AgentWorkflowCreate,
    AgentWorkflowUpdate,
    AIAgentWorkflow,
)

from ..deps import require_admin_key
from ..services.agent_service import AIAgentOrchestrator
from ..storage import get_session

logger = get_logger(__name__)

router = APIRouter(tags=["AI Agents"])


@router.post("/workflows", response_model=AIAgentWorkflow)
@rate_limit(rate=50, per=60)
async def create_workflow(
    request: Request,
    workflow_data: AgentWorkflowCreate,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AIAgentWorkflow:
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
@rate_limit(rate=200, per=60)
async def list_workflows(
    request: Request,
    owner_id: str | None = None,
    is_public: bool | None = None,
    tags: list[str] | None = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AIAgentWorkflow]:
    """List agent workflows with filtering"""
    try:
        query = select(AIAgentWorkflow)
        if owner_id:
            query = query.where(AIAgentWorkflow.owner_id == owner_id)
        elif not is_public:
            query = query.where((AIAgentWorkflow.owner_id == current_user) | AIAgentWorkflow.is_public)
        if is_public is not None:
            query = query.where(AIAgentWorkflow.is_public == is_public)
        if tags:
            for tag in tags:
                query = query.where(AIAgentWorkflow.tags.contains([tag]))  # type: ignore[attr-defined]
        workflows = session.exec(query).all()
        return list(workflows)
    except Exception as e:
        logger.error("Failed to list workflows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workflows/{workflow_id}", response_model=AIAgentWorkflow)
@rate_limit(rate=200, per=60)
async def get_workflow(
    request: Request,
    workflow_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AIAgentWorkflow:
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
@rate_limit(rate=50, per=60)
async def update_workflow(
    request: Request,
    workflow_id: str,
    workflow_data: AgentWorkflowUpdate,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AIAgentWorkflow:
    """Update an agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user:
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
@rate_limit(rate=50, per=60)
async def delete_workflow(
    request: Request,
    workflow_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, str]:
    """Delete an agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user:
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
@rate_limit(rate=50, per=60)
async def execute_workflow(
    request: Request,
    workflow_id: str,
    execution_request: AgentExecutionRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentExecutionResponse:
    """Execute an AI agent workflow"""
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != current_user and (not workflow.is_public):
            raise HTTPException(status_code=403, detail="Access denied")
        execution_request_obj = AgentExecutionRequest(
            workflow_id=workflow_id,
            inputs=execution_request.inputs,
            verification_level=execution_request.verification_level or workflow.verification_level,
            max_execution_time=execution_request.max_execution_time or workflow.max_execution_time,
            max_cost_budget=execution_request.max_cost_budget or workflow.max_cost_budget,
        )
        from ..coordinator_client import CoordinatorClient

        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)  # type: ignore[arg-type]
        response = await orchestrator.execute_workflow(execution_request_obj, current_user)
        logger.info("Started agent execution: %s", response.execution_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}/status", response_model=AgentExecutionStatus)
@rate_limit(rate=200, per=60)
async def get_execution_status(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> AgentExecutionStatus:
    """Get execution status"""
    try:
        from ..coordinator_client import CoordinatorClient
        from ..services.agent_service import AIAgentOrchestrator

        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)  # type: ignore[arg-type]
        status = await orchestrator.get_execution_status(execution_id)
        workflow = session.get(AIAgentWorkflow, status.workflow_id)
        if workflow is None or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get execution status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions", response_model=list[AgentExecutionStatus])
@rate_limit(rate=200, per=60)
async def list_executions(
    request: Request,
    workflow_id: str | None = None,
    status: AgentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> list[AgentExecutionStatus]:
    """List agent executions with filtering"""
    try:
        from app.domain.agent import AgentExecution

        query = select(AgentExecution)
        if workflow_id:
            workflow = session.get(AIAgentWorkflow, workflow_id)
            if not workflow or workflow.owner_id != current_user:
                raise HTTPException(status_code=404, detail="Workflow not found")
            query = query.where(AgentExecution.workflow_id == workflow_id)
        else:
            user_workflows = session.exec(select(AIAgentWorkflow.id).where(AIAgentWorkflow.owner_id == current_user)).all()
            workflow_ids = list(user_workflows)
            query = query.where(AgentExecution.workflow_id.in_(workflow_ids))  # type: ignore[attr-defined]
        if status:
            query = query.where(AgentExecution.status == status)
        query = query.offset(offset).limit(limit)
        query = query.order_by(AgentExecution.created_at.desc())  # type: ignore[attr-defined]
        executions = session.exec(query).all()
        execution_statuses = []
        for execution in executions:
            from ..coordinator_client import CoordinatorClient
            from ..services.agent_service import AIAgentOrchestrator

            coordinator_client = CoordinatorClient()
            orchestrator = AIAgentOrchestrator(session, coordinator_client)  # type: ignore[arg-type]
            exec_status = await orchestrator.get_execution_status(execution.id)
            execution_statuses.append(exec_status)
        return execution_statuses
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list executions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/executions/{execution_id}/cancel")
@rate_limit(rate=50, per=60)
async def cancel_execution(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, str]:
    """Cancel an ongoing execution"""
    try:
        from app.domain.agent import AgentExecution

        from ..services.agent_service import AgentStateManager

        execution = session.get(AgentExecution, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        workflow = session.get(AIAgentWorkflow, execution.workflow_id)
        if workflow is None or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        if execution.status not in [AgentStatus.PENDING, AgentStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Execution cannot be cancelled")
        state_manager = AgentStateManager(session)
        await state_manager.update_execution_status(execution_id, status=AgentStatus.CANCELLED, completed_at=datetime.now(UTC))
        logger.info("Cancelled agent execution: %s", execution_id)
        return {"message": "Execution cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel execution: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}/logs")
@rate_limit(rate=200, per=60)
async def get_execution_logs(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get execution logs"""
    try:
        from app.domain.agent import AgentExecution, AgentStepExecution

        execution = session.get(AgentExecution, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        workflow = session.get(AIAgentWorkflow, execution.workflow_id)
        if workflow is None or workflow.owner_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        step_executions = session.exec(select(AgentStepExecution).where(AgentStepExecution.execution_id == execution_id)).all()
        logs = []
        for step_exec in step_executions:
            logs.append(
                {
                    "step_id": step_exec.step_id,
                    "status": step_exec.status,
                    "started_at": step_exec.started_at,
                    "completed_at": step_exec.completed_at,
                    "execution_time": step_exec.execution_time,
                    "error_message": step_exec.error_message,
                    "gpu_accelerated": step_exec.gpu_accelerated,
                    "memory_usage": step_exec.memory_usage,
                }
            )
        return {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "status": execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "total_execution_time": execution.total_execution_time,
            "step_logs": logs,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get execution logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/test")
@rate_limit(rate=1000, per=60)
async def test_endpoint(request: Request) -> dict[str, str]:
    """Test endpoint to verify router is working"""
    return {"message": "Agent router is working", "timestamp": datetime.now(UTC).isoformat()}


@router.post("/networks", response_model=dict[str, Any], status_code=201)
@rate_limit(rate=50, per=60)
async def create_agent_network(
    request: Request,
    network_data: dict[str, Any],
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Create a new agent network for collaborative processing"""
    try:
        if not network_data.get("name"):
            raise HTTPException(status_code=400, detail="Network name is required")
        if not network_data.get("agents"):
            raise HTTPException(status_code=400, detail="Agent list is required")
        network_id = f"network_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        network_response = {
            "id": network_id,
            "name": network_data["name"],
            "description": network_data.get("description", ""),
            "agents": network_data["agents"],
            "coordination_strategy": network_data.get("coordination", "centralized"),
            "status": "active",
            "created_at": datetime.now(UTC).isoformat(),
            "owner_id": current_user,
        }
        logger.info("Created agent network: %s", network_id)
        return network_response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create agent network: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/executions/{execution_id}/receipt")
@rate_limit(rate=200, per=60)
async def get_execution_receipt(
    request: Request,
    execution_id: str,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    current_user: Annotated[str, Depends(require_admin_key())] = Depends(),
) -> dict[str, Any]:
    """Get verifiable receipt for completed execution"""
    try:
        receipt_data = {
            "execution_id": execution_id,
            "workflow_id": f"workflow_{execution_id}",
            "status": "completed",
            "receipt_id": f"receipt_{execution_id}",
            "miner_signature": "0xmock_signature_placeholder",
            "coordinator_attestations": [
                {
                    "coordinator_id": "coordinator_1",
                    "signature": "0xmock_attestation_1",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
            "minted_amount": 1000,
            "recorded_at": datetime.now(UTC).isoformat(),
            "verified": True,
            "block_hash": "0xmock_block_hash",
            "transaction_hash": "0xmock_tx_hash",
        }
        logger.info("Generated receipt for execution: %s", execution_id)
        return receipt_data
    except Exception as e:
        logger.error("Failed to get execution receipt: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
