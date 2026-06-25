"""
Contract Commands Tests
Tests for contract CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestContractCommands:
    """Test contract command group"""

    def test_contract_group_exists(self):
        """Test that contract command group exists"""
        from aitbc_cli.commands.contract import contract

        assert contract is not None
        assert hasattr(contract, "name")

    def test_contract_group_name(self):
        """Test contract group name"""
        from aitbc_cli.commands.contract import contract

        assert contract.name == "contract"

    def test_contract_group_has_deploy_subcommand(self):
        """The ``deploy`` subcommand is registered on the contract group."""
        from aitbc_cli.commands.contract import contract

        assert "deploy" in contract.commands

    def test_contract_group_has_call_subcommand(self):
        """The ``call`` subcommand is registered on the contract group."""
        from aitbc_cli.commands.contract import contract

        assert "call" in contract.commands

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_deploy_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``contract deploy`` deploys a contract via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"tx_hash": "0xdeploy123", "status": "confirmed"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract,
            ["deploy", "--contract-name", "MyContract"],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        # Verify the deploy endpoint and contract name are in the request.
        called_path = mock_client.post.call_args[0][0]
        assert "/rpc/contracts/deploy" in called_path

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_call_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``contract call`` calls a contract method via the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"result": "0xreturnvalue", "status": "success"}

        from aitbc_cli.commands.contract import contract

        result = runner.invoke(
            contract,
            [
                "call",
                "--contract-address", "ait1qcontract000000000000000000000000000",
                "--method", "balanceOf",
                "--args", '["ait1qtestaddress0000000000000000000000000"]',
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        called_path = mock_client.post.call_args[0][0]
        assert "/rpc/contracts/call" in called_path

    @patch("aitbc_cli.commands.contract.AITBCHTTPClient")
    def test_contract_deploy_network_error_aborts(self, mock_http_class, runner):
        """``contract deploy`` aborts (non-zero) on a NetworkError."""
        from aitbc_cli.commands.contract import contract
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            contract,
            ["deploy", "--contract-name", "MyContract"],
        )

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
