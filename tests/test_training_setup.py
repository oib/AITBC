"""Tests for AITBC training_setup module.

Tests cover:
- exceptions.py: TrainingSetupError, FundingError, MessagingError, FaucetError, PrerequisitesError
- stage_runner.py: Command, ExpectedCondition, StageDefinition, StageRunner, create_example_stage_json
- environment.py: TrainingEnvironment class
- cli.py: click CLI commands
"""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from aitbc.training_setup import (
    FundingError,
    MessagingError,
    # FaucetError, N/A in __init__
    # PrerequisitesError, N/A in __init__
    TrainingSetupError,
)
from aitbc.training_setup.cli import cli
from aitbc.training_setup.environment import TrainingEnvironment
from aitbc.training_setup.exceptions import (
    FaucetError,
    PrerequisitesError,
)
from aitbc.training_setup.stage_runner import (
    Command,
    ExpectedCondition,
    StageDefinition,
    StageRunner,
    create_example_stage_json,
)


class TestExceptions:
    """Test training_setup exceptions."""

    def test_training_setup_error(self):
        """Test TrainingSetupError base exception."""
        with pytest.raises(TrainingSetupError):
            raise TrainingSetupError("Test error")

    def test_funding_error(self):
        """Test FundingError exception."""
        with pytest.raises(FundingError):
            raise FundingError("Funding failed")

    def test_messaging_error(self):
        """Test MessagingError exception."""
        with pytest.raises(MessagingError):
            raise MessagingError("Messaging failed")

    def test_faucet_error(self):
        """Test FaucetError exception."""
        with pytest.raises(FaucetError):
            raise FaucetError("Faucet failed")

    def test_prerequisites_error(self):
        """Test PrerequisitesError exception."""
        with pytest.raises(PrerequisitesError):
            raise PrerequisitesError("Prerequisites not met")

    def test_exception_hierarchy(self):
        """Test exception inheritance."""
        assert issubclass(FundingError, TrainingSetupError)
        assert issubclass(MessagingError, TrainingSetupError)
        assert issubclass(FaucetError, TrainingSetupError)
        assert issubclass(PrerequisitesError, TrainingSetupError)

    def test_catch_base_exception(self):
        """Test catching derived exceptions with base class."""
        try:
            raise FundingError("test")
        except TrainingSetupError:
            pass  # Expected


class TestCommand:
    """Test Command dataclass."""

    def test_command_creation(self):
        """Test Command creation with all fields."""
        cmd = Command(cmd="wallet create", args=["test", "--password", "abc"], expected_re="success", expected_exit_code=0)
        assert cmd.cmd == "wallet create"
        assert cmd.args == ["test", "--password", "abc"]
        assert cmd.expected_re == "success"
        assert cmd.expected_exit_code == 0

    def test_command_defaults(self):
        """Test Command with default values."""
        cmd = Command(cmd="sleep", args=["5"])
        assert cmd.cmd == "sleep"
        assert cmd.args == ["5"]
        assert cmd.expected_re is None
        assert cmd.expected_exit_code == 0


class TestExpectedCondition:
    """Test ExpectedCondition dataclass."""

    def test_expected_condition_creation(self):
        """Test ExpectedCondition creation."""
        cond = ExpectedCondition(type="value", value=True)
        assert cond.type == "value"
        assert cond.value is True

    def test_expected_condition_regex(self):
        """Test ExpectedCondition with regex type."""
        cond = ExpectedCondition(type="regex", value=r"wallet-\d+")
        assert cond.type == "regex"
        assert cond.value == r"wallet-\d+"


class TestStageDefinition:
    """Test StageDefinition dataclass."""

    def test_stage_definition_creation(self):
        """Test StageDefinition creation."""
        commands = [Command(cmd="test", args=[])]
        expected = {"success": ExpectedCondition(type="value", value=True)}
        stage = StageDefinition(stage=1, title="Test Stage", commands=commands, expected=expected)
        assert stage.stage == 1
        assert stage.title == "Test Stage"
        assert len(stage.commands) == 1
        assert "success" in stage.expected


