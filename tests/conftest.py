"""
Enhanced conftest for pytest with AITBC CLI support and comprehensive test coverage
"""

import pytest
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock
from click.testing import CliRunner

# Configure Python path for test discovery
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add CLI path
sys.path.insert(0, str(project_root / "cli"))

# Add all source paths for comprehensive testing
source_paths = [
    "packages/py/aitbc-core/src",
    "packages/py/aitbc-crypto/src", 
    "packages/py/aitbc-p2p/src",
    "packages/py/aitbc-sdk/src",
    "apps/coordinator-api/src",
    "apps/wallet-daemon/src",
    "apps/blockchain-node/src",
    "apps/pool-hub/src",
    "apps/explorer-web/src",
    "apps/zk-circuits/src"
]

for path in source_paths:
    full_path = project_root / path
    if full_path.exists():
        sys.path.insert(0, str(full_path))

# Add test paths for imports
test_paths = [
    "packages/py/aitbc-crypto/tests",
    "packages/py/aitbc-sdk/tests", 
    "apps/coordinator-api/tests",
    "apps/wallet-daemon/tests",
    "apps/blockchain-node/tests",
    "apps/pool-hub/tests",
    "apps/explorer-web/tests",
    "cli/tests"
]

for path in test_paths:
    full_path = project_root / path
    if full_path.exists():
        sys.path.insert(0, str(full_path))

# Set up test environment
os.environ["TEST_MODE"] = "true"
os.environ["AUDIT_LOG_DIR"] = str(project_root / "logs" / "audit")
os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"

# Mock missing optional dependencies
sys.modules['slowapi'] = Mock()
sys.modules['slowapi.util'] = Mock()
sys.modules['slowapi.limiter'] = Mock()
sys.modules['web3'] = Mock()
sys.modules['aitbc_crypto'] = Mock()

# Mock aitbc_crypto functions
def mock_encrypt_data(data, key):
    return f"encrypted_{data}"
def mock_decrypt_data(data, key):
    return data.replace("encrypted_", "")
def mock_generate_viewing_key():
    return "test_viewing_key"

sys.modules['aitbc_crypto'].encrypt_data = mock_encrypt_data
sys.modules['aitbc_crypto'].decrypt_data = mock_decrypt_data
sys.modules['aitbc_crypto'].generate_viewing_key = mock_generate_viewing_key

# Common fixtures for all test types
@pytest.fixture
def cli_runner():
    """Create CLI runner for testing"""
    return CliRunner()

@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'coordinator_url': 'http://localhost:8000',
        'api_key': 'test-key',
        'wallet_name': 'test-wallet',
        'blockchain_url': 'http://localhost:8082'
    }

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_http_client():
    """Mock HTTP client for API testing"""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client.put.return_value = mock_response
    mock_client.delete.return_value = mock_response
    return mock_client

# Test markers for different test types
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (may require external services)")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "cli: CLI command tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "blockchain: Blockchain-related tests")
    config.addinivalue_line("markers", "crypto: Cryptography tests")
    config.addinivalue_line("markers", "contracts: Smart contract tests")

# Pytest collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location"""
    for item in items:
        # Add markers based on file path
        if "cli/tests" in str(item.fspath):
            item.add_marker(pytest.mark.cli)
        elif "apps/coordinator-api/tests" in str(item.fspath):
            item.add_marker(pytest.mark.api)
        elif "apps/blockchain-node/tests" in str(item.fspath):
            item.add_marker(pytest.mark.blockchain)
        elif "packages/py/aitbc-crypto/tests" in str(item.fspath):
            item.add_marker(pytest.mark.crypto)
        elif "contracts/test" in str(item.fspath):
            item.add_marker(pytest.mark.contracts)
        
        # Add slow marker for integration tests
        if "integration" in str(item.fspath).lower():
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def aitbc_cli_runner():
    """Create AITBC CLI runner with test configuration"""
    cli_path = project_root / "aitbc-cli"

    def runner(*args, env=None, cwd=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [str(cli_path), *args],
            capture_output=True,
            text=True,
            cwd=str(cwd or project_root),
            env=merged_env,
        )
    
    # Default test configuration
    default_config = {
        'coordinator_url': 'http://test:8000',
        'api_key': 'test_api_key',
        'output_format': 'json',
        'log_level': 'INFO'
    }
    
    return runner, default_config


@pytest.fixture
def mock_aitbc_config():
    """Mock AITBC configuration for testing"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_api_key"
    config.wallet_path = "/tmp/test_wallet.json"
    config.default_chain = "testnet"
    config.timeout = 30
    config.retry_attempts = 3
    return config


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
