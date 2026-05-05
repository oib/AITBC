"""
Integration tests for training environment setup.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from aitbc.training_setup import TrainingEnvironment, TrainingSetupError, FundingError, MessagingError


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

    def test_check_prerequisites_success(self, training_env_mock):
        """Test successful prerequisites check"""
        result = training_env_mock.check_prerequisites()
        assert result is True

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

    def test_fund_training_wallet_success(self, training_env_mock):
        """Test successful wallet funding"""
        result = training_env_mock.fund_training_wallet("test-wallet")
        assert result["status"] == "completed"
        assert result["wallet"] == "test-wallet"
        assert result["amount"] == 1000

    def test_fund_training_wallet_custom_password(self, training_env_mock):
        """Test wallet funding with custom password"""
        result = training_env_mock.fund_training_wallet("test-wallet", "custom-password")
        assert result["status"] == "completed"

    def test_verify_environment(self, training_env_mock):
        """Test environment verification"""
        result = training_env_mock.verify_environment()
        assert "wallets" in result
        assert "blockchain" in result

    def test_create_genesis_allocation(self, training_env_mock):
        """Test genesis allocation creation"""
        result = training_env_mock.create_genesis_allocation()
        assert result["status"] == "completed"
        assert result["allocation"] == 10000

    def test_setup_faucet_wallet(self, training_env_mock):
        """Test faucet wallet setup"""
        result = training_env_mock.setup_faucet_wallet()
        assert result["status"] == "completed"
        assert result["amount"] == 1000

    def test_configure_messaging_auth(self, training_env_mock):
        """Test messaging authentication configuration"""
        result = training_env_mock.configure_messaging_auth("test-wallet")
        assert result["status"] == "completed"
        assert result["wallet"] == "test-wallet"
        assert "token_file" in result

    def test_test_messaging_connectivity(self, training_env_mock):
        """Test messaging connectivity test"""
        result = training_env_mock.test_messaging_connectivity()
        assert result is True

    def test_setup_full_environment(self, training_env_mock):
        """Test full environment setup"""
        result = training_env_mock.setup_full_environment()
        assert "prerequisites" in result
        assert "funding" in result
        assert "wallets_funded" in result
        assert "messaging" in result
        assert "verification" in result


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
        
        with patch('subprocess.run', side_effect=mock_run):
            yield env

    def test_funding_with_subprocess_error(self, mock_env):
        """Test funding when subprocess fails"""
        def mock_run_fail(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Funding failed"
            return mock_result
        
        with patch('subprocess.run', side_effect=mock_run_fail):
            with pytest.raises(FundingError):
                mock_env.fund_training_wallet("test-wallet")

    def test_messaging_with_subprocess_error(self, mock_env):
        """Test messaging configuration when subprocess fails"""
        def mock_run_fail(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Messaging failed"
            return mock_result
        
        with patch('subprocess.run', side_effect=mock_run_fail):
            with pytest.raises(MessagingError):
                mock_env.configure_messaging_auth("test-wallet")


@pytest.mark.integration
class TestTrainingEnvironmentIntegration:
    """Integration tests that may require actual AITBC CLI"""

    def test_real_cli_check(self, training_env):
        """Test with real AITBC CLI if available"""
        # This test will be skipped if prerequisites are not met
        result = training_env.check_prerequisites()
        assert result is True

    def test_real_token_generation(self, training_env):
        """Test token generation with real environment"""
        token = training_env.generate_auth_token()
        assert len(token) == 64
