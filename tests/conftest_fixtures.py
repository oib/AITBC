"""
Comprehensive test fixtures for AITBC testing
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Generator
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import all necessary modules
from apps.coordinator_api.src.app.main import app as coordinator_app
from apps.wallet_daemon.src.app.main import app as wallet_app
from apps.blockchain_node.src.aitbc_chain.node import BlockchainNode


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def coordinator_client():
    """Create a test client for coordinator API"""
    return TestClient(coordinator_app)


@pytest.fixture
def wallet_client():
    """Create a test client for wallet daemon"""
    return TestClient(wallet_app)


@pytest.fixture
def blockchain_client():
    """Create a test client for blockchain node"""
    node = BlockchainNode()
    return TestClient(node.app)


@pytest.fixture
def marketplace_client():
    """Create a test client for marketplace"""
    from apps.marketplace.src.app.main import app as marketplace_app
    return TestClient(marketplace_app)


@pytest.fixture
def sample_tenant():
    """Create a sample tenant for testing"""
    return {
        "id": "tenant-123",
        "name": "Test Tenant",
        "created_at": datetime.utcnow(),
        "status": "active"
    }


@pytest.fixture
def sample_user():
    """Create a sample user for testing"""
    return {
        "id": "user-123",
        "email": "test@example.com",
        "tenant_id": "tenant-123",
        "role": "user",
        "created_at": datetime.utcnow()
    }


@pytest.fixture
def sample_wallet_data():
    """Sample wallet creation data"""
    return {
        "name": "Test Wallet",
        "type": "hd",
        "currency": "AITBC"
    }


@pytest.fixture
def sample_wallet():
    """Sample wallet object"""
    return {
        "id": "wallet-123",
        "address": "0x1234567890abcdef1234567890abcdef12345678",
        "user_id": "user-123",
        "balance": "1000.0",
        "status": "active",
        "created_at": datetime.utcnow()
    }


@pytest.fixture
def sample_job_data():
    """Sample job creation data"""
    return {
        "job_type": "ai_inference",
        "parameters": {
            "model": "gpt-4",
            "prompt": "Test prompt",
            "max_tokens": 100,
            "temperature": 0.7
        },
        "priority": "normal",
        "timeout": 300
    }


@pytest.fixture
def sample_job():
    """Sample job object"""
    return {
        "id": "job-123",
        "job_type": "ai_inference",
        "status": "pending",
        "tenant_id": "tenant-123",
        "created_at": datetime.utcnow(),
        "parameters": {
            "model": "gpt-4",
            "prompt": "Test prompt"
        }
    }


@pytest.fixture
def sample_transaction():
    """Sample transaction object"""
    return {
        "hash": "0x1234567890abcdef",
        "from": "0xsender1234567890",
        "to": "0xreceiver1234567890",
        "value": "1000",
        "gas": "21000",
        "gas_price": "20",
        "nonce": 1,
        "status": "pending"
    }


@pytest.fixture
def sample_block():
    """Sample block object"""
    return {
        "number": 100,
        "hash": "0xblock1234567890",
        "parent_hash": "0xparent0987654321",
        "timestamp": datetime.utcnow(),
        "transactions": [],
        "validator": "0xvalidator123"
    }


@pytest.fixture
def sample_account():
    """Sample account object"""
    return {
        "address": "0xaccount1234567890",
        "balance": "1000000",
        "nonce": 25,
        "code_hash": "0xempty"
    }


@pytest.fixture
def signed_receipt():
    """Sample signed receipt"""
    return {
        "job_id": "job-123",
        "hash": "0xreceipt123456",
        "signature": "sig789012345",
        "miner_id": "miner-123",
        "timestamp": datetime.utcnow().isoformat()
    }


@pytest.fixture
def sample_tenant_quota():
    """Sample tenant quota"""
    return {
        "tenant_id": "tenant-123",
        "jobs_per_day": 1000,
        "jobs_per_month": 30000,
        "max_concurrent": 50,
        "storage_gb": 100
    }


@pytest.fixture
def validator_address():
    """Sample validator address"""
    return "0xvalidator1234567890abcdef"


@pytest.fixture
def miner_address():
    """Sample miner address"""
    return "0xminer1234567890abcdef"


@pytest.fixture
def sample_transactions():
    """List of sample transactions"""
    return [
        {
            "hash": "0xtx123",
            "from": "0xaddr1",
            "to": "0xaddr2",
            "value": "100"
        },
        {
            "hash": "0xtx456",
            "from": "0xaddr3",
            "to": "0xaddr4",
            "value": "200"
        }
    ]


@pytest.fixture
def sample_block(sample_transactions):
    """Sample block with transactions"""
    return {
        "number": 100,
        "hash": "0xblockhash123",
        "parent_hash": "0xparenthash456",
        "transactions": sample_transactions,
        "timestamp": datetime.utcnow(),
        "validator": "0xvalidator123"
    }


@pytest.fixture
def mock_database():
    """Mock database session"""
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    from unittest.mock import Mock
    redis_mock = Mock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.delete.return_value = 1
    return redis_mock


@pytest.fixture
def mock_web3():
    """Mock Web3 instance"""
    from unittest.mock import Mock
    web3_mock = Mock()
    web3_mock.eth.contract.return_value = Mock()
    web3_mock.eth.get_balance.return_value = 1000000
    web3_mock.eth.gas_price = 20
    return web3_mock


@pytest.fixture
def browser():
    """Selenium WebDriver fixture for E2E tests"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()


