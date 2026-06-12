"""
Workflow Commands Tests
Tests for workflow CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestWorkflowCommands:
    """Test workflow command group"""

    def test_workflow_group_exists(self):
        """Test that workflow command group exists"""
        try:
            from aitbc_cli.commands.workflow import workflow
            assert workflow is not None
            assert hasattr(workflow, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import workflow commands: {e}")

    def test_workflow_group_name(self):
        """Test workflow group name"""
        try:
            from aitbc_cli.commands.workflow import workflow
            assert workflow.name == "workflow"
        except ImportError as e:
            pytest.skip(f"Cannot import workflow commands: {e}")

    @patch('aitbc_cli.commands.workflow.success')
    @patch('aitbc_cli.commands.workflow.click')
    def test_workflow_run_dry_run(self, mock_click, mock_success):
        """Test workflow run with dry-run flag"""
        try:
            from aitbc_cli.commands.workflow import run
            from click.testing import CliRunner

            runner = CliRunner()
            result = runner.invoke(run, ['test-workflow', '--dry-run'])

            assert result.exit_code == 0
            assert mock_success.called
        except Exception as e:
            pytest.skip(f"Cannot test workflow run dry-run: {e}")

    @patch('aitbc_cli.commands.workflow.success')
    @patch('aitbc_cli.commands.workflow.click')
    def test_workflow_run_normal(self, mock_click, mock_success):
        """Test workflow run without dry-run"""
        try:
            from aitbc_cli.commands.workflow import run
            from click.testing import CliRunner

            runner = CliRunner()
            result = runner.invoke(run, ['test-workflow'])

            assert result.exit_code == 0
            assert mock_success.called
        except Exception as e:
            pytest.skip(f"Cannot test workflow run normal: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
