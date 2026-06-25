"""
Genesis Commands Tests
Tests for genesis CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch, MagicMock

import pytest


class TestGenesisCommands:
    """Test genesis command group"""

    def test_genesis_group_exists(self):
        """Test that genesis command group exists"""
        from aitbc_cli.commands.genesis import genesis

        assert genesis is not None
        assert hasattr(genesis, "name")

    def test_genesis_group_name(self):
        """Test genesis group name"""
        from aitbc_cli.commands.genesis import genesis

        assert genesis.name == "genesis"

    def test_genesis_group_has_init_subcommand(self):
        """The ``init`` subcommand is registered on the genesis group."""
        from aitbc_cli.commands.genesis import genesis

        assert "init" in genesis.commands

    def test_genesis_group_has_verify_subcommand(self):
        """The ``verify`` subcommand is registered on the genesis group."""
        from aitbc_cli.commands.genesis import genesis

        assert "verify" in genesis.commands

    def test_genesis_group_has_info_subcommand(self):
        """The ``info`` subcommand is registered on the genesis group."""
        from aitbc_cli.commands.genesis import genesis

        assert "info" in genesis.commands

    @patch("aitbc_cli.commands.genesis.subprocess.run")
    def test_genesis_init_command(self, mock_run, runner):
        """``genesis init`` runs the genesis generation script via subprocess."""
        mock_result = MagicMock()
        mock_result.stdout = "Genesis block created successfully"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(
            genesis,
            ["init", "--chain-id", "test-chain", "--create-wallet"],
        )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        # Verify the command includes the chain-id.
        cmd_args = mock_run.call_args[0][0] if mock_run.call_args[0] else mock_run.call_args[1].get("args", [])
        assert "--chain-id" in cmd_args
        assert "test-chain" in cmd_args

    @patch("aitbc_cli.commands.genesis.subprocess.run")
    def test_genesis_init_command_with_force(self, mock_run, runner):
        """``genesis init --force`` passes the --force flag to the script."""
        mock_result = MagicMock()
        mock_result.stdout = "Genesis block created"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(
            genesis,
            ["init", "--chain-id", "test-chain", "--force"],
        )

        assert result.exit_code == 0, result.output
        cmd_args = mock_run.call_args[0][0] if mock_run.call_args[0] else mock_run.call_args[1].get("args", [])
        assert "--force" in cmd_args

    def test_genesis_verify_command_no_genesis(self, runner):
        """``genesis verify`` reports an error when genesis config is not found."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(genesis, ["verify", "--chain-id", "nonexistent-chain"])

        # The command calls error() and returns (exit 0) when the genesis
        # file is not found.
        assert result.exit_code == 0, result.output

    def test_genesis_info_command_no_genesis(self, runner):
        """``genesis info`` reports an error when genesis config is not found."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(genesis, ["info", "--chain-id", "nonexistent-chain"])

        # The command calls error() and returns (exit 0) when the genesis
        # file is not found.
        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
