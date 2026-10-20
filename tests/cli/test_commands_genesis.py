"""
Genesis Commands Tests
Tests for genesis CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

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

    def test_genesis_init_password_without_create_wallet_exits_nonzero(self, runner):
        """CLEAN-1: --password* without --create-wallet is a usage error
        that must exit non-zero (it used to only print and return 0)."""
        from aitbc_cli.commands.genesis import genesis

        for extra in (["--password", "secret"], ["--password-stdin"]):
            result = runner.invoke(genesis, ["init", "--chain-id", "test-chain"] + extra)
            assert result.exit_code != 0, extra

    @patch("aitbc_cli.commands.genesis.subprocess.run")
    def test_genesis_init_command(self, mock_run, runner, tmp_path):
        """``genesis init`` is retired: it refuses before reading or writing
        any file and names the only builder (GAP-GENESIS-INIT-1)."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(
            genesis,
            ["init", "--chain-id", "test-chain", "--create-wallet"],
            obj={"output_format": "table"},
        )

        assert result.exit_code == 1, result.output
        assert "retired" in result.output
        assert "scripts/ops/build-genesis.py" in result.output
        assert "bc2-consumers.md" in result.output
        mock_run.assert_not_called()
        assert list(tmp_path.iterdir()) == []

    @patch("aitbc_cli.commands.genesis.subprocess.run")
    def test_genesis_init_command_with_force(self, mock_run, runner):
        """``genesis init --force`` hits the same refusal — no flag revives it."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(
            genesis,
            ["init", "--chain-id", "test-chain", "--force"],
            obj={"output_format": "table"},
        )

        assert result.exit_code == 1, result.output
        assert "build-genesis.py" in result.output
        mock_run.assert_not_called()

    def test_genesis_init_help_still_works(self, runner):
        """Retirement keeps --help: options and the retired note render."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(genesis, ["init", "--help"])
        assert result.exit_code == 0, result.output
        assert "Retired" in result.output
        assert "build-genesis" in result.output
        assert "--create-wallet" in result.output

    def test_genesis_verify_command_no_genesis(self, runner):
        """``genesis verify`` refuses when the genesis config is missing."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(genesis, ["verify", "--chain-id", "nonexistent-chain"])

        # Deliberate since dcfa58039: error() then ctx.exit(1) — no genesis
        # file is a failure, not a report.
        assert result.exit_code == 1, result.output
        assert "Genesis config not found" in result.output

    def test_genesis_info_command_no_genesis(self, runner):
        """``genesis info`` refuses when the genesis config is missing."""
        from aitbc_cli.commands.genesis import genesis

        result = runner.invoke(genesis, ["info", "--chain-id", "nonexistent-chain"])

        # Same deliberate exit-1 path as verify (dcfa58039).
        assert result.exit_code == 1, result.output
        assert "Genesis config not found" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
