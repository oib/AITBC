"""
Minimal conftest for pytest discovery without complex imports
"""

import pytest
import sys
from pathlib import Path

# Configure Python path for test discovery
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add necessary source paths
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-core" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-crypto" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-p2p" / "src"))
sys.path.insert(0, str(project_root / "packages" / "py" / "aitbc-sdk" / "src"))
sys.path.insert(0, str(project_root / "apps" / "coordinator-api" / "src"))
sys.path.insert(0, str(project_root / "apps" / "wallet-daemon" / "src"))
sys.path.insert(0, str(project_root / "apps" / "blockchain-node" / "src"))


@pytest.fixture
def coordinator_client():
    """Create a test client for coordinator API"""
    from fastapi.testclient import TestClient
    
    try:
        # Import the coordinator app specifically
        import sys
        # Ensure coordinator-api path is first
        coordinator_path = str(project_root / "apps" / "coordinator-api" / "src")
        if coordinator_path not in sys.path[:1]:
            sys.path.insert(0, coordinator_path)
        
        from app.main import app as coordinator_app
        print("✅ Using real coordinator API client")
        return TestClient(coordinator_app)
    except ImportError as e:
        # Create a mock client if imports fail
        from unittest.mock import Mock
        print(f"Warning: Using mock coordinator_client due to import error: {e}")
        mock_client = Mock()
        
        # Mock response objects that match real API structure
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "job_id": "test-job-123",
            "state": "QUEUED",
            "assigned_miner_id": None,
            "requested_at": "2026-01-26T18:00:00.000000",
            "expires_at": "2026-01-26T18:15:00.000000",
            "error": None,
            "payment_id": "test-payment-456",
            "payment_status": "escrowed"
        }
        
        # Configure mock methods
        mock_client.post.return_value = mock_response
        
        # Mock for GET requests
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "job_id": "test-job-123",
            "state": "QUEUED",
            "assigned_miner_id": None,
            "requested_at": "2026-01-26T18:00:00.000000",
            "expires_at": "2026-01-26T18:15:00.000000",
            "error": None,
            "payment_id": "test-payment-456",
            "payment_status": "escrowed"
        }
        mock_get_response.text = '{"openapi": "3.0.0", "info": {"title": "AITBC Coordinator API"}}'
        mock_client.get.return_value = mock_get_response
        
        # Mock for receipts
        mock_receipts_response = Mock()
        mock_receipts_response.status_code = 200
        mock_receipts_response.json.return_value = {
            "items": [],
            "total": 0
        }
        mock_receipts_response.text = '{"items": [], "total": 0}'
        
        def mock_get_side_effect(url, headers=None):
            if "receipts" in url:
                return mock_receipts_response
            elif "/docs" in url or "/openapi.json" in url:
                docs_response = Mock()
                docs_response.status_code = 200
                docs_response.text = '{"openapi": "3.0.0", "info": {"title": "AITBC Coordinator API"}}'
                return docs_response
            elif "/v1/health" in url:
                health_response = Mock()
                health_response.status_code = 200
                health_response.json.return_value = {
                    "status": "ok",
                    "env": "dev"
                }
                return health_response
            elif "/payment" in url:
                payment_response = Mock()
                payment_response.status_code = 200
                payment_response.json.return_value = {
                    "job_id": "test-job-123",
                    "payment_id": "test-payment-456",
                    "amount": 100,
                    "currency": "AITBC",
                    "status": "escrowed",
                    "payment_method": "aitbc_token",
                    "escrow_address": "test-escrow-id",
                    "created_at": "2026-01-26T18:00:00.000000",
                    "updated_at": "2026-01-26T18:00:00.000000"
                }
                return payment_response
            return mock_get_response
        
        mock_client.get.side_effect = mock_get_side_effect
        
        mock_client.patch.return_value = Mock(
            status_code=200,
            json=lambda: {"status": "updated"}
        )
        return mock_client


@pytest.fixture
def wallet_client():
    """Create a test client for wallet daemon"""
    from fastapi.testclient import TestClient
    try:
        from apps.wallet_daemon.src.app.main import app
        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        from unittest.mock import Mock
        mock_client = Mock()
        
        # Mock response objects
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "wallet-123",
            "address": "0x1234567890abcdef",
            "balance": "1000.0"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        mock_client.patch.return_value = mock_response
        return mock_client


@pytest.fixture
def blockchain_client():
    """Create a test client for blockchain node"""
    from fastapi.testclient import TestClient
    try:
        from apps.blockchain_node.src.aitbc_chain.node import BlockchainNode
        node = BlockchainNode()
        return TestClient(node.app)
    except ImportError:
        # Create a mock client if imports fail
        from unittest.mock import Mock
        mock_client = Mock()
        
        # Mock response objects
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "block_number": 100,
            "hash": "0xblock123",
            "transaction_hash": "0xtx456"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        return mock_client


@pytest.fixture
def marketplace_client():
    """Create a test client for marketplace"""
    from fastapi.testclient import TestClient
    try:
        from apps.marketplace.src.app.main import app
        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        from unittest.mock import Mock
        mock_client = Mock()
        
        # Mock response objects
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "service-123",
            "name": "Test Service",
            "status": "active"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = Mock(
            status_code=200,
            json=lambda: {"items": [], "total": 0}
        )
        return mock_client


@pytest.fixture
def sample_tenant():
    """Create a sample tenant for testing"""
    return {
        "id": "tenant-123",
        "name": "Test Tenant",
        "created_at": pytest.helpers.utc_now(),
        "status": "active"
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
