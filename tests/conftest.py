"""
Shared test configuration and fixtures for AITBC
"""

import asyncio
import pytest
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, Generator, AsyncGenerator
from unittest.mock import Mock, AsyncMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
import redis
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Import AITBC modules
from apps.coordinator_api.src.app.main import app as coordinator_app
from apps.coordinator_api.src.app.database import get_db
from apps.coordinator_api.src.app.models import Base
from apps.coordinator_api.src.app.models.multitenant import Tenant, TenantUser, TenantQuota
from apps.wallet_daemon.src.app.main import app as wallet_app
from packages.py.aitbc_crypto import sign_receipt, verify_receipt
from packages.py.aitbc_sdk import AITBCClient


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config():
    """Test configuration settings."""
    return {
        "database_url": "sqlite:///:memory:",
        "redis_url": "redis://localhost:6379/1",  # Use test DB
        "test_tenant_id": "test-tenant-123",
        "test_user_id": "test-user-456",
        "test_api_key": "test-api-key-789",
        "coordinator_url": "http://localhost:8001",
        "wallet_url": "http://localhost:8002",
        "blockchain_url": "http://localhost:8545",
    }


@pytest.fixture(scope="session")
def test_engine(test_config):
    """Create a test database engine."""
    engine = create_engine(
        test_config["database_url"],
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    
    # Begin a nested transaction
    nested = connection.begin_nested()
    
    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(session, transaction):
        """Rollback to the savepoint after each test."""
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()
    
    yield session
    
    # Rollback all changes
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_redis():
    """Create a test Redis client."""
    client = redis.Redis.from_url("redis://localhost:6379/1", decode_responses=True)
    # Clear test database
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def coordinator_client(db_session):
    """Create a test client for the coordinator API."""
    def override_get_db():
        yield db_session
    
    coordinator_app.dependency_overrides[get_db] = override_get_db
    with TestClient(coordinator_app) as client:
        yield client
    coordinator_app.dependency_overrides.clear()


@pytest.fixture
def wallet_client():
    """Create a test client for the wallet daemon."""
    with TestClient(wallet_app) as client:
        yield client


@pytest.fixture
def sample_tenant(db_session):
    """Create a sample tenant for testing."""
    tenant = Tenant(
        id="test-tenant-123",
        name="Test Tenant",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def sample_tenant_user(db_session, sample_tenant):
    """Create a sample tenant user for testing."""
    user = TenantUser(
        tenant_id=sample_tenant.id,
        user_id="test-user-456",
        role="admin",
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_tenant_quota(db_session, sample_tenant):
    """Create sample tenant quota for testing."""
    quota = TenantQuota(
        tenant_id=sample_tenant.id,
        resource_type="api_calls",
        limit=10000,
        used=0,
        period="monthly",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(quota)
    db_session.commit()
    return quota


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "job_type": "ai_inference",
        "parameters": {
            "model": "gpt-3.5-turbo",
            "prompt": "Test prompt",
            "max_tokens": 100,
        },
        "requirements": {
            "gpu_memory": "8GB",
            "compute_time": 30,
        },
    }


@pytest.fixture
def sample_receipt_data():
    """Sample receipt data for testing."""
    return {
        "job_id": "test-job-123",
        "miner_id": "test-miner-456",
        "coordinator_id": "test-coordinator-789",
        "timestamp": datetime.utcnow().isoformat(),
        "result": {
            "output": "Test output",
            "confidence": 0.95,
            "tokens_used": 50,
        },
        "signature": "test-signature",
    }


@pytest.fixture
def test_keypair():
    """Generate a test Ed25519 keypair for signing."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def signed_receipt(sample_receipt_data, test_keypair):
    """Create a signed receipt for testing."""
    private_key, public_key = test_keypair
    
    # Serialize receipt without signature
    receipt_copy = sample_receipt_data.copy()
    receipt_copy.pop("signature", None)
    receipt_json = json.dumps(receipt_copy, sort_keys=True, separators=(',', ':'))
    
    # Sign the receipt
    signature = private_key.sign(receipt_json.encode())
    
    # Add signature to receipt
    receipt_copy["signature"] = signature.hex()
    receipt_copy["public_key"] = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    
    return receipt_copy


@pytest.fixture
def aitbc_client(test_config):
    """Create an AITBC client for testing."""
    return AITBCClient(
        base_url=test_config["coordinator_url"],
        api_key=test_config["test_api_key"],
    )


@pytest.fixture
def mock_miner_service():
    """Mock miner service for testing."""
    service = AsyncMock()
    service.register_miner = AsyncMock(return_value={"miner_id": "test-miner-456"})
    service.heartbeat = AsyncMock(return_value={"status": "active"})
    service.fetch_jobs = AsyncMock(return_value=[])
    service.submit_result = AsyncMock(return_value={"job_id": "test-job-123"})
    return service


@pytest.fixture
def mock_blockchain_node():
    """Mock blockchain node for testing."""
    node = AsyncMock()
    node.get_block = AsyncMock(return_value={"number": 100, "hash": "0x123"})
    node.get_transaction = AsyncMock(return_value={"hash": "0x456", "status": "confirmed"})
    node.submit_transaction = AsyncMock(return_value={"hash": "0x789", "status": "pending"})
    node.subscribe_blocks = AsyncMock()
    node.subscribe_transactions = AsyncMock()
    return node


@pytest.fixture
def sample_gpu_service():
    """Sample GPU service definition."""
    return {
        "id": "llm-inference",
        "name": "LLM Inference Service",
        "category": "ai_ml",
        "description": "Large language model inference",
        "requirements": {
            "gpu_memory": "16GB",
            "cuda_version": "11.8",
            "driver_version": "520.61.05",
        },
        "pricing": {
            "per_hour": 0.50,
            "per_token": 0.0001,
        },
        "capabilities": [
            "text-generation",
            "chat-completion",
            "embedding",
        ],
    }


@pytest.fixture
def sample_cross_chain_data():
    """Sample cross-chain settlement data."""
    return {
        "source_chain": "ethereum",
        "target_chain": "polygon",
        "source_tx_hash": "0xabcdef123456",
        "target_address": "0x1234567890ab",
        "amount": "1000",
        "token": "USDC",
        "bridge_id": "layerzero",
        "nonce": 12345,
    }


@pytest.fixture
def confidential_transaction_data():
    """Sample confidential transaction data."""
    return {
        "sender": "0x1234567890abcdef",
        "receiver": "0xfedcba0987654321",
        "amount": 1000,
        "asset": "AITBC",
        "confidential": True,
        "ciphertext": "encrypted_data_here",
        "viewing_key": "viewing_key_here",
        "proof": "zk_proof_here",
    }


@pytest.fixture
def mock_hsm_client():
    """Mock HSM client for testing."""
    client = AsyncMock()
    client.generate_key = AsyncMock(return_value={"key_id": "test-key-123"})
    client.sign_data = AsyncMock(return_value={"signature": "test-signature"})
    client.verify_signature = AsyncMock(return_value={"valid": True})
    client.encrypt_data = AsyncMock(return_value={"ciphertext": "encrypted_data"})
    client.decrypt_data = AsyncMock(return_value={"plaintext": "decrypted_data"})
    return client


@pytest.fixture
def temp_directory():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def sample_config_file(temp_directory):
    """Create a sample configuration file."""
    config = {
        "coordinator": {
            "host": "localhost",
            "port": 8001,
            "database_url": "sqlite:///test.db",
        },
        "blockchain": {
            "host": "localhost",
            "port": 8545,
            "chain_id": 1337,
        },
        "wallet": {
            "host": "localhost",
            "port": 8002,
            "keystore_path": temp_directory,
        },
    }
    
    config_path = temp_directory / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f)
    
    return config_path


# Async fixtures

@pytest.fixture
async def async_aitbc_client(test_config):
    """Create an async AITBC client for testing."""
    client = AITBCClient(
        base_url=test_config["coordinator_url"],
        api_key=test_config["test_api_key"],
    )
    yield client
    await client.close()


@pytest.fixture
async def websocket_client():
    """Create a WebSocket client for testing."""
    import websockets
    
    uri = "ws://localhost:8546"
    async with websockets.connect(uri) as websocket:
        yield websocket


# Performance testing fixtures

@pytest.fixture
def performance_config():
    """Configuration for performance tests."""
    return {
        "concurrent_users": 100,
        "ramp_up_time": 30,  # seconds
        "test_duration": 300,  # seconds
        "think_time": 1,  # seconds
    }


# Security testing fixtures

@pytest.fixture
def malicious_payloads():
    """Collection of malicious payloads for security testing."""
    return {
        "sql_injection": "'; DROP TABLE jobs; --",
        "xss": "<script>alert('xss')</script>",
        "path_traversal": "../../../etc/passwd",
        "overflow": "A" * 10000,
        "unicode": "\ufeff\u200b\u200c\u200d",
    }


@pytest.fixture
def rate_limit_config():
    """Rate limiting configuration for testing."""
    return {
        "requests_per_minute": 60,
        "burst_size": 10,
        "window_size": 60,
    }


# Helper functions

def create_test_job(job_id: str = None, **kwargs) -> Dict[str, Any]:
    """Create a test job with default values."""
    return {
        "id": job_id or f"test-job-{datetime.utcnow().timestamp()}",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "job_type": kwargs.get("job_type", "ai_inference"),
        "parameters": kwargs.get("parameters", {}),
        "requirements": kwargs.get("requirements", {}),
        "tenant_id": kwargs.get("tenant_id", "test-tenant-123"),
    }


def create_test_receipt(job_id: str = None, **kwargs) -> Dict[str, Any]:
    """Create a test receipt with default values."""
    return {
        "id": f"receipt-{job_id or 'test'}",
        "job_id": job_id or "test-job-123",
        "miner_id": kwargs.get("miner_id", "test-miner-456"),
        "coordinator_id": kwargs.get("coordinator_id", "test-coordinator-789"),
        "timestamp": kwargs.get("timestamp", datetime.utcnow().isoformat()),
        "result": kwargs.get("result", {"output": "test"}),
        "signature": kwargs.get("signature", "test-signature"),
    }


def assert_valid_receipt(receipt: Dict[str, Any]):
    """Assert that a receipt has valid structure."""
    required_fields = ["id", "job_id", "miner_id", "coordinator_id", "timestamp", "result", "signature"]
    for field in required_fields:
        assert field in receipt, f"Receipt missing required field: {field}"
    
    # Validate timestamp format
    assert isinstance(receipt["timestamp"], str), "Timestamp should be a string"
    
    # Validate result structure
    assert isinstance(receipt["result"], dict), "Result should be a dictionary"


# Marks for different test types
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.e2e = pytest.mark.e2e
pytest.mark.performance = pytest.mark.performance
pytest.mark.security = pytest.mark.security
pytest.mark.slow = pytest.mark.slow
