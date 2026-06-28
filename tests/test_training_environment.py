"""Tests for aitbc.training_setup.environment"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from aitbc.training_setup.environment import TrainingEnvironment


class TestTrainingEnvironment:
    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            assert env.aitbc_dir == Path(tmpdir)
            assert env.wallet_prefix == "training-w"

    def test_generate_auth_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            token = env.generate_auth_token()
            assert len(token) == 64

    def test_get_wallet_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            assert env.get_wallet_name(1) == "training-w1"

    def test_check_prerequisites_no_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "aitbc-cli").touch()
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "running"
                result = env.check_prerequisites()
            assert result is True

    def test_create_genesis_allocation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "genesis"
                result = env.create_genesis_allocation()
            assert result["status"] == "completed"

    def test_setup_faucet_wallet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "1000000"
                result = env.setup_faucet_wallet()
            assert result["status"] == "completed"

    def test_fund_training_wallet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                result = env.fund_training_wallet("test-wallet")
            assert result["status"] == "completed"
            assert result["wallet"] == "test-wallet"

    def test_configure_messaging_auth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                result = env.configure_messaging_auth("test-wallet")
            assert result["status"] == "completed"

    def test_test_messaging_connectivity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "ok"
                result = env.test_messaging_connectivity()
            assert result is True

    def test_test_messaging_connectivity_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stderr = "error"
                result = env.test_messaging_connectivity()
            assert result is False

    def test_verify_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = (
                    "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C\n0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"
                )
                result = env.verify_environment()
            assert "wallets" in result

    def test_setup_full_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                result = env.setup_full_environment()
            assert "prerequisites" in result
