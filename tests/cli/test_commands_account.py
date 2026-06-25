"""
Account Commands Tests
Tests for account CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestAccountCommands:
    """Test account command group"""

    def test_account_group_exists(self):
        """Test that account command group exists"""
        from aitbc_cli.commands.account import account

        assert account is not None
        assert hasattr(account, "name")

    def test_account_group_name(self):
        """Test account group name"""
        from aitbc_cli.commands.account import account

        assert account.name == "account"

    def test_account_group_has_get_subcommand(self):
        """The ``get`` subcommand is registered on the account group."""
        from aitbc_cli.commands.account import account

        assert "get" in account.commands

    def test_account_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the account group."""
        from aitbc_cli.commands.account import account

        assert "list" in account.commands

    @patch("aitbc_cli.commands.account.AITBCHTTPClient")
    def test_account_get_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``account get`` returns account data from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = mock_blockchain_rpc.responses["/rpc/account/ait1qtestaddress0000000000000000000000000"]

        from aitbc_cli.commands.account import account

        result = runner.invoke(
            account,
            ["get", "--address", "ait1qtestaddress0000000000000000000000000"],
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        # The address should appear in the RPC path that was requested.
        requested_path = mock_client.get.call_args[0][0]
        assert "ait1qtestaddress0000000000000000000000000" in requested_path

    @patch("aitbc_cli.commands.account.AITBCHTTPClient")
    def test_account_get_command_with_chain_id(self, mock_http_class, runner, mock_blockchain_rpc):
        """``account get --chain-id`` forwards the chain_id param."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = mock_blockchain_rpc.responses["/rpc/account/ait1qtestaddress0000000000000000000000000"]

        from aitbc_cli.commands.account import account

        result = runner.invoke(
            account,
            ["get", "--address", "ait1qtestaddress0000000000000000000000000", "--chain-id", "test-chain"],
        )

        assert result.exit_code == 0, result.output
        _, kwargs = mock_client.get.call_args
        assert kwargs.get("params", {}).get("chain_id") == "test-chain"

    @patch("aitbc_cli.commands.account.AITBCHTTPClient")
    def test_account_list_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``account list`` returns the accounts list from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = mock_blockchain_rpc.responses["/rpc/accounts"]

        from aitbc_cli.commands.account import account

        result = runner.invoke(account, ["list"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/rpc/accounts" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.account.AITBCHTTPClient")
    def test_account_list_falls_back_on_network_error(self, mock_http_class, runner):
        """``account list`` falls back to simulated data on NetworkError."""
        from aitbc_cli.commands.account import account
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(account, ["list"])

        # NetworkError is caught and a simulated payload is emitted (exit 0).
        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    @patch("aitbc_cli.commands.account.AITBCHTTPClient")
    def test_account_get_command_network_error_aborts(self, mock_http_class, runner):
        """``account get`` aborts (non-zero) on a NetworkError."""
        from aitbc_cli.commands.account import account
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            account,
            ["get", "--address", "ait1qtestaddress0000000000000000000000000"],
        )

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