@pytest.fixture
def mobile_browser():
    """Mobile browser fixture for responsive testing"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    mobile_emulation = {
        "deviceMetrics": {"width": 375, "height": 667, "pixelRatio": 2.0},
        "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
    }
    options.add_experimental_option("mobileEmulation", mobile_emulation)
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()


@pytest.fixture
def base_url():
    """Base URL for E2E tests"""
    return "http://localhost:8000"


@pytest.fixture
def mock_file_storage():
    """Mock file storage service"""
    from unittest.mock import Mock
    storage_mock = Mock()
    storage_mock.upload.return_value = {"url": "http://example.com/file.txt"}
    storage_mock.download.return_value = b"file content"
    storage_mock.delete.return_value = True
    return storage_mock


@pytest.fixture
def mock_email_service():
    """Mock email service"""
    from unittest.mock import Mock
    email_mock = Mock()
    email_mock.send.return_value = {"message_id": "msg-123"}
    email_mock.send_verification.return_value = {"token": "token-456"}
    return email_mock


@pytest.fixture
def mock_notification_service():
    """Mock notification service"""
    from unittest.mock import Mock
    notification_mock = Mock()
    notification_mock.send_push.return_value = True
    notification_mock.send_webhook.return_value = {"status": "sent"}
    return notification_mock


@pytest.fixture
def sample_api_key():
    """Sample API key"""
    return {
        "id": "key-123",
        "key": "aitbc_test_key_1234567890",
        "name": "Test API Key",
        "permissions": ["read", "write"],
        "created_at": datetime.utcnow()
    }


@pytest.fixture
def sample_service_listing():
    """Sample marketplace service listing"""
    return {
        "id": "service-123",
        "name": "AI Inference Service",
        "description": "High-performance AI inference",
        "provider_id": "provider-123",
        "pricing": {
            "per_token": 0.0001,
            "per_minute": 0.01
        },
        "capabilities": ["text-generation", "image-generation"],
        "status": "active"
    }


@pytest.fixture
def sample_booking():
    """Sample booking object"""
    return {
        "id": "booking-123",
        "service_id": "service-123",
        "client_id": "client-123",
        "status": "confirmed",
        "start_time": datetime.utcnow() + timedelta(hours=1),
        "end_time": datetime.utcnow() + timedelta(hours=2),
        "total_cost": "10.0"
    }


@pytest.fixture
def mock_blockchain_node():
    """Mock blockchain node for testing"""
    from unittest.mock import Mock
    node_mock = Mock()
    node_mock.start.return_value = {"status": "running"}
    node_mock.stop.return_value = {"status": "stopped"}
    node_mock.get_block.return_value = {"number": 100, "hash": "0x123"}
    node_mock.submit_transaction.return_value = {"hash": "0xtx456"}
    return node_mock


@pytest.fixture
def sample_zk_proof():
    """Sample zero-knowledge proof"""
    return {
        "proof": "zk_proof_123456",
        "public_inputs": ["x", "y"],
        "verification_key": "vk_789012"
    }


@pytest.fixture
def sample_confidential_data():
    """Sample confidential transaction data"""
    return {
        "encrypted_payload": "encrypted_data_123",
        "commitment": "commitment_hash_456",
        "nullifier": "nullifier_789",
        "merkle_proof": {
            "root": "root_hash",
            "path": ["hash1", "hash2", "hash3"],
            "indices": [0, 1, 0]
        }
    }


@pytest.fixture
def mock_ipfs():
    """Mock IPFS client"""
    from unittest.mock import Mock
    ipfs_mock = Mock()
    ipfs_mock.add.return_value = {"Hash": "QmHash123"}
    ipfs_mock.cat.return_value = b"IPFS content"
    ipfs_mock.pin.return_value = {"Pins": ["QmHash123"]}
    return ipfs_mock


@pytest.fixture(autouse=True)
def cleanup_mocks():
    """Cleanup after each test"""
    yield
    # Add any cleanup code here
    pass


# Performance testing fixtures
@pytest.fixture
def performance_metrics():
    """Collect performance metrics during test"""
    import time
    start_time = time.time()
    yield {"start": start_time}
    end_time = time.time()
    return {"duration": end_time - start_time}


# Load testing fixtures
@pytest.fixture
def load_test_config():
    """Configuration for load testing"""
    return {
        "concurrent_users": 100,
        "ramp_up_time": 30,
        "test_duration": 300,
        "target_rps": 50
    }
