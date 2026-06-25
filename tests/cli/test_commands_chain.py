"""
Chain Commands Tests
Tests for chain CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestChainCommands:
    """Test chain command group"""

    def test_chain_group_exists(self):
        """Test that chain command group exists"""
        from aitbc_cli.commands.chain import chain

        assert chain is not None
        assert hasattr(chain, "name")

    def test_chain_group_name(self):
        """Test chain group name"""
        from aitbc_cli.commands.chain import chain

        assert chain.name == "chain"

    def test_chain_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the chain group."""
        from aitbc_cli.commands.chain import chain

        assert "list" in chain.commands

    def test_chain_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the chain group."""
        from aitbc_cli.commands.chain import chain

        assert "status" in chain.commands

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_chain_list_command(
        self, mock_load_config, mock_chain_manager_class, mock_asyncio_run, runner
    ):
        """``chain list`` lists available chains from the mocked chain manager."""
        # Return an empty list — the command should output "No chains found".
        mock_asyncio_run.return_value = []

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["list"])

        assert result.exit_code == 0, result.output
        mock_load_config.assert_called_once()
        mock_chain_manager_class.assert_called_once()

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_chain_list_with_chains(
        self, mock_load_config, mock_chain_manager_class, mock_asyncio_run, runner
    ):
        """``chain list`` formats and outputs chains when available."""
        mock_chain = MagicMock()
        mock_chain.id = "chain-1"
        mock_chain.type.value = "main"
        mock_chain.purpose = "general"
        mock_chain.name = "Main Chain"
        mock_chain.size_mb = 100.5
        mock_chain.node_count = 5
        mock_chain.contract_count = 10
        mock_chain.client_count = 3
        mock_chain.miner_count = 2
        mock_chain.status.value = "active"
        mock_asyncio_run.return_value = [mock_chain]

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["list"])

        assert result.exit_code == 0, result.output
        assert "chain-1" in result.output

    @patch("asyncio.run")
    @patch("aitbc_cli.commands.chain.ChainManager")
    @patch("aitbc_cli.commands.chain.load_multichain_config")
    def test_chain_status_command(
        self, mock_load_config, mock_chain_manager_class, mock_asyncio_run, runner
    ):
        """``chain status`` without a chain-id lists all chain statuses."""
        mock_chain = MagicMock()
        mock_chain.id = "chain-1"
        mock_chain.name = "Main Chain"
        mock_chain.type.value = "main"
        mock_chain.status.value = "active"
        mock_chain.block_height = 12345
        mock_chain.active_nodes = 3
        mock_asyncio_run.return_value = [mock_chain]

        from aitbc_cli.commands.chain import chain

        result = runner.invoke(chain, ["status"])

        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
