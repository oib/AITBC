import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi import HTTPException

from app.services.dao_governance_service import DAOGovernanceService
from app.domain.dao_governance import ProposalState, ProposalType
from app.schemas.dao_governance import MemberCreate, ProposalCreate, VoteCreate

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
def dao_service(test_db, mock_contract_service):
    return DAOGovernanceService(
        session=test_db,
        contract_service=mock_contract_service
    )

@pytest.mark.asyncio
async def test_register_member(dao_service):
    req = MemberCreate(wallet_address="0xDAO1", staked_amount=100.0)
    member = await dao_service.register_member(req)
    
    assert member.wallet_address == "0xDAO1"
    assert member.staked_amount == 100.0
    assert member.voting_power == 100.0

@pytest.mark.asyncio
async def test_create_proposal(dao_service):
    # Register proposer
    await dao_service.register_member(MemberCreate(wallet_address="0xDAO1", staked_amount=100.0))
    
    req = ProposalCreate(
        proposer_address="0xDAO1",
        title="Fund new AI model",
        description="Allocate 1000 AITBC to train a new model",
        proposal_type=ProposalType.GRANT,
        execution_payload={"amount": "1000", "recipient_address": "0xDev1"},
        voting_period_days=7
    )
    
    proposal = await dao_service.create_proposal(req)
    assert proposal.title == "Fund new AI model"
    assert proposal.status == ProposalState.ACTIVE
    assert proposal.proposal_type == ProposalType.GRANT

@pytest.mark.asyncio
async def test_cast_vote(dao_service):
    await dao_service.register_member(MemberCreate(wallet_address="0xDAO1", staked_amount=100.0))
    await dao_service.register_member(MemberCreate(wallet_address="0xDAO2", staked_amount=50.0))
    
    prop_req = ProposalCreate(
        proposer_address="0xDAO1",
        title="Test Proposal",
        description="Testing voting"
    )
    proposal = await dao_service.create_proposal(prop_req)
    
    # Cast vote
    vote_req = VoteCreate(
        member_address="0xDAO2",
        proposal_id=proposal.id,
        support=True
    )
    vote = await dao_service.cast_vote(vote_req)
    
    assert vote.support is True
    assert vote.weight == 50.0
    
    dao_service.session.refresh(proposal)
    assert proposal.for_votes == 50.0

@pytest.mark.asyncio
async def test_execute_proposal_success(dao_service, test_db):
    await dao_service.register_member(MemberCreate(wallet_address="0xDAO1", staked_amount=100.0))
    
    prop_req = ProposalCreate(
        proposer_address="0xDAO1",
        title="Test Grant",
        description="Testing grant execution",
        proposal_type=ProposalType.GRANT,
        execution_payload={"amount": "500", "recipient_address": "0xDev"}
    )
    proposal = await dao_service.create_proposal(prop_req)
    
    await dao_service.cast_vote(VoteCreate(
        member_address="0xDAO1",
        proposal_id=proposal.id,
        support=True
    ))
    
    # Fast forward time to end of voting period
    proposal.end_time = datetime.utcnow() - timedelta(seconds=1)
    test_db.commit()
    
    exec_proposal = await dao_service.execute_proposal(proposal.id)
    
    assert exec_proposal.status == ProposalState.EXECUTED
    
    # Verify treasury allocation was created
    from app.domain.dao_governance import TreasuryAllocation
    from sqlmodel import select
    allocation = test_db.exec(select(TreasuryAllocation).where(TreasuryAllocation.proposal_id == proposal.id)).first()
    
    assert allocation is not None
    assert allocation.amount == 500.0
    assert allocation.recipient_address == "0xDev"
