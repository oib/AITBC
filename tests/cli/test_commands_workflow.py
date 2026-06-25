"""
Workflow Commands Tests
Tests for workflow CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWorkflowCommands:
    """Test workflow command group"""

    def test_workflow_group_exists(self):
        """Test that workflow command group exists"""
        from aitbc_cli.commands.workflow import workflow

        assert workflow is not None
        assert hasattr(workflow, "name")

    def test_workflow_group_name(self):
        """Test workflow group name"""
        from aitbc_cli.commands.workflow import workflow

        assert workflow.name == "workflow"

    def test_workflow_group_has_run_subcommand(self):
        """The ``run`` subcommand is registered on the workflow group."""
        from aitbc_cli.commands.workflow import workflow

        assert "run" in workflow.commands

    def test_workflow_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the workflow group."""
        from aitbc_cli.commands.workflow import workflow

        assert "list" in workflow.commands

    def test_workflow_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the workflow group."""
        from aitbc_cli.commands.workflow import workflow

        assert "status" in workflow.commands

    def test_workflow_group_has_stop_subcommand(self):
        """The ``stop`` subcommand is registered on the workflow group."""
        from aitbc_cli.commands.workflow import workflow

        assert "stop" in workflow.commands

    def test_workflow_list_command(self, runner):
        """``workflow list`` lists available workflows."""
        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["list"])

        assert result.exit_code == 0, result.output
        assert "gpu-marketplace" in result.output
        assert "ai-job-processing" in result.output

    def test_workflow_list_json_format(self, runner):
        """``workflow list --format json`` outputs JSON."""
        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["list", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert "gpu-marketplace" in result.output

    @patch("aitbc_cli.commands.workflow.get_config")
    def test_workflow_run_dry_run(self, mock_get_config, runner):
        """``workflow run --dry-run`` prints a dry-run message without executing."""
        mock_config = mock_get_config.return_value
        mock_config.coordinator_url = "http://localhost:8203"

        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["run", "test-workflow", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output
        assert "test-workflow" in result.output

    @patch("httpx.post")
    @patch("aitbc_cli.commands.workflow.get_config")
    def test_workflow_run_normal(self, mock_get_config, mock_post, runner):
        """``workflow run`` submits the workflow to the coordinator API."""
        mock_config = mock_get_config.return_value
        mock_config.coordinator_url = "http://localhost:8203"
        mock_config.coordinator_api_key = "test-key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"execution_id": "exec-123", "status": "Running"}
        mock_post.return_value = mock_response

        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["run", "test-workflow"])

        assert result.exit_code == 0, result.output
        assert "exec-123" in result.output
        mock_post.assert_called_once()

    @patch("httpx.post")
    @patch("aitbc_cli.commands.workflow.get_config")
    def test_workflow_run_failure(self, mock_get_config, mock_post, runner):
        """``workflow run`` reports an error when the coordinator returns non-200."""
        mock_config = mock_get_config.return_value
        mock_config.coordinator_url = "http://localhost:8203"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["run", "test-workflow"])

        assert result.exit_code == 0, result.output
        assert "Failed" in result.output

    @patch("httpx.get")
    @patch("aitbc_cli.commands.workflow.get_config")
    def test_workflow_status_command(self, mock_get_config, mock_get, runner):
        """``workflow status`` fetches execution status from the coordinator API."""
        mock_config = mock_get_config.return_value
        mock_config.coordinator_url = "http://localhost:8203"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "running",
            "workflow_id": "test-workflow",
            "current_step": 2,
            "total_steps": 5,
        }
        mock_get.return_value = mock_response

        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["status", "exec-123"])

        assert result.exit_code == 0, result.output
        assert "running" in result.output
        mock_get.assert_called_once()

    @patch("httpx.post")
    @patch("aitbc_cli.commands.workflow.get_config")
    def test_workflow_stop_command(self, mock_get_config, mock_post, runner):
        """``workflow stop`` cancels a running workflow via the coordinator API."""
        mock_config = mock_get_config.return_value
        mock_config.coordinator_url = "http://localhost:8203"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        from aitbc_cli.commands.workflow import workflow

        result = runner.invoke(workflow, ["stop", "exec-123"])

        assert result.exit_code == 0, result.output
        assert "Cancelled" in result.output
        mock_post.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
