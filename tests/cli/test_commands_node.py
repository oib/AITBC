"""
Node Commands Tests
Tests for node CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestNodeCommands:
    """Test node command group"""

    def test_node_group_exists(self):
        """Test that node command group exists"""
        from aitbc_cli.commands.node import node

        assert node is not None
        assert hasattr(node, "name")

    def test_node_group_name(self):
        """Test node group name"""
        from aitbc_cli.commands.node import node

        assert node.name == "node"

    def test_node_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the node group."""
        from aitbc_cli.commands.node import node

        assert "list" in node.commands

    def test_node_group_has_add_subcommand(self):
        """The ``add`` subcommand is registered on the node group."""
        from aitbc_cli.commands.node import node

        assert "add" in node.commands

    def test_node_group_has_remove_subcommand(self):
        """The ``remove`` subcommand is registered on the node group."""
        from aitbc_cli.commands.node import node

        assert "remove" in node.commands

    def test_node_group_has_island_subgroup(self):
        """The ``island`` subgroup is registered on the node group."""
        from aitbc_cli.commands.node import node

        assert "island" in node.commands

    def test_node_group_has_hub_subgroup(self):
        """The ``hub`` subgroup is registered on the node group."""
        from aitbc_cli.commands.node import node

        assert "hub" in node.commands

    def test_island_group_has_create_subcommand(self):
        """The ``create`` subcommand is registered on the island group."""
        from aitbc_cli.commands.node import node

        island = node.commands["island"]
        assert "create" in island.commands

    def test_island_group_has_list_islands_subcommand(self):
        """The ``list-islands`` subcommand is registered on the island group."""
        from aitbc_cli.commands.node import node

        island = node.commands["island"]
        assert "list-islands" in island.commands

    def test_island_group_has_leave_subcommand(self):
        """The ``leave`` subcommand is registered on the island group."""
        from aitbc_cli.commands.node import node

        island = node.commands["island"]
        assert "leave" in island.commands

    @patch("aitbc_cli.commands.node.main.load_multichain_config")
    def test_node_list_empty(self, mock_load_config, runner):
        """``node list`` shows 'No nodes configured' when config is empty."""
        mock_config = MagicMock()
        mock_config.nodes = {}
        mock_load_config.return_value = mock_config

        from aitbc_cli.commands.node import node

        result = runner.invoke(node, ["list"])

        assert result.exit_code == 0, result.output
        assert "No nodes configured" in result.output

    def test_node_island_list_islands(self, runner):
        """``node island list-islands`` returns hardcoded island data."""
        from aitbc_cli.commands.node import node

        result = runner.invoke(node, ["island", "list-islands"])

        assert result.exit_code == 0, result.output
        assert "Island" in result.output

    def test_node_island_create(self, runner):
        """``node island create`` creates a new island with provided details."""
        from aitbc_cli.commands.node import node

        result = runner.invoke(
            node,
            ["island", "create", "--island-id", "test-island", "--island-name", "test", "--chain-id", "test-chain"],
        )

        assert result.exit_code == 0, result.output
        assert "test-island" in result.output

    def test_node_island_leave(self, runner):
        """``node island leave`` confirms leaving an island."""
        from aitbc_cli.commands.node import node

        result = runner.invoke(node, ["island", "leave", "test-island"])

        assert result.exit_code == 0, result.output
        assert "Successfully left" in result.output

    def test_node_island_create_auto_generates_id(self, runner):
        """``node island create`` without --island-id auto-generates a UUID."""
        from aitbc_cli.commands.node import node

        result = runner.invoke(node, ["island", "create"])

        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
