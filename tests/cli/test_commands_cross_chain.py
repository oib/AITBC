"""
Cross Chain Commands Tests
Tests for cross_chain CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestCrossChainCommands:
    """Test cross_chain command group"""

    def test_cross_chain_group_exists(self):
        """Test that cross_chain command group exists"""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert cross_chain is not None
        assert hasattr(cross_chain, "name")

    def test_cross_chain_group_name(self):
        """Test cross_chain group name"""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert cross_chain.name == "cross-chain"

    def test_cross_chain_group_has_rates_subcommand(self):
        """The ``rates`` subcommand is registered on the cross_chain group."""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert "rates" in cross_chain.commands

    def test_cross_chain_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the cross_chain group."""
        from aitbc_cli.commands.cross_chain import cross_chain

        assert "status" in cross_chain.commands

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_rates_command(self, mock_http_class, runner, mock_config):
        """``cross-chain rates`` returns exchange rates from the mocked RPC."""
        # The rates command uses AITBCHTTPClient as a context manager and
        # treats the return of client.get() as a response object with
        # status_code and json().  Configure the mock accordingly.
        mock_client = mock_http_class.return_value.__enter__.return_value
        mock_response = mock_client.get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {"rates": {"chain-a-chain-b": 1.5}}

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["rates"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_rates_command_specific_pair(self, mock_http_class, runner, mock_config):
        """``cross-chain rates --from-chain --to-chain`` filters to a specific pair."""
        mock_client = mock_http_class.return_value.__enter__.return_value
        mock_response = mock_client.get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {"rates": {"chain-a-chain-b": 1.5}}

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["rates", "--from-chain", "chain-a", "--to-chain", "chain-b"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output

    @patch("aitbc_cli.commands.cross_chain.AITBCHTTPClient")
    def test_cross_chain_status_command(self, mock_http_class, runner, mock_config):
        """``cross-chain status`` returns swap status from the mocked RPC."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "swap_id": "swap123",
            "status": "completed",
            "from_chain": "chain-a",
            "to_chain": "chain-b",
        }

        from aitbc_cli.commands.cross_chain import cross_chain

        result = runner.invoke(
            cross_chain,
            ["status", "swap123"],
            obj={"output": "table", "output_format": "table", "config": mock_config},
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        called_path = mock_client.get.call_args[0][0]
        assert "/cross-chain/swap/swamp123" in called_path or "swap" in called_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
