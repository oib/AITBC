"""
Script Commands Tests
Tests for script CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestScriptCommands:
    """Test script command group"""

    def test_script_group_exists(self):
        """Test that script command group exists"""
        from aitbc_cli.commands.script import script

        assert script is not None
        assert hasattr(script, "name")

    def test_script_group_name(self):
        """Test script group name"""
        from aitbc_cli.commands.script import script

        assert script.name == "script"

    def test_script_group_has_run_subcommand(self):
        """The ``run`` subcommand is registered on the script group."""
        from aitbc_cli.commands.script import script

        assert "run" in script.commands

    def test_script_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the script group."""
        from aitbc_cli.commands.script import script

        assert "list" in script.commands

    @patch("subprocess.run")
    def test_script_run_command(self, mock_run, runner):
        """``script run`` executes a script and returns its output."""
        mock_result = MagicMock()
        mock_result.stdout = "hello world"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.script import script

        result = runner.invoke(
            script,
            ["run", "--script-path", "/bin/echo", "--args", "hello world"],
        )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_script_run_command_with_args(self, mock_run, runner):
        """``script run --args`` passes arguments to the script."""
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        from aitbc_cli.commands.script import script

        result = runner.invoke(
            script,
            ["run", "--script-path", "/bin/echo", "--args", "arg1 arg2"],
        )

        assert result.exit_code == 0, result.output
        cmd = mock_run.call_args[0][0]
        assert "arg1" in cmd
        assert "arg2" in cmd

    def test_script_list_command(self, runner, tmp_path):
        """``script list`` lists available scripts from the scripts directory."""
        # Create a fake script file
        (tmp_path / "deploy.sh").write_text("#!/bin/bash\necho deploy")
        (tmp_path / "backup.sh").write_text("#!/bin/bash\necho backup")

        from aitbc_cli.commands.script import script

        result = runner.invoke(script, ["list", "--script-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "deploy.sh" in result.output
        assert "backup.sh" in result.output

    def test_script_list_command_nonexistent_dir(self, runner):
        """``script list`` with a non-existent directory aborts."""
        from aitbc_cli.commands.script import script

        result = runner.invoke(script, ["list", "--script-dir", "/nonexistent/path/12345"])

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
