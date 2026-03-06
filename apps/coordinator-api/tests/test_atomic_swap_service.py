import pytest
from datetime import datetime, timedelta
import secrets
import hashlib
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi import HTTPException

from app.services.atomic_swap_service import AtomicSwapService
from app.domain.atomic_swap import SwapStatus, AtomicSwapOrder
from app.schemas.atomic_swap import SwapCreateRequest, SwapActionRequest, SwapCompleteRequest

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
def swap_service(test_db, mock_contract_service):
    return AtomicSwapService(session=test_db, contract_service=mock_contract_service)

@pytest.mark.asyncio
async def test_create_swap_order(swap_service):
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="0xTokenA",
        source_amount=100.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="0xTokenB",
        target_amount=200.0,
        source_timelock_hours=48,
        target_timelock_hours=24
    )
    
    order = await swap_service.create_swap_order(request)
    
    assert order.initiator_agent_id == "agent-A"
    assert order.status == SwapStatus.CREATED
    assert order.hashlock.startswith("0x")
    assert order.secret is not None
    assert order.source_timelock > order.target_timelock

@pytest.mark.asyncio
async def test_create_swap_invalid_timelocks(swap_service):
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="0xTokenA",
        source_amount=100.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="0xTokenB",
        target_amount=200.0,
        source_timelock_hours=24,  # Invalid: not strictly greater than target
        target_timelock_hours=24
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await swap_service.create_swap_order(request)
    assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_swap_lifecycle_success(swap_service):
    # 1. Create
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="0xTokenA",
        source_amount=100.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="0xTokenB",
        target_amount=200.0
    )
    order = await swap_service.create_swap_order(request)
    swap_id = order.id
    secret = order.secret
    
    # 2. Initiate
    action_req = SwapActionRequest(tx_hash="0xTxInitiate")
    order = await swap_service.mark_initiated(swap_id, action_req)
    assert order.status == SwapStatus.INITIATED
    
    # 3. Participate
    action_req = SwapActionRequest(tx_hash="0xTxParticipate")
    order = await swap_service.mark_participating(swap_id, action_req)
    assert order.status == SwapStatus.PARTICIPATING
    
    # 4. Complete
    comp_req = SwapCompleteRequest(tx_hash="0xTxComplete", secret=secret)
    order = await swap_service.complete_swap(swap_id, comp_req)
    assert order.status == SwapStatus.COMPLETED

@pytest.mark.asyncio
async def test_complete_swap_invalid_secret(swap_service):
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="native",
        source_amount=1.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="native",
        target_amount=2.0
    )
    order = await swap_service.create_swap_order(request)
    swap_id = order.id
    
    await swap_service.mark_initiated(swap_id, SwapActionRequest(tx_hash="0x1"))
    await swap_service.mark_participating(swap_id, SwapActionRequest(tx_hash="0x2"))
    
    comp_req = SwapCompleteRequest(tx_hash="0x3", secret="wrong_secret")
    
    with pytest.raises(HTTPException) as exc_info:
        await swap_service.complete_swap(swap_id, comp_req)
    assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_refund_swap_too_early(swap_service, test_db):
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="native",
        source_amount=1.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="native",
        target_amount=2.0
    )
    order = await swap_service.create_swap_order(request)
    swap_id = order.id
    
    await swap_service.mark_initiated(swap_id, SwapActionRequest(tx_hash="0x1"))
    
    # Timelock has not expired yet
    action_req = SwapActionRequest(tx_hash="0xRefund")
    with pytest.raises(HTTPException) as exc_info:
        await swap_service.refund_swap(swap_id, action_req)
    assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_refund_swap_success(swap_service, test_db):
    request = SwapCreateRequest(
        initiator_agent_id="agent-A",
        initiator_address="0xA",
        source_chain_id=1,
        source_token="native",
        source_amount=1.0,
        participant_agent_id="agent-B",
        participant_address="0xB",
        target_chain_id=137,
        target_token="native",
        target_amount=2.0,
        source_timelock_hours=48,
        target_timelock_hours=24
    )
    order = await swap_service.create_swap_order(request)
    swap_id = order.id
    
    await swap_service.mark_initiated(swap_id, SwapActionRequest(tx_hash="0x1"))
    
    # Manually backdate the timelock to simulate expiration
    order.source_timelock = int((datetime.utcnow() - timedelta(hours=1)).timestamp())
    test_db.commit()
    
    action_req = SwapActionRequest(tx_hash="0xRefund")
    order = await swap_service.refund_swap(swap_id, action_req)
    
    assert order.status == SwapStatus.REFUNDED
