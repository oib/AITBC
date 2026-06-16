"""
Common test fixtures for AITBC tests
Provides shared fixtures used across multiple test domains
"""

import os
from unittest.mock import Mock

import pytest
from aitbc import DATA_DIR, LOG_DIR
from aitbc.testing import MockCache, MockDatabase, MockFactory, TestDataGenerator


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically set up test environment for all tests"""
    os.environ["TEST_MODE"] = "true"
    os.environ["AUDIT_LOG_DIR"] = str(LOG_DIR / "audit")
    os.environ["TEST_DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["DATA_DIR"] = str(DATA_DIR)
    yield
    # Cleanup if needed


@pytest.fixture
def mock_optional_dependencies():
    """Mock optional dependencies that may not be installed"""
    # Use pytest-mock to mock modules at test time
    # Tests that need these can use this fixture
    return None


@pytest.fixture
def mock_aitbc_crypto():
    """Mock aitbc_crypto package when not available"""
    try:
        import aitbc_crypto

        return aitbc_crypto
    except ImportError:
        # Create mock
        mock_crypto = Mock()

        def mock_encrypt_data(data, key):
            return f"encrypted_{data}"

        def mock_decrypt_data(data, key):
            return data.replace("encrypted_", "")

        def mock_generate_viewing_key():
            return "test_viewing_key"

        mock_crypto.encrypt_data = mock_encrypt_data
        mock_crypto.decrypt_data = mock_decrypt_data
        mock_crypto.generate_viewing_key = mock_generate_viewing_key

        # Add signing submodule
        signing_mod = Mock()

        class _ReceiptSigner:
            def verify_receipt(self, payload, signature):
                return True

        signing_mod.ReceiptSigner = _ReceiptSigner
        mock_crypto.signing = signing_mod

        return mock_crypto


@pytest.fixture
def sample_tenant():
    """Create a sample tenant for testing using TestDataGenerator"""
    return TestDataGenerator.generate_user_data(id="tenant-123", first_name="Test", last_name="Tenant", is_active=True)


@pytest.fixture
def sample_job_data():
    """Sample job creation data using TestDataGenerator"""
    return {
        "job_type": "ai_inference",
        "parameters": {"model": "gpt-4", "prompt": "Test prompt", "max_tokens": 100, "temperature": 0.7},
        "priority": "normal",
        "timeout": 300,
    }


@pytest.fixture
def mock_db():
    """Create a mock database for testing"""
    return MockDatabase()


@pytest.fixture
def mock_cache():
    """Create a mock cache for testing"""
    return MockCache()


@pytest.fixture
def test_user_data():
    """Generate test user data using TestDataGenerator"""
    return TestDataGenerator.generate_user_data()


@pytest.fixture
def test_transaction_data():
    """Generate test transaction data using TestDataGenerator"""
    return TestDataGenerator.generate_transaction_data()


@pytest.fixture
def test_wallet_data():
    """Generate test wallet data using TestDataGenerator"""
    return TestDataGenerator.generate_wallet_data()


@pytest.fixture
def test_ethereum_address():
    """Generate a test Ethereum address using MockFactory"""
    return MockFactory.generate_ethereum_address()
