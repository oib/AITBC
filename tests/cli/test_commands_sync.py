"""
Sync Commands Tests
Tests for sync CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSyncCommands:
    """Test sync command group"""

    def test_sync_group_exists(self):
        """Test that sync command group exists"""
        from aitbc_cli.commands.sync import sync

        assert sync is not None
        assert hasattr(sync, "name")

    def test_sync_group_name(self):
        """Test sync group name"""
        from aitbc_cli.commands.sync import sync

        assert sync.name == "sync"

    def test_sync_group_has_bulk_subcommand(self):
        """The ``bulk`` subcommand is registered on the sync group."""
        from aitbc_cli.commands.sync import sync

        assert "bulk" in sync.commands

    @patch("subprocess.run")
    def test_sync_bulk_command(self, mock_run, runner):
        """``sync bulk`` invokes the sync_cli.py script via subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(
            sync,
            ["bulk", "--source", "http://leader:8202", "--import-url", "http://local:8202"],
        )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "sync_cli.py" in cmd[1]

    @patch("subprocess.run")
    def test_sync_bulk_command_with_batch_size(self, mock_run, runner):
        """``sync bulk --batch-size`` forwards the batch size to sync_cli.py."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(sync, ["bulk", "--batch-size", "200"])

        assert result.exit_code == 0, result.output
        cmd = mock_run.call_args[0][0]
        assert "200" in cmd

    @patch("subprocess.run")
    def test_sync_bulk_command_failure(self, mock_run, runner):
        """``sync bulk`` aborts when sync_cli.py returns non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        from aitbc_cli.commands.sync import sync

        result = runner.invoke(sync, ["bulk"])

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
