"""
Minimal conftest for pytest discovery
Imports fixtures from dedicated fixture files for better organization
"""

import sys
from pathlib import Path

# Configure Python path for test discovery
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import fixtures from dedicated fixture files
# Common fixtures (environment setup, data generators)
from tests.fixtures.common import (
    setup_test_environment,
    mock_optional_dependencies,
    mock_aitbc_crypto,
    sample_tenant,
    sample_job_data,
    mock_db,
    mock_cache,
    test_user_data,
    test_transaction_data,
    test_wallet_data,
    test_ethereum_address,
)

# Coordinator API fixtures
from tests.fixtures.coordinator import coordinator_client

# Blockchain fixtures
from tests.fixtures.blockchain import (
    blockchain_client,
    wallet_client,
    marketplace_client,
)

# Training fixtures (kept here as they're specific to training tests)
from aitbc.training_setup import TrainingEnvironment, TrainingSetupError

import pytest


@pytest.fixture(scope="session")
def training_env():
    """
    Session-scoped fixture for training environment setup.
    Sets up the training environment once per test session.
    """
    env = TrainingEnvironment()
    try:
        env.check_prerequisites()
        yield env
    except TrainingSetupError as e:
        pytest.skip(f"Training prerequisites not met: {e}")


@pytest.fixture
def training_env_mock():
    """
    Function-scoped fixture for mocked training environment.
    Uses mocked subprocess calls for faster, isolated tests.
    """
    from unittest.mock import patch, MagicMock
    
    env = TrainingEnvironment()
    
    def mock_subprocess_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        return mock_result
    
    with patch('subprocess.run', side_effect=mock_subprocess_run):
        yield env


@pytest.fixture
def mock_faucet_response():
    """Mock faucet API response for testing"""
    return {
        "status": "success",
        "address": "ait1testaddress",
        "amount": 1000,
        "transaction_id": "tx_test123",
        "timestamp": "2026-05-05T12:00:00"
    }


@pytest.fixture
def training_stage_data():
    """Sample training stage data for testing"""
    return {
        "stage": "stage1_foundation",
        "agent_type": "general",
        "training_data": {
            "prerequisites": {
                "description": "Test prerequisites",
                "setup_script": "/opt/aitbc/scripts/training/setup_training_env.sh",
                "requirements": ["AITBC node running", "Funded accounts"]
            },
            "operations": [
                {
                    "operation": "wallet_create",
                    "parameters": {"name": "test-wallet"},
                    "expected_result": {"status": "success"}
                }
            ]
        }
    }
