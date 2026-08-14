"""
Integration tests for training environment setup.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aitbc.training_setup import FundingError, MessagingError, TrainingEnvironment, TrainingSetupError


class TestTrainingEnvironment:
    """Test TrainingEnvironment class"""

    def test_initialization(self):
        """Test TrainingEnvironment initialization"""
        env = TrainingEnvironment()
        assert env.aitbc_dir == Path("/opt/aitbc")
        assert env.log_dir == Path("/var/log/aitbc/training-setup")
        assert env.faucet_amount == 1000
        assert env.genesis_allocation == 10000

    def test_custom_initialization(self):
        """Test TrainingEnvironment with custom parameters"""
        env = TrainingEnvironment(
            aitbc_dir="/custom/path",
            log_dir="/custom/logs",
            faucet_amount=500,
            genesis_allocation=5000,
        )
        assert env.aitbc_dir == Path("/custom/path")
        assert env.log_dir == Path("/custom/logs")
        assert env.faucet_amount == 500
        assert env.genesis_allocation == 5000

    def test_check_prerequisites_missing_cli(self, tmp_path):
        """Test prerequisites check with missing CLI"""
        env = TrainingEnvironment(aitbc_dir=str(tmp_path))
        with pytest.raises(TrainingSetupError):
            env.check_prerequisites()

    def test_generate_auth_token(self, training_env_mock):
        """Test auth token generation"""
        token = training_env_mock.generate_auth_token()
        assert isinstance(token, str)
        assert len(token) == 64  # 32 hex bytes = 64 characters

    def test_verify_environment(self, training_env_mock):
        """Test environment verification"""
        result = training_env_mock.verify_environment()
        assert "wallets" in result
        assert "blockchain" in result


class TestTrainingSetupExceptions:
    """Test training setup exceptions"""

    def test_funding_error(self):
        """Test FundingError exception"""
        with pytest.raises(FundingError) as exc_info:
            raise FundingError("Funding failed")
        assert str(exc_info.value) == "Funding failed"
        assert isinstance(exc_info.value, TrainingSetupError)

    def test_messaging_error(self):
        """Test MessagingError exception"""
        with pytest.raises(MessagingError) as exc_info:
            raise MessagingError("Messaging failed")
        assert str(exc_info.value) == "Messaging failed"
        assert isinstance(exc_info.value, TrainingSetupError)

    def test_training_setup_error(self):
        """Test TrainingSetupError exception"""
        with pytest.raises(TrainingSetupError) as exc_info:
            raise TrainingSetupError("Setup failed")
        assert str(exc_info.value) == "Setup failed"


class TestTrainingEnvWithMockSubprocess:
    """Test training environment with mocked subprocess calls"""

    @pytest.fixture
    def mock_env(self):
        """Create training environment with subprocess mocked"""
        env = TrainingEnvironment()

        def mock_run(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "success"
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", side_effect=mock_run):
            yield env


@pytest.mark.integration
class TestTrainingEnvironmentIntegration:
    """Integration tests that may require actual AITBC CLI"""

    def test_real_token_generation(self, training_env):
        """Test token generation with real environment"""
        token = training_env.generate_auth_token()
        assert len(token) == 64
