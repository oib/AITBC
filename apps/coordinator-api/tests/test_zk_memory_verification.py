import pytest
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.services.zk_memory_verification import ZKMemoryVerificationService
from app.domain.decentralized_memory import AgentMemoryNode, MemoryType

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
def zk_service(test_db, mock_contract_service):
    return ZKMemoryVerificationService(
        session=test_db,
        contract_service=mock_contract_service
    )

@pytest.mark.asyncio
async def test_generate_memory_proof(zk_service, test_db):
    node = AgentMemoryNode(
        agent_id="agent-zk",
        memory_type=MemoryType.VECTOR_DB
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    
    raw_data = b"secret_vector_data"
    
    proof_payload, proof_hash = await zk_service.generate_memory_proof(node.id, raw_data)
    
    assert proof_payload is not None
    assert proof_hash.startswith("0x")
    assert "groth16" in proof_payload

@pytest.mark.asyncio
async def test_verify_retrieved_memory_success(zk_service, test_db):
    node = AgentMemoryNode(
        agent_id="agent-zk",
        memory_type=MemoryType.VECTOR_DB
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    
    raw_data = b"secret_vector_data"
    proof_payload, proof_hash = await zk_service.generate_memory_proof(node.id, raw_data)
    
    # Simulate anchoring
    node.zk_proof_hash = proof_hash
    test_db.commit()
    
    # Verify
    is_valid = await zk_service.verify_retrieved_memory(node.id, raw_data, proof_payload)
    assert is_valid is True

@pytest.mark.asyncio
async def test_verify_retrieved_memory_tampered_data(zk_service, test_db):
    node = AgentMemoryNode(
        agent_id="agent-zk",
        memory_type=MemoryType.VECTOR_DB
    )
    test_db.add(node)
    test_db.commit()
    test_db.refresh(node)
    
    raw_data = b"secret_vector_data"
    proof_payload, proof_hash = await zk_service.generate_memory_proof(node.id, raw_data)
    
    node.zk_proof_hash = proof_hash
    test_db.commit()
    
    # Tamper with data
    tampered_data = b"secret_vector_data_modified"
    
    is_valid = await zk_service.verify_retrieved_memory(node.id, tampered_data, proof_payload)
    assert is_valid is False
