# Swarm & Network Endpoints Implementation Specification

## Overview

This document provides detailed specifications for implementing the missing Swarm & Network endpoints in the AITBC FastAPI backend. These endpoints are required to support the CLI commands that are currently returning 404 errors.

## Current Status

### ✅ Missing Endpoints (404 Errors) - RESOLVED
- **Agent Network**: `/api/v1/agents/networks/*` endpoints - ✅ **IMPLEMENTED** (March 5, 2026)
- **Agent Receipt**: `/api/v1/agents/executions/{execution_id}/receipt` endpoint - ✅ **IMPLEMENTED** (March 5, 2026)
- **Swarm Operations**: `/swarm/*` endpoints

### ✅ CLI Commands Ready
- All CLI commands are implemented and working
- Error handling is robust
- Authentication is properly configured

---

## 1. Agent Network Endpoints

### 1.1 Create Agent Network
**Endpoint**: `POST /api/v1/agents/networks`
**CLI Command**: `aitbc agent network create`

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..storage import SessionDep
from ..deps import require_admin_key

class AgentNetworkCreate(BaseModel):
    name: str
    description: Optional[str] = None
    agents: List[str]  # List of agent IDs
    coordination_strategy: str = "round-robin"

class AgentNetworkView(BaseModel):
    id: str
    name: str
    description: Optional[str]
    agents: List[str]
    coordination_strategy: str
    status: str
    created_at: str
    owner_id: str