class TestStageRunner:
    """Test StageRunner class."""

    @pytest.fixture
    def stage_runner(self):
        """Create StageRunner with mock CLI."""
        with patch("aitbc.training_setup.stage_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="success", stderr="")
            runner = StageRunner("/mock/aitbc-cli")
            yield runner

    def test_stage_runner_init(self):
        """Test StageRunner initialization."""
        runner = StageRunner("/custom/cli")
        assert runner.aitbc_cli == "/custom/cli"
        assert runner.results == {}

    def test_stage_runner_default_cli(self):
        """Test StageRunner default CLI path."""
        runner = StageRunner()
        assert runner.aitbc_cli == "/opt/aitbc/aitbc-cli"

    def test_load_stage_from_json(self, stage_runner):
        """Test loading stage from JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "stage": 2,
                    "title": "Test Stage",
                    "prerequisites": ["prereq1"],
                    "commands": [{"cmd": "wallet create", "args": ["w1", "--password", "pw"], "re": "w1", "exit_code": 0}],
                    "expected": {"wallet_exists": {"type": "value", "value": True}},
                },
                f,
            )
            f.flush()

            stage = stage_runner.load_stage_from_json(f.name)

            assert stage.stage == 2
            assert stage.title == "Test Stage"
            assert stage.prerequisites == ["prereq1"]
            assert len(stage.commands) == 1
            assert stage.commands[0].cmd == "wallet create"
            assert "wallet_exists" in stage.expected

            Path(f.name).unlink()

    def test_load_stage_missing_file(self, stage_runner):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            stage_runner.load_stage_from_json("/nonexistent/path.json")

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_sleep(self, mock_run, stage_runner):
        """Test run_command with sleep."""
        cmd = Command(cmd="sleep", args=["2"])

        result = stage_runner.run_command(cmd)

        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "Slept" in result["output"]

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_sleep_invalid(self, mock_run, stage_runner):
        """Test run_command with invalid sleep arg."""
        cmd = Command(cmd="sleep", args=["invalid"])

        result = stage_runner.run_command(cmd)

        assert result["success"] is False

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_aitbc_success(self, mock_run, stage_runner):
        """Test run_command with successful AITBC CLI command."""
        cmd = Command(cmd="wallet list", args=[])
        mock_run.return_value = Mock(returncode=0, stdout="wallet1\nwallet2", stderr="")

        result = stage_runner.run_command(cmd)

        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "wallet1" in result["output"]

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_aitbc_failure(self, mock_run, stage_runner):
        """Test run_command with failed AITBC CLI command."""
        cmd = Command(cmd="wallet create", args=["w1", "--password", "pw"], expected_exit_code=0)
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="Error creating wallet")

        result = stage_runner.run_command(cmd)

        assert result["success"] is False
        assert result["exit_code"] == 1

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_regex_match(self, mock_run, stage_runner):
        """Test run_command with regex validation."""
        cmd = Command(cmd="wallet list", args=[], expected_re=r"wallet-\d+")
        mock_run.return_value = Mock(returncode=0, stdout="wallet-1\nwallet-2", stderr="")

        result = stage_runner.run_command(cmd)

        assert result["success"] is True

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_regex_fail(self, mock_run, stage_runner):
        """Test run_command with regex validation failure."""
        cmd = Command(cmd="wallet list", args=[], expected_re=r"wallet-\d+")
        mock_run.return_value = Mock(returncode=0, stdout="no match here", stderr="")

        result = stage_runner.run_command(cmd)

        assert result["success"] is False

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_command_timeout(self, mock_run, stage_runner):
        """Test run_command timeout."""
        cmd = Command(cmd="wallet list", args=[])
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        result = stage_runner.run_command(cmd)

        assert result["success"] is False
        assert "timed out" in result["error"]

    def test_extract_tx_hash_64_hex(self, stage_runner):
        """Test _extract_tx_hash with 64-char hex."""
        output = "Transaction hash: abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        tx_hash = stage_runner._extract_tx_hash(output)
        assert tx_hash == "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    def test_extract_tx_hash_with_prefix(self, stage_runner):
        """Test _extract_tx_hash with tx_hash prefix."""
        output = "tx_hash: abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        tx_hash = stage_runner._extract_tx_hash(output)
        assert tx_hash == "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    def test_extract_tx_hash_no_match(self, stage_runner):
        """Test _extract_tx_hash with no match."""
        output = "No transaction hash here"
        tx_hash = stage_runner._extract_tx_hash(output)
        assert tx_hash is None

    def test_validate_conditions(self, stage_runner):
        """Test validate_conditions method."""
        expected = {
            "balance": ExpectedCondition(type="value", value=100),
            "wallet": ExpectedCondition(type="regex", value=r"wallet-\d+"),
        }

        results = stage_runner.validate_conditions(expected)

        assert "balance" in results
        assert "wallet" in results
        assert results["balance"]["passed"] is True
        assert results["wallet"]["passed"] is True

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_stage_success(self, mock_run, stage_runner):
        """Test run_stage with successful commands."""
        mock_run.return_value = Mock(returncode=0, stdout="success", stderr="")

        commands = [
            Command(cmd="wallet create", args=["w1", "--password", "pw"]),
            Command(cmd="wallet list", args=[]),
        ]
        stage = StageDefinition(
            stage=1,
            title="Test Stage",
            commands=commands,
            expected={"done": ExpectedCondition(type="value", value=True)},
        )

        result = stage_runner.run_stage(stage)

        assert result["success"] is True
        assert len(result["commands"]) == 2
        assert all(c["success"] for c in result["commands"])

    @patch("aitbc.training_setup.stage_runner.subprocess.run")
    def test_run_stage_failure(self, mock_run, stage_runner):
        """Test run_stage with failed command."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="success", stderr=""),
            Mock(returncode=1, stdout="", stderr="Failed"),
        ]

        commands = [
            Command(cmd="wallet create", args=["w1"]),
            Command(cmd="wallet send", args=["genesis", "w2", "100"]),
        ]
        stage = StageDefinition(stage=1, title="Test Stage", commands=commands, expected={})

        result = stage_runner.run_stage(stage)

        assert result["success"] is False
        assert len(result["commands"]) == 2


