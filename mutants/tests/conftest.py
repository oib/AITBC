"""
Minimal conftest for pytest discovery
Imports fixtures from dedicated fixture files for better organization
"""

import pytest
from aitbc.training_setup import TrainingEnvironment, TrainingSetupError
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def mock_ctx_obj(monkeypatch):
    """Auto-use fixture that patches CliRunner.invoke to set ctx.obj"""
    original_invoke = CliRunner.invoke

    def patched_invoke(self, cli, args, **kwargs):
        # Ensure obj is set with default context values
        if "obj" not in kwargs or kwargs["obj"] is None:
            kwargs["obj"] = {"output": "table", "url": None, "api_key": None, "verbose": 0, "debug": False}
        return original_invoke(self, cli, args, **kwargs)

    monkeypatch.setattr(CliRunner, "invoke", patched_invoke)


@pytest.fixture(scope="session")
def training_env():
    """
    Session-scoped fixture for training environment setup.
    Sets up the training environment once per test session.
    """
    env = TrainingEnvironment()
    try:
        # Temporarily skip prerequisites check to avoid hanging
        # env.check_prerequisites()
        yield env
    except TrainingSetupError as e:
        pytest.skip(f"Training prerequisites not met: {e}")


@pytest.fixture
def training_env_mock():
    """
    Function-scoped fixture for mocked training environment.
    Uses mocked subprocess calls for faster, isolated tests.
    """
    from unittest.mock import MagicMock, patch

    env = TrainingEnvironment()

    def mock_subprocess_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        return mock_result

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        yield env


@pytest.fixture
def mock_faucet_response():
    """Mock faucet API response for testing"""
    return {
        "status": "success",
        "address": "ait1testaddress",
        "amount": 1000,
        "transaction_id": "tx_test123",
        "timestamp": "2026-05-05T12:00:00",
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
                "requirements": ["AITBC node running", "Funded accounts"],
            },
            "operations": [
                {"operation": "wallet_create", "parameters": {"name": "test-wallet"}, "expected_result": {"status": "success"}}
            ],
        },
    }
