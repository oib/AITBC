"""Tests for governance CLI commands"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from aitbc_cli.commands.operations import operations
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    config = Mock()
    config.coordinator_url = "http://localhost:8000"
    config.api_key = "test_key"
    config.blockchain_rpc_url = "http://localhost:8202"
    config.hub_discovery_url = "hub.aitbc.bubuit.net"
    config.governance_service_url = "http://localhost:8105"
    return config


@pytest.fixture
def temp_wallet_dir():
    """Create a temporary wallet directory with a test wallet"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wallet_dir = Path(tmpdir) / "wallets"
        wallet_dir.mkdir(parents=True, exist_ok=True)
        wallet_file = wallet_dir / "test_wallet.json"
        wallet_data = {"address": "aitbc1test", "balance": 1000.0, "private_key": "a" * 64}
        wallet_file.write_text(json.dumps(wallet_data))
        with patch("aitbc_cli.commands.operations.DEFAULT_WALLET_DIR", wallet_dir):
            yield wallet_dir


class TestGovernanceCommands:
    @pytest.fixture(autouse=True)
    def mock_http(self):
        """Mock AITBCHTTPClient for blockchain RPC calls"""
        with patch("aitbc_cli.commands.operations.AITBCHTTPClient") as mock_http_class:
            mock_instance = Mock()
            mock_http_class.return_value = mock_instance
            mock_instance.post.return_value = {"proposal_id": "prop_123", "status": "active", "tx_hash": "0xabc123"}
            mock_instance.get.return_value = {
                "proposal_id": "prop_123",
                "title": "Test Proposal",
                "status": "active",
                "votes_for": 10.0,
                "votes_against": 2.0,
                "total_votes": 12.0,
                "voter_count": 3,
            }
            yield mock_http_class

    def test_proposal_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test creating a governance proposal"""
        result = runner.invoke(
            operations,
            [
                "governance",
                "proposal",
                "--proposal-id",
                "prop_123",
                "--title",
                "Test Proposal",
                "--description",
                "Test description",
                "--category",
                "general",
                "--wallet",
                "test_wallet",
                "--voting-days",
                "7",
            ],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/rpc/governance/proposal" in call_args[0][0]

    def test_vote_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test voting on a governance proposal"""
        result = runner.invoke(
            operations,
            ["governance", "vote", "prop_123", "--vote", "for", "--wallet", "test_wallet", "--voting-power", "10"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/rpc/governance/vote" in call_args[0][0]
        assert call_args[1]["json"]["vote_type"] == "for"

    def test_get_proposal_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test getting a governance proposal"""
        result = runner.invoke(
            operations, ["governance", "get-proposal", "prop_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        mock_http.return_value.get.assert_called_once()
        call_args = mock_http.return_value.get.call_args
        assert "/rpc/governance/proposal/prop_123" in call_args[0][0]

    def test_stake_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test governance staking command"""
        result = runner.invoke(
            operations,
            ["governance", "stake", "--address", "aitbc1test", "--amount", "1000", "--lock-days", "30"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/v1/governance/stake" in call_args[0][0]

    def test_delegate_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test governance delegation command"""
        result = runner.invoke(
            operations,
            ["governance", "delegate", "--delegator", "aitbc1alice", "--delegate", "aitbc1bob", "--amount", "500"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/v1/governance/delegate" in call_args[0][0]

    def test_execute_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test proposal execution command"""
        result = runner.invoke(
            operations, ["governance", "execute", "prop_123"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        mock_http.return_value.post.assert_called_once()
        call_args = mock_http.return_value.post.call_args
        assert "/v1/governance/proposals/prop_123/execute" in call_args[0][0]

    def test_voting_power_command(self, runner, mock_config, mock_http, temp_wallet_dir):
        """Test voting power query command"""
        result = runner.invoke(
            operations, ["governance", "voting-power", "aitbc1test"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        mock_http.return_value.get.assert_called_once()
        call_args = mock_http.return_value.get.call_args
        assert "/v1/governance/voting-power/aitbc1test" in call_args[0][0]