@router.post("/networks", response_model=AgentNetworkView, status_code=201)
async def create_agent_network(
    network_data: AgentNetworkCreate,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> AgentNetworkView:
    """Create a new agent network for collaborative processing"""
    
    try:
        # Validate agents exist
        for agent_id in network_data.agents:
            agent = session.exec(select(AIAgentWorkflow).where(
                AIAgentWorkflow.id == agent_id
            )).first()
            if not agent:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Agent {agent_id} not found"
                )
        
        # Create network
        network = AgentNetwork(
            name=network_data.name,
            description=network_data.description,
            agents=network_data.agents,
            coordination_strategy=network_data.coordination_strategy,
            owner_id=current_user,
            status="active"
        )
        
        session.add(network)
        session.commit()
        session.refresh(network)
        
        return AgentNetworkView.from_orm(network)
        
    except Exception as e:
        logger.error(f"Failed to create agent network: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 1.2 Execute Network Task
**Endpoint**: `POST /api/v1/agents/networks/{network_id}/execute`
**CLI Command**: `aitbc agent network execute`

```python
class NetworkTaskExecute(BaseModel):
    task: dict  # Task definition
    priority: str = "normal"

class NetworkExecutionView(BaseModel):
    execution_id: str
    network_id: str
    task: dict
    status: str
    started_at: str
    results: Optional[dict] = None

@router.post("/networks/{network_id}/execute", response_model=NetworkExecutionView)
async def execute_network_task(
    network_id: str,
    task_data: NetworkTaskExecute,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> NetworkExecutionView:
    """Execute a collaborative task on the agent network"""
    
    try:
        # Verify network exists and user has permission
        network = session.exec(select(AgentNetwork).where(
            AgentNetwork.id == network_id,
            AgentNetwork.owner_id == current_user
        )).first()
        
        if not network:
            raise HTTPException(
                status_code=404,
                detail=f"Agent network {network_id} not found"
            )
        
        # Create execution record
        execution = AgentNetworkExecution(
            network_id=network_id,
            task=task_data.task,
            priority=task_data.priority,
            status="queued"
        )
        
        session.add(execution)
        session.commit()
        session.refresh(execution)
        
        # TODO: Implement actual task distribution logic
        # This would involve:
        # 1. Task decomposition
        # 2. Agent assignment
        # 3. Result aggregation
        
        return NetworkExecutionView.from_orm(execution)
        
    except Exception as e:
        logger.error(f"Failed to execute network task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 1.3 Optimize Network
**Endpoint**: `GET /api/v1/agents/networks/{network_id}/optimize`
**CLI Command**: `aitbc agent network optimize`

```python
class NetworkOptimizationView(BaseModel):
    network_id: str
    optimization_type: str
    recommendations: List[dict]
    performance_metrics: dict
    optimized_at: str

@router.get("/networks/{network_id}/optimize", response_model=NetworkOptimizationView)
async def optimize_agent_network(
    network_id: str,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> NetworkOptimizationView:
    """Get optimization recommendations for the agent network"""
    
    try:
        # Verify network exists
        network = session.exec(select(AgentNetwork).where(
            AgentNetwork.id == network_id,
            AgentNetwork.owner_id == current_user
        )).first()
        
        if not network:
            raise HTTPException(
                status_code=404,
                detail=f"Agent network {network_id} not found"
            )
        
        # TODO: Implement optimization analysis
        # This would analyze:
        # 1. Agent performance metrics
        # 2. Task distribution efficiency
        # 3. Resource utilization
        # 4. Coordination strategy effectiveness
        
        optimization = NetworkOptimizationView(
            network_id=network_id,
            optimization_type="performance",
            recommendations=[
                {
                    "type": "load_balancing",
                    "description": "Distribute tasks more evenly across agents",
                    "impact": "high"
                }
            ],
            performance_metrics={
                "avg_task_time": 2.5,
                "success_rate": 0.95,
                "resource_utilization": 0.78
            },
            optimized_at=datetime.utcnow().isoformat()
        )
        
        return optimization
        
    except Exception as e:
        logger.error(f"Failed to optimize network: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 1.4 Get Network Status
**Endpoint**: `GET /api/v1/agents/networks/{network_id}/status`
**CLI Command**: `aitbc agent network status`

```python
class NetworkStatusView(BaseModel):
    network_id: str
    name: str
    status: str
    agent_count: int
    active_tasks: int
    total_executions: int
    performance_metrics: dict
    last_activity: str

@router.get("/networks/{network_id}/status", response_model=NetworkStatusView)
async def get_network_status(
    network_id: str,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> NetworkStatusView:
    """Get current status of the agent network"""
    
    try:
        # Verify network exists
        network = session.exec(select(AgentNetwork).where(
            AgentNetwork.id == network_id,
            AgentNetwork.owner_id == current_user
        )).first()
        
        if not network:
            raise HTTPException(
                status_code=404,
                detail=f"Agent network {network_id} not found"
            )
        
        # Get execution statistics
        executions = session.exec(select(AgentNetworkExecution).where(
            AgentNetworkExecution.network_id == network_id
        )).all()
        
        active_tasks = len([e for e in executions if e.status == "running"])
        
        status = NetworkStatusView(
            network_id=network_id,
            name=network.name,
            status=network.status,
            agent_count=len(network.agents),
            active_tasks=active_tasks,
            total_executions=len(executions),
            performance_metrics={
                "avg_execution_time": 2.1,
                "success_rate": 0.94,
                "throughput": 15.5
            },
            last_activity=network.updated_at.isoformat()
        )
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to get network status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 2. Swarm Endpoints

### 2.1 Create Swarm Router
**File**: `/apps/coordinator-api/src/app/routers/swarm_router.py`

```python
"""
Swarm Intelligence API Router
Provides REST API endpoints for swarm coordination and collective optimization
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..storage import SessionDep
from ..deps import require_admin_key
from ..storage.db import get_session
from sqlmodel import Session, select
from aitbc.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/swarm", tags=["Swarm Intelligence"])

# Pydantic Models
class SwarmJoinRequest(BaseModel):
    role: str  # load-balancer, resource-optimizer, task-coordinator, monitor
    capability: str
    region: Optional[str] = None
    priority: str = "normal"

class SwarmJoinView(BaseModel):
    swarm_id: str
    member_id: str
    role: str
    status: str
    joined_at: str

class SwarmMember(BaseModel):
    member_id: str
    role: str
    capability: str
    region: Optional[str]
    priority: str
    status: str
    joined_at: str

class SwarmListView(BaseModel):
    swarms: List[Dict[str, Any]]
    total_count: int

class SwarmStatusView(BaseModel):
    swarm_id: str
    member_count: int
    active_tasks: int
    coordination_status: str
    performance_metrics: dict

class SwarmCoordinateRequest(BaseModel):
    task_id: str
    strategy: str = "map-reduce"
    parameters: dict = {}

class SwarmConsensusRequest(BaseModel):
    task_id: str
    consensus_algorithm: str = "majority-vote"
    timeout_seconds: int = 300
```

### 2.2 Join Swarm
**Endpoint**: `POST /swarm/join`
**CLI Command**: `aitbc swarm join`

```python
@router.post("/join", response_model=SwarmJoinView, status_code=201)
async def join_swarm(
    swarm_data: SwarmJoinRequest,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> SwarmJoinView:
    """Join an agent swarm for collective optimization"""
    
    try:
        # Validate role
        valid_roles = ["load-balancer", "resource-optimizer", "task-coordinator", "monitor"]
        if swarm_data.role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {valid_roles}"
            )
        
        # Create swarm member
        member = SwarmMember(
            swarm_id=f"swarm_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            member_id=f"member_{current_user}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            role=swarm_data.role,
            capability=swarm_data.capability,
            region=swarm_data.region,
            priority=swarm_data.priority,
            status="active",
            owner_id=current_user
        )
        
        session.add(member)
        session.commit()
        session.refresh(member)
        
        return SwarmJoinView(
            swarm_id=member.swarm_id,
            member_id=member.member_id,
            role=member.role,
            status=member.status,
            joined_at=member.created_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to join swarm: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.3 Leave Swarm
**Endpoint**: `POST /swarm/leave`
**CLI Command**: `aitbc swarm leave`

```python
class SwarmLeaveRequest(BaseModel):
    swarm_id: str
    member_id: Optional[str] = None  # If not provided, leave all swarms for user

class SwarmLeaveView(BaseModel):
    swarm_id: str
    member_id: str
    left_at: str
    status: str

@router.post("/leave", response_model=SwarmLeaveView)
async def leave_swarm(
    leave_data: SwarmLeaveRequest,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> SwarmLeaveView:
    """Leave an agent swarm"""
    
    try:
        # Find member to remove
        if leave_data.member_id:
            member = session.exec(select(SwarmMember).where(
                SwarmMember.member_id == leave_data.member_id,
                SwarmMember.owner_id == current_user
            )).first()
        else:
            # Find any member for this user in the swarm
            member = session.exec(select(SwarmMember).where(
                SwarmMember.swarm_id == leave_data.swarm_id,
                SwarmMember.owner_id == current_user
            )).first()
        
        if not member:
            raise HTTPException(
                status_code=404,
                detail="Swarm member not found"
            )
        
        # Update member status
        member.status = "left"
        member.left_at = datetime.utcnow()
        session.commit()
        
        return SwarmLeaveView(
            swarm_id=member.swarm_id,
            member_id=member.member_id,
            left_at=member.left_at.isoformat(),
            status="left"
        )
        
    except Exception as e:
        logger.error(f"Failed to leave swarm: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.4 List Active Swarms
**Endpoint**: `GET /swarm/list`
**CLI Command**: `aitbc swarm list`

```python
@router.get("/list", response_model=SwarmListView)
async def list_active_swarms(
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> SwarmListView:
    """List all active swarms"""
    
    try:
        # Get all active swarm members for this user
        members = session.exec(select(SwarmMember).where(
            SwarmMember.owner_id == current_user,
            SwarmMember.status == "active"
        )).all()
        
        # Group by swarm_id
        swarms = {}
        for member in members:
            if member.swarm_id not in swarms:
                swarms[member.swarm_id] = {
                    "swarm_id": member.swarm_id,
                    "members": [],
                    "created_at": member.created_at.isoformat(),
                    "coordination_status": "active"
                }
            swarms[member.swarm_id]["members"].append({
                "member_id": member.member_id,
                "role": member.role,
                "capability": member.capability,
                "region": member.region,
                "priority": member.priority
            })
        
        return SwarmListView(
            swarms=list(swarms.values()),
            total_count=len(swarms)
        )
        
    except Exception as e:
        logger.error(f"Failed to list swarms: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.5 Get Swarm Status
**Endpoint**: `GET /swarm/status`
**CLI Command**: `aitbc swarm status`

```python
@router.get("/status", response_model=List[SwarmStatusView])
async def get_swarm_status(
    swarm_id: Optional[str] = None,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> List[SwarmStatusView]:
    """Get status of swarm(s)"""
    
    try:
        # Build query
        query = select(SwarmMember).where(SwarmMember.owner_id == current_user)
        if swarm_id:
            query = query.where(SwarmMember.swarm_id == swarm_id)
        
        members = session.exec(query).all()
        
        # Group by swarm and calculate status
        swarm_status = {}
        for member in members:
            if member.swarm_id not in swarm_status:
                swarm_status[member.swarm_id] = {
                    "swarm_id": member.swarm_id,
                    "member_count": 0,
                    "active_tasks": 0,
                    "coordination_status": "active"
                }
            swarm_status[member.swarm_id]["member_count"] += 1
        
        # Convert to response format
        status_list = []
        for swarm_id, status_data in swarm_status.items():
            status_view = SwarmStatusView(
                swarm_id=swarm_id,
                member_count=status_data["member_count"],
                active_tasks=status_data["active_tasks"],
                coordination_status=status_data["coordination_status"],
                performance_metrics={
                    "avg_task_time": 1.8,
                    "success_rate": 0.96,
                    "coordination_efficiency": 0.89
                }
            )
            status_list.append(status_view)
        
        return status_list
        
    except Exception as e:
        logger.error(f"Failed to get swarm status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.6 Coordinate Swarm Execution
**Endpoint**: `POST /swarm/coordinate`
**CLI Command**: `aitbc swarm coordinate`

```python
class SwarmCoordinateView(BaseModel):
    task_id: str
    swarm_id: str
    coordination_strategy: str
    status: str
    assigned_members: List[str]
    started_at: str

@router.post("/coordinate", response_model=SwarmCoordinateView)
async def coordinate_swarm_execution(
    coord_data: SwarmCoordinateRequest,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> SwarmCoordinateView:
    """Coordinate swarm task execution"""
    
    try:
        # Find available swarm members
        members = session.exec(select(SwarmMember).where(
            SwarmMember.owner_id == current_user,
            SwarmMember.status == "active"
        )).all()
        
        if not members:
            raise HTTPException(
                status_code=404,
                detail="No active swarm members found"
            )
        
        # Select swarm (use first available for now)
        swarm_id = members[0].swarm_id
        
        # Create coordination record
        coordination = SwarmCoordination(
            task_id=coord_data.task_id,
            swarm_id=swarm_id,
            strategy=coord_data.strategy,
            parameters=coord_data.parameters,
            status="coordinating",
            assigned_members=[m.member_id for m in members[:3]]  # Assign first 3 members
        )
        
        session.add(coordination)
        session.commit()
        session.refresh(coordination)
        
        # TODO: Implement actual coordination logic
        # This would involve:
        # 1. Task decomposition
        # 2. Member selection based on capabilities
        # 3. Task assignment
        # 4. Progress monitoring
        
        return SwarmCoordinateView(
            task_id=coordination.task_id,
            swarm_id=coordination.swarm_id,
            coordination_strategy=coordination.strategy,
            status=coordination.status,
            assigned_members=coordination.assigned_members,
            started_at=coordination.created_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to coordinate swarm: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 2.7 Achieve Swarm Consensus
**Endpoint**: `POST /swarm/consensus`
**CLI Command**: `aitbc swarm consensus`

```python
class SwarmConsensusView(BaseModel):
    task_id: str
    swarm_id: str
    consensus_algorithm: str
    result: dict
    confidence_score: float
    participating_members: List[str]
    consensus_reached_at: str

@router.post("/consensus", response_model=SwarmConsensusView)
async def achieve_swarm_consensus(
    consensus_data: SwarmConsensusRequest,
    session: Session = Depends(SessionDep),
    current_user: str = Depends(require_admin_key())
) -> SwarmConsensusView:
    """Achieve consensus on swarm task result"""
    
    try:
        # Find task coordination
        coordination = session.exec(select(SwarmCoordination).where(
            SwarmCoordination.task_id == consensus_data.task_id
        )).first()
        
        if not coordination:
            raise HTTPException(
                status_code=404,
                detail=f"Task {consensus_data.task_id} not found"
            )
        
        # TODO: Implement actual consensus algorithm
        # This would involve:
        # 1. Collect results from all participating members
        # 2. Apply consensus algorithm (majority vote, weighted, etc.)
        # 3. Calculate confidence score
        # 4. Return final result
        
        consensus_result = SwarmConsensusView(
            task_id=consensus_data.task_id,
            swarm_id=coordination.swarm_id,
            consensus_algorithm=consensus_data.consensus_algorithm,
            result={
                "final_answer": "Consensus result here",
                "votes": {"option_a": 3, "option_b": 1}
            },
            confidence_score=0.85,
            participating_members=coordination.assigned_members,
            consensus_reached_at=datetime.utcnow().isoformat()
        )
        
        return consensus_result
        
    except Exception as e:
        logger.error(f"Failed to achieve consensus: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 3. Database Schema Updates

### 3.1 Agent Network Tables

```sql
-- Agent Networks Table
CREATE TABLE agent_networks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    agents JSONB NOT NULL,
    coordination_strategy VARCHAR(50) DEFAULT 'round-robin',
    status VARCHAR(20) DEFAULT 'active',
    owner_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Agent Network Executions Table
CREATE TABLE agent_network_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    network_id UUID NOT NULL REFERENCES agent_networks(id),
    task JSONB NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) DEFAULT 'queued',
    results JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.2 Swarm Tables

```sql
-- Swarm Members Table
CREATE TABLE swarm_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    swarm_id VARCHAR(255) NOT NULL,
    member_id VARCHAR(255) NOT NULL UNIQUE,
    role VARCHAR(50) NOT NULL,
    capability VARCHAR(100) NOT NULL,
    region VARCHAR(50),
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) DEFAULT 'active',
    owner_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    left_at TIMESTAMP
);

-- Swarm Coordination Table
CREATE TABLE swarm_coordination (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(255) NOT NULL,
    swarm_id VARCHAR(255) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'coordinating',
    assigned_members JSONB,
    results JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 4. Integration Steps

### 4.1 Update Main Application
Add to `/apps/coordinator-api/src/app/main.py`:

```python
from .routers import swarm_router

# Add this to the router imports section
app.include_router(swarm_router.router, prefix="/v1")
```

### 4.2 Update Agent Router
Add network endpoints to existing `/apps/coordinator-api/src/app/routers/agent_router.py`:

```python
# Add these endpoints to the agent router
@router.post("/networks", response_model=AgentNetworkView, status_code=201)
async def create_agent_network(...):
    # Implementation from section 1.1

@router.post("/networks/{network_id}/execute", response_model=NetworkExecutionView)
async def execute_network_task(...):
    # Implementation from section 1.2

@router.get("/networks/{network_id}/optimize", response_model=NetworkOptimizationView)
async def optimize_agent_network(...):
    # Implementation from section 1.3

@router.get("/networks/{network_id}/status", response_model=NetworkStatusView)
async def get_network_status(...):
    # Implementation from section 1.4
```

### 4.3 Create Domain Models
Add to `/apps/coordinator-api/src/app/domain/`:

```python
# agent_network.py
class AgentNetwork(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    description: Optional[str]
    agents: List[str] = Field(sa_column=Column(JSON))
    coordination_strategy: str = "round-robin"
    status: str = "active"
    owner_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# swarm.py
class SwarmMember(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    swarm_id: str
    member_id: str
    role: str
    capability: str
    region: Optional[str]
    priority: str = "normal"
    status: str = "active"
    owner_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    left_at: Optional[datetime]
```

---

## 5. Testing Strategy

### 5.1 Unit Tests
```python
# Test agent network creation
def test_create_agent_network():
    # Test valid network creation
    # Test agent validation
    # Test permission checking

# Test swarm operations
def test_swarm_join_leave():
    # Test joining swarm
    # Test leaving swarm
    # Test status updates
```

### 5.2 Integration Tests
```python
# Test end-to-end CLI integration
def test_cli_agent_network_create():
    # Call CLI command
    # Verify network created in database
    # Verify response format

def test_cli_swarm_operations():
    # Test swarm join via CLI
    # Test swarm status via CLI
    # Test swarm leave via CLI
```

### 5.3 CLI Testing Commands
```bash
# Test agent network commands
aitbc agent network create --name "test-network" --agents "agent1,agent2"
aitbc agent network execute <network_id> --task task.json
aitbc agent network optimize <network_id>
aitbc agent network status <network_id>

# Test swarm commands
aitbc swarm join --role load-balancer --capability "gpu-processing"
aitbc swarm list
aitbc swarm status
aitbc swarm coordinate --task-id "task123" --strategy "map-reduce"
aitbc swarm consensus --task-id "task123"
aitbc swarm leave --swarm-id "swarm123"
```

---

## 6. Success Criteria

### 6.1 Functional Requirements
- [ ] All CLI commands return 200/201 instead of 404
- [ ] Agent networks can be created and managed
- [ ] Swarm members can join/leave swarms
- [ ] Network tasks can be executed
- [ ] Swarm coordination works end-to-end

### 6.2 Performance Requirements
- [ ] Network creation < 500ms
- [ ] Swarm join/leave < 200ms
- [ ] Status queries < 100ms
- [ ] Support 100+ concurrent swarm members

### 6.3 Security Requirements
- [ ] Proper authentication for all endpoints
- [ ] Authorization checks (users can only access their own resources)
- [ ] Input validation and sanitization
- [ ] Rate limiting where appropriate

---

## 7. Next Steps

1. **Implement Database Schema**: Create the required tables
2. **Create Swarm Router**: Implement all swarm endpoints
3. **Update Agent Router**: Add network endpoints to existing router
4. **Add Domain Models**: Create Pydantic/SQLModel classes
5. **Update Main App**: Include new router in FastAPI app
6. **Write Tests**: Unit and integration tests
7. **CLI Testing**: Verify all CLI commands work
8. **Documentation**: Update API documentation

---

**Priority**: High - These endpoints are blocking core CLI functionality
**Estimated Effort**: 2-3 weeks for full implementation
**Dependencies**: Database access, existing authentication system
