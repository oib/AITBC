import pytest
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi import HTTPException

from app.services.ipfs_storage_adapter import IPFSAdapterService
from app.domain.decentralized_memory import MemoryType, StorageStatus
from app.schemas.decentralized_memory import MemoryNodeCreate

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
def storage_service(test_db, mock_contract_service):
    return IPFSAdapterService(
        session=test_db, 
        contract_service=mock_contract_service,
        pinning_service_token="mock_token"
    )

@pytest.mark.asyncio
async def test_store_memory(storage_service):
    request = MemoryNodeCreate(
        agent_id="agent-007",
        memory_type=MemoryType.VECTOR_DB,
        tags=["training", "batch1"]
    )
    
    raw_data = b"mock_vector_embeddings_data"
    
    node = await storage_service.store_memory(request, raw_data, zk_proof_hash="0xabc123")
    
    assert node.agent_id == "agent-007"
    assert node.memory_type == MemoryType.VECTOR_DB
    assert node.cid is not None
    assert node.cid.startswith("bafy")
    assert node.size_bytes == len(raw_data)
    assert node.status == StorageStatus.PINNED
    assert node.zk_proof_hash == "0xabc123"

@pytest.mark.asyncio
async def test_get_memory_nodes(storage_service):
    # Store multiple
    await storage_service.store_memory(
        MemoryNodeCreate(agent_id="agent-007", memory_type=MemoryType.VECTOR_DB, tags=["v1"]), 
        b"data1"
    )
    await storage_service.store_memory(
        MemoryNodeCreate(agent_id="agent-007", memory_type=MemoryType.KNOWLEDGE_GRAPH, tags=["v1"]), 
        b"data2"
    )
    await storage_service.store_memory(
        MemoryNodeCreate(agent_id="agent-008", memory_type=MemoryType.VECTOR_DB), 
        b"data3"
    )
    
    # Get all for agent-007
    nodes = await storage_service.get_memory_nodes("agent-007")
    assert len(nodes) == 2
    
    # Filter by type
    nodes_kg = await storage_service.get_memory_nodes("agent-007", memory_type=MemoryType.KNOWLEDGE_GRAPH)
    assert len(nodes_kg) == 1
    assert nodes_kg[0].memory_type == MemoryType.KNOWLEDGE_GRAPH
    
    # Filter by tag
    nodes_tag = await storage_service.get_memory_nodes("agent-007", tags=["v1"])
    assert len(nodes_tag) == 2

@pytest.mark.asyncio
async def test_anchor_to_blockchain(storage_service):
    node = await storage_service.store_memory(
        MemoryNodeCreate(agent_id="agent-007", memory_type=MemoryType.VECTOR_DB), 
        b"data1"
    )
    
    assert node.anchor_tx_hash is None
    
    anchored_node = await storage_service.anchor_to_blockchain(node.id)
    
    assert anchored_node.status == StorageStatus.ANCHORED
    assert anchored_node.anchor_tx_hash is not None

@pytest.mark.asyncio
async def test_retrieve_memory(storage_service):
    node = await storage_service.store_memory(
        MemoryNodeCreate(agent_id="agent-007", memory_type=MemoryType.VECTOR_DB), 
        b"data1"
    )
    
    data = await storage_service.retrieve_memory(node.id)
    assert isinstance(data, bytes)
    assert b"mock" in data
