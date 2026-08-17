"""Tests for the `aitbc update` command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_update_command_is_registered():
    """``update`` is a top-level command on the CLI."""
    from aitbc_cli.core.main import cli

    assert "update" in cli.commands


class TestUpdateCommand:
    """Test `aitbc update` subprocess invocations."""

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_update_pulls_git_and_runs_update_sh(self, mock_run, runner):
        """The command runs `git pull --ff-only origin main` then `bash update.sh`."""
        from aitbc_cli.commands.update import update

        mock_run.return_value = Mock(returncode=0)

        result = runner.invoke(update, [])

        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 2

        git_call, bash_call = mock_run.call_args_list
        assert git_call.args[0] == ["git", "pull", "--ff-only", "origin", "main"]
        assert bash_call.args[0][0] == "bash"
        assert "scripts/deployment/update.sh" in bash_call.args[0][1]

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_update_aborts_when_git_pull_fails(self, mock_run, runner):
        """A non-zero `git pull` stops before running update.sh."""
        from aitbc_cli.commands.update import update

        mock_run.side_effect = [Mock(returncode=1), Mock(returncode=0)]

        result = runner.invoke(update, [])

        assert result.exit_code != 0
        assert mock_run.call_count == 1
