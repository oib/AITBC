import pytest
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi import HTTPException

from app.services.federated_learning import FederatedLearningService
from app.domain.federated_learning import TrainingStatus, ParticipantStatus
from app.schemas.federated_learning import FederatedSessionCreate, JoinSessionRequest, SubmitUpdateRequest

@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

@pytest.fixture
def mock_contract_service():
    return AsyncMock()

@pytest.fixture
def fl_service(test_db, mock_contract_service):
    return FederatedLearningService(
        session=test_db, 
        contract_service=mock_contract_service
    )

@pytest.mark.asyncio
async def test_create_session(fl_service):
    req = FederatedSessionCreate(
        initiator_agent_id="agent-admin",
        task_description="Train LLM on financial data",
        model_architecture_cid="bafy_arch_123",
        target_participants=2,
        total_rounds=2,
        min_participants_per_round=2
    )
    
    session = await fl_service.create_session(req)
    assert session.status == TrainingStatus.GATHERING_PARTICIPANTS
    assert session.initiator_agent_id == "agent-admin"

@pytest.mark.asyncio
async def test_join_session_and_start(fl_service):
    req = FederatedSessionCreate(
        initiator_agent_id="agent-admin",
        task_description="Train LLM on financial data",
        model_architecture_cid="bafy_arch_123",
        target_participants=2,
        total_rounds=2,
        min_participants_per_round=2
    )
    session = await fl_service.create_session(req)
    
    # Agent 1 joins
    p1 = await fl_service.join_session(
        session.id, 
        JoinSessionRequest(agent_id="agent-1", compute_power_committed=10.0)
    )
    assert p1.status == ParticipantStatus.JOINED
    assert session.status == TrainingStatus.GATHERING_PARTICIPANTS
    
    # Agent 2 joins, triggers start
    p2 = await fl_service.join_session(
        session.id, 
        JoinSessionRequest(agent_id="agent-2", compute_power_committed=15.0)
    )
    
    # Needs refresh
    fl_service.session.refresh(session)
    
    assert session.status == TrainingStatus.TRAINING
    assert session.current_round == 1
    assert len(session.rounds) == 1
    assert session.rounds[0].status == "active"

@pytest.mark.asyncio
async def test_submit_updates_and_aggregate(fl_service):
    # Setup
    req = FederatedSessionCreate(
        initiator_agent_id="agent-admin",
        task_description="Train LLM on financial data",
        model_architecture_cid="bafy_arch_123",
        target_participants=2,
        total_rounds=1, # Only 1 round for quick test
        min_participants_per_round=2
    )
    session = await fl_service.create_session(req)
    await fl_service.join_session(session.id, JoinSessionRequest(agent_id="agent-1", compute_power_committed=10.0))
    await fl_service.join_session(session.id, JoinSessionRequest(agent_id="agent-2", compute_power_committed=15.0))
    
    fl_service.session.refresh(session)
    round1 = session.rounds[0]
    
    # Agent 1 submits
    u1 = await fl_service.submit_local_update(
        session.id, 
        round1.id, 
        SubmitUpdateRequest(agent_id="agent-1", weights_cid="bafy_w1", data_samples_count=1000)
    )
    assert u1.weights_cid == "bafy_w1"
    
    fl_service.session.refresh(session)
    fl_service.session.refresh(round1)
    
    # Not aggregated yet
    assert round1.status == "active"
    
    # Agent 2 submits, triggers aggregation and completion since total_rounds=1
    u2 = await fl_service.submit_local_update(
        session.id, 
        round1.id, 
        SubmitUpdateRequest(agent_id="agent-2", weights_cid="bafy_w2", data_samples_count=1500)
    )
    
    fl_service.session.refresh(session)
    fl_service.session.refresh(round1)
    
    assert round1.status == "completed"
    assert session.status == TrainingStatus.COMPLETED
    assert session.global_model_cid is not None
    assert session.global_model_cid.startswith("bafy_aggregated_")