class TestCreateExampleStageJson:
    """Test create_example_stage_json function."""

    def test_create_example_stage_json(self):
        """Test creating example stage JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.flush()
            create_example_stage_json(f.name)

            with open(f.name) as f2:
                data = json.load(f2)

            assert data["stage"] == 1
            assert data["title"] == "Foundation – Wallets & Accounts"
            assert "prerequisites" in data
            assert len(data["commands"]) == 3
            assert "expected" in data

            Path(f.name).unlink()


class TestTrainingEnvironment:
    """Test TrainingEnvironment class."""

    @pytest.fixture
    def mock_env(self):
        """Create TrainingEnvironment with mocked dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(
                aitbc_dir=tmpdir,
                log_dir=tmpdir + "/logs",
                faucet_amount=1000,
                genesis_allocation=10000,
            )
            # Mock the CLI path
            env.stage_runner.aitbc_cli = "/mock/cli"
            yield env

    def test_init(self, mock_env):
        """Test TrainingEnvironment initialization."""
        assert mock_env.aitbc_dir is not None
        assert mock_env.faucet_amount == 1000
        assert mock_env.genesis_allocation == 10000
        assert mock_env.wallet_prefix == "training-w"
        assert mock_env.stage_runner is not None

    def test_init_with_custom_params(self):
        """Test TrainingEnvironment with custom parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(
                aitbc_dir=tmpdir,
                log_dir=tmpdir + "/logs",
                faucet_amount=2000,
                genesis_allocation=20000,
                wallet_prefix="custom-w",
            )
            assert env.faucet_amount == 2000
            assert env.genesis_allocation == 20000
            assert env.wallet_prefix == "custom-w"

    @patch("aitbc.training_setup.environment.Path.exists")
    @patch("aitbc.training_setup.environment.Path.read_text")
    def test_load_genesis_password_exists(self, mock_read, mock_exists):
        """Test _load_genesis_password when file exists."""
        mock_exists.return_value = True
        mock_read.return_value = "genesis_password_123"

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            password = env._load_genesis_password()
            assert password == "genesis_password_123"

    @patch("aitbc.training_setup.environment.Path.exists")
    def test_load_genesis_password_not_exists(self, mock_exists):
        """Test _load_genesis_password when file doesn't exist."""
        mock_exists.return_value = False

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            password = env._load_genesis_password()
            assert password == ""

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_check_prerequisites_success(self, mock_run):
        """Test check_prerequisites success."""
        mock_run.return_value = Mock(returncode=0, stdout="blockchain info")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)  # Override to existing dir
            (env.aitbc_dir / "aitbc-cli").write_text("#!/bin/bash\necho test")
            (env.aitbc_dir / "aitbc-cli").chmod(0o755)

            result = env.check_prerequisites()
            assert result is True

    @patch("aitbc.training_setup.environment.Path.exists")
    def test_check_prerequisites_missing_cli(self, mock_exists):
        """Test check_prerequisites with missing CLI."""
        mock_exists.return_value = False

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")

            with pytest.raises(PrerequisitesError):
                env.check_prerequisites()

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_create_genesis_allocation(self, mock_run):
        """Test create_genesis_allocation."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="genesis\nwallet1"),
            Mock(returncode=0, stdout="10000 AIT"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.create_genesis_allocation()
            assert result["status"] == "completed"

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_setup_faucet_wallet(self, mock_run):
        """Test setup_faucet_wallet."""
        mock_run.return_value = Mock(returncode=0, stdout="100000 AIT")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.setup_faucet_wallet()
            assert result["status"] == "completed"
            assert result["funding_source"] == "genesis"

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_fund_training_wallet(self, mock_run):
        """Test fund_training_wallet."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout=""),  # wallet list
            Mock(returncode=0, stdout="created"),  # wallet create
            Mock(returncode=0, stdout="sent"),  # wallet send
            Mock(returncode=0, stdout="1000 AIT"),  # wallet balance
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.fund_training_wallet("test-wallet")
            assert result["status"] == "completed"
            assert result["wallet"] == "test-wallet"
            assert result["amount"] == 1000

    def test_fund_training_wallet_failure(self):
        """Test fund_training_wallet on funding failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")

            with patch.object(env, "fund_training_wallet", side_effect=FundingError("Failed")):
                with pytest.raises(FundingError):
                    env.fund_training_wallet("test-wallet")

    def test_generate_auth_token(self):
        """Test generate_auth_token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            token = env.generate_auth_token()
            assert len(token) == 64  # 32 bytes = 64 hex chars

    @patch("aitbc.training_setup.environment.subprocess.run")
    @patch("aitbc.training_setup.environment.Path.write_text")
    @patch("aitbc.training_setup.environment.Path.chmod")
    def test_configure_messaging_auth(self, mock_chmod, mock_write, mock_run):
        """Test configure_messaging_auth."""
        mock_run.return_value = Mock(returncode=0, stdout="success")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.configure_messaging_auth("test-wallet")
            assert result["status"] == "completed"
            assert result["wallet"] == "test-wallet"

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_test_messaging_connectivity_success(self, mock_run):
        """Test test_messaging_connectivity success."""
        mock_run.return_value = Mock(returncode=0, stdout="sent")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.test_messaging_connectivity()
            assert result is True

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_test_messaging_connectivity_failure(self, mock_run):
        """Test test_messaging_connectivity failure."""
        mock_run.return_value = Mock(returncode=1, stderr="failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.test_messaging_connectivity()
            assert result is False

    @patch("aitbc.training_setup.environment.subprocess.run")
    def test_verify_environment(self, mock_run):
        """Test verify_environment."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="ait1...ait1..."),  # wallet list
            Mock(returncode=0, stdout="blockchain info"),  # blockchain info
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            env.aitbc_dir = Path(tmpdir)

            result = env.verify_environment()
            assert "wallets" in result
            assert "blockchain" in result

    @patch.object(TrainingEnvironment, "check_prerequisites")
    @patch.object(TrainingEnvironment, "create_genesis_allocation")
    @patch.object(TrainingEnvironment, "setup_faucet_wallet")
    @patch.object(TrainingEnvironment, "fund_training_wallet")
    @patch.object(TrainingEnvironment, "configure_messaging_auth")
    @patch.object(TrainingEnvironment, "test_messaging_connectivity")
    @patch.object(TrainingEnvironment, "verify_environment")
    def test_setup_full_environment_success(
        self, mock_verify, mock_messaging, mock_fund, mock_configure, mock_faucet, mock_genesis, mock_prereq
    ):
        """Test setup_full_environment success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")

            mock_verify.return_value = {"wallets": 2, "blockchain": "running"}

            result = env.setup_full_environment()

            assert result["prerequisites"] == "passed"
            assert result["funding"] == "completed"
            assert result["wallets_funded"] == "completed"
            assert result["messaging"] == "completed"

    @patch.object(TrainingEnvironment, "check_prerequisites")
    def test_setup_full_environment_prereq_fail(self, mock_prereq):
        """Test setup_full_environment with prerequisites failure."""
        mock_prereq.side_effect = PrerequisitesError("CLI not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")

            result = env.setup_full_environment()

            assert result["prerequisites"] == "failed"

    def test_get_wallet_name(self):
        """Test get_wallet_name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")

            assert env.get_wallet_name(1) == "training-w1"
            assert env.get_wallet_name(10) == "training-w10"

    @patch("aitbc.training_setup.environment.StageRunner.run_stage_from_json")
    def test_run_stage_from_json(self, mock_run_stage):
        """Test run_stage_from_json."""
        mock_run_stage.return_value = {"success": True, "stage": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            env = TrainingEnvironment(aitbc_dir=tmpdir, log_dir=tmpdir + "/logs")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as f:
                json.dump({"stage": 1, "commands": []}, f)
                f.flush()

                result = env.run_stage_from_json(f.name)
                assert result["success"] is True


class TestCLI:
    """Test CLI commands."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner."""
        return CliRunner()

    @patch("aitbc.training_setup.cli.TrainingEnvironment.setup_full_environment")
    def test_setup_command(self, mock_setup, cli_runner):
        """Test setup command."""
        mock_setup.return_value = {"prerequisites": "passed", "funding": "completed"}

        result = cli_runner.invoke(cli, ["setup", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 0
        assert "Setup Summary" in result.output

    @patch("aitbc.training_setup.cli.TrainingEnvironment.setup_full_environment")
    def test_setup_command_failure(self, mock_setup, cli_runner):
        """Test setup command failure."""
        mock_setup.return_value = {"prerequisites": "failed"}

        result = cli_runner.invoke(cli, ["setup", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 1

    @patch("aitbc.training_setup.cli.TrainingEnvironment.check_prerequisites")
    def test_check_command_success(self, mock_check, cli_runner):
        """Test check command success."""
        mock_check.return_value = True

        result = cli_runner.invoke(cli, ["check", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 0
        assert "prerequisites met" in result.output

    @patch("aitbc.training_setup.cli.TrainingEnvironment.check_prerequisites")
    def test_check_command_failure(self, mock_check, cli_runner):
        """Test check command failure."""
        mock_check.side_effect = PrerequisitesError("CLI not found")

        result = cli_runner.invoke(cli, ["check", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 1
        assert "not met" in result.output

    @patch("aitbc.training_setup.cli.TrainingEnvironment.verify_environment")
    def test_verify_command(self, mock_verify, cli_runner):
        """Test verify command."""
        mock_verify.return_value = {"wallets": 2, "blockchain": "running"}

        result = cli_runner.invoke(cli, ["verify", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 0
        assert "Verification Results" in result.output

    @patch("aitbc.training_setup.cli.TrainingEnvironment.fund_training_wallet")
    def test_fund_wallet_command(self, mock_fund, cli_runner):
        """Test fund_wallet command."""
        mock_fund.return_value = {"status": "completed", "wallet": "test-wallet"}

        result = cli_runner.invoke(cli, ["fund-wallet", "test-wallet", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 0
        assert "funded" in result.output

    @patch("aitbc.training_setup.cli.TrainingEnvironment.fund_training_wallet")
    def test_fund_wallet_command_failure(self, mock_fund, cli_runner):
        """Test fund_wallet command failure."""
        mock_fund.side_effect = FundingError("Insufficient funds")

        result = cli_runner.invoke(cli, ["fund-wallet", "test-wallet", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 1

    @patch("aitbc.training_setup.cli.TrainingEnvironment.run_stage_from_json")
    def test_run_stage_command(self, mock_run_stage, cli_runner):
        """Test run_stage command."""
        mock_run_stage.return_value = {
            "success": True,
            "stage": 1,
            "title": "Test Stage",
            "commands": [{"success": True, "tx_hash": "abc123"}],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"stage": 1, "commands": []}, f)
            f.flush()

            result = cli_runner.invoke(cli, ["run-stage", f.name, "--aitbc-dir", "/tmp/test"])

            assert result.exit_code == 0
            assert "Stage Execution Results" in result.output

            Path(f.name).unlink()

    @patch("aitbc.training_setup.cli.TrainingEnvironment.run_stage_from_json")
    def test_run_stage_command_not_found(self, mock_run_stage, cli_runner):
        """Test run_stage with non-existent JSON."""
        mock_run_stage.side_effect = FileNotFoundError("File not found")

        result = cli_runner.invoke(cli, ["run-stage", "/nonexistent/path.json", "--aitbc-dir", "/tmp/test"])

        assert result.exit_code == 1
        assert "not found" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
