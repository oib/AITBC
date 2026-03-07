from sqlalchemy.orm import Session
from typing import Annotated
"""
AI Agent API Router for Verifiable AI Agent Orchestration
Provides REST API endpoints for agent workflow management and execution
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from datetime import datetime
from aitbc.logging import get_logger

from ..domain.agent import (
    AIAgentWorkflow, AgentWorkflowCreate, AgentWorkflowUpdate,
    AgentExecutionRequest, AgentExecutionResponse, AgentExecutionStatus,
    AgentStatus, VerificationLevel
)
from ..services.agent_service import AIAgentOrchestrator
from ..storage import get_session
from ..deps import require_admin_key
from sqlmodel import Session, select

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["AI Agents"])


@router.post("/workflows", response_model=AIAgentWorkflow)
async def create_workflow(
    workflow_data: AgentWorkflowCreate,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create a new AI agent workflow"""
    
    try:
        workflow = AIAgentWorkflow(
            owner_id=current_user,  # Use string directly
            **workflow_data.dict()
        )
        
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        
        logger.info(f"Created agent workflow: {workflow.id}")
        return workflow
        
    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows", response_model=List[AIAgentWorkflow])
async def list_workflows(
    owner_id: Optional[str] = None,
    is_public: Optional[bool] = None,
    tags: Optional[List[str]] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """List agent workflows with filtering"""
    
    try:
        query = select(AIAgentWorkflow)
        
        # Filter by owner or public workflows
        if owner_id:
            query = query.where(AIAgentWorkflow.owner_id == owner_id)
        elif not is_public:
            query = query.where(
                (AIAgentWorkflow.owner_id == current_user.id) |
                (AIAgentWorkflow.is_public == True)
            )
        
        # Filter by public status
        if is_public is not None:
            query = query.where(AIAgentWorkflow.is_public == is_public)
        
        # Filter by tags
        if tags:
            for tag in tags:
                query = query.where(AIAgentWorkflow.tags.contains([tag]))
        
        workflows = session.execute(query).all()
        return workflows
        
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}", response_model=AIAgentWorkflow)
async def get_workflow(
    workflow_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get a specific agent workflow"""
    
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check access permissions
        if workflow.owner_id != current_user and not workflow.is_public:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return workflow
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/workflows/{workflow_id}", response_model=AIAgentWorkflow)
async def update_workflow(
    workflow_id: str,
    workflow_data: AgentWorkflowUpdate,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Update an agent workflow"""
    
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check ownership
        if workflow.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update workflow
        update_data = workflow_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(workflow, field, value)
        
        workflow.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(workflow)
        
        logger.info(f"Updated agent workflow: {workflow.id}")
        return workflow
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Delete an agent workflow"""
    
    try:
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Check ownership
        if workflow.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        session.delete(workflow)
        session.commit()
        
        logger.info(f"Deleted agent workflow: {workflow_id}")
        return {"message": "Workflow deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{workflow_id}/execute", response_model=AgentExecutionResponse)
async def execute_workflow(
    workflow_id: str,
    execution_request: AgentExecutionRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Execute an AI agent workflow"""
    
    try:
        # Verify workflow exists and user has access
        workflow = session.get(AIAgentWorkflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        if workflow.owner_id != current_user.id and not workflow.is_public:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create execution request
        request = AgentExecutionRequest(
            workflow_id=workflow_id,
            inputs=execution_request.inputs,
            verification_level=execution_request.verification_level or workflow.verification_level,
            max_execution_time=execution_request.max_execution_time or workflow.max_execution_time,
            max_cost_budget=execution_request.max_cost_budget or workflow.max_cost_budget
        )
        
        # Create orchestrator and execute
        from ..coordinator_client import CoordinatorClient
        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)
        
        response = await orchestrator.execute_workflow(request, current_user.id)
        
        logger.info(f"Started agent execution: {response.execution_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/status", response_model=AgentExecutionStatus)
async def get_execution_status(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get execution status"""
    
    try:
        from ..services.agent_service import AIAgentOrchestrator
        from ..coordinator_client import CoordinatorClient
        
        coordinator_client = CoordinatorClient()
        orchestrator = AIAgentOrchestrator(session, coordinator_client)
        
        status = await orchestrator.get_execution_status(execution_id)
        
        # Verify user has access to this execution
        workflow = session.get(AIAgentWorkflow, status.workflow_id)
        if workflow.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions", response_model=List[AgentExecutionStatus])
async def list_executions(
    workflow_id: Optional[str] = None,
    status: Optional[AgentStatus] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """List agent executions with filtering"""
    
    try:
        from ..domain.agent import AgentExecution
        
        query = select(AgentExecution)
        
        # Filter by user's workflows
        if workflow_id:
            workflow = session.get(AIAgentWorkflow, workflow_id)
            if not workflow or workflow.owner_id != current_user.id:
                raise HTTPException(status_code=404, detail="Workflow not found")
            query = query.where(AgentExecution.workflow_id == workflow_id)
        else:
            # Get all workflows owned by user
            user_workflows = session.execute(
                select(AIAgentWorkflow.id).where(AIAgentWorkflow.owner_id == current_user.id)
            ).all()
            workflow_ids = [w.id for w in user_workflows]
            query = query.where(AgentExecution.workflow_id.in_(workflow_ids))
        
        # Filter by status
        if status:
            query = query.where(AgentExecution.status == status)
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        query = query.order_by(AgentExecution.created_at.desc())
        
        executions = session.execute(query).all()
        
        # Convert to response models
        execution_statuses = []
        for execution in executions:
            from ..services.agent_service import AIAgentOrchestrator
            from ..coordinator_client import CoordinatorClient
            
            coordinator_client = CoordinatorClient()
            orchestrator = AIAgentOrchestrator(session, coordinator_client)
            
            status = await orchestrator.get_execution_status(execution.id)
            execution_statuses.append(status)
        
        return execution_statuses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Cancel an ongoing execution"""
    
    try:
        from ..domain.agent import AgentExecution
        from ..services.agent_service import AgentStateManager
        
        # Get execution
        execution = session.get(AgentExecution, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        # Verify user has access
        workflow = session.get(AIAgentWorkflow, execution.workflow_id)
        if workflow.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if execution can be cancelled
        if execution.status not in [AgentStatus.PENDING, AgentStatus.RUNNING]:
            raise HTTPException(status_code=400, detail="Execution cannot be cancelled")
        
        # Cancel execution
        state_manager = AgentStateManager(session)
        await state_manager.update_execution_status(
            execution_id,
            status=AgentStatus.CANCELLED,
            completed_at=datetime.utcnow()
        )
        
        logger.info(f"Cancelled agent execution: {execution_id}")
        return {"message": "Execution cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/logs")
async def get_execution_logs(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get execution logs"""
    
    try:
        from ..domain.agent import AgentExecution, AgentStepExecution
        
        # Get execution
        execution = session.get(AgentExecution, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        # Verify user has access
        workflow = session.get(AIAgentWorkflow, execution.workflow_id)
        if workflow.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get step executions
        step_executions = session.execute(
            select(AgentStepExecution).where(AgentStepExecution.execution_id == execution_id)
        ).all()
        
        logs = []
        for step_exec in step_executions:
            logs.append({
                "step_id": step_exec.step_id,
                "status": step_exec.status,
                "started_at": step_exec.started_at,
                "completed_at": step_exec.completed_at,
                "execution_time": step_exec.execution_time,
                "error_message": step_exec.error_message,
                "gpu_accelerated": step_exec.gpu_accelerated,
                "memory_usage": step_exec.memory_usage
            })
        
        return {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "status": execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "total_execution_time": execution.total_execution_time,
            "step_logs": logs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Agent router is working", "timestamp": datetime.utcnow().isoformat()}


@router.post("/networks", response_model=dict, status_code=201)
async def create_agent_network(
    network_data: dict,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create a new agent network for collaborative processing"""
    
    try:
        # Validate required fields
        if not network_data.get("name"):
            raise HTTPException(status_code=400, detail="Network name is required")
        
        if not network_data.get("agents"):
            raise HTTPException(status_code=400, detail="Agent list is required")
        
        # Create network record (simplified for now)
        network_id = f"network_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        network_response = {
            "id": network_id,
            "name": network_data["name"],
            "description": network_data.get("description", ""),
            "agents": network_data["agents"],
            "coordination_strategy": network_data.get("coordination", "centralized"),
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "owner_id": current_user
        }
        
        logger.info(f"Created agent network: {network_id}")
        return network_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create agent network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/{execution_id}/receipt")
async def get_execution_receipt(
    execution_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get verifiable receipt for completed execution"""
    
    try:
        # For now, return a mock receipt since the full execution system isn't implemented
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
                    "timestamp": datetime.utcnow().isoformat()
                }
            ],
            "minted_amount": 1000,
            "recorded_at": datetime.utcnow().isoformat(),
            "verified": True,
            "block_hash": "0xmock_block_hash",
            "transaction_hash": "0xmock_tx_hash"
        }
        
        logger.info(f"Generated receipt for execution: {execution_id}")
        return receipt_data
        
    except Exception as e:
        logger.error(f"Failed to get execution receipt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
