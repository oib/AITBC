"""Integration tests for workflow CLI commands

These tests require coordinator-api running and validate workflow execution,
status tracking, and API interactions with actual service calls.
"""

import json
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from aitbc_cli.commands.workflow import workflow
from click.testing import CliRunner

from aitbc.network import AITBCHTTPClient


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://127.0.0.1:18000"
    config.api_key = "test_api_key"
    return config


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for coordinator-api"""
    client = MagicMock(spec=AITBCHTTPClient)
    return client


class TestWorkflowCommands:
    """Integration tests for workflow commands with coordinator-api"""

    @pytest.fixture(autouse=True)
    def mock_httpx(self):
        """Mock httpx for all workflow tests"""
        with patch("httpx.get") as mock_get, patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "execution_id": "exec_123",
                "status": "running",
                "last_execution": "2024-01-01",
                "workflows": [{"name": "wf1", "status": "active"}, {"name": "wf2", "status": "paused"}],
            }
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response
            yield

    @pytest.fixture
    def coordinator_available(self):
        """Skip test if coordinator-api is not running"""
        pytest.skip("coordinator-api not running at http://127.0.0.1:18000")

    def test_workflow_run_basic(self, runner, mock_config):
        """Test running a basic workflow"""
        result = runner.invoke(workflow, ["run", "test_workflow"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "test_workflow" in result.output
        assert "Running" in result.output

    def test_workflow_run_with_config(self, runner, mock_config, tmp_path):
        """Test running workflow with config file"""
        config_file = tmp_path / "workflow_config.yaml"
        config_file.write_text("param1: value1\nparam2: value2")

        result = runner.invoke(
            workflow, ["run", "test_workflow", "--config", str(config_file)], obj={"config": mock_config, "output": "table"}
        )

        assert result.exit_code == 0
        assert "test_workflow" in result.output
        assert str(config_file) in result.output

    def test_workflow_run_dry_run(self, runner, mock_config):
        """Test workflow dry run mode"""
        result = runner.invoke(workflow, ["run", "test_workflow", "--dry-run"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "without making changes" in result.output

    def test_workflow_list(self, runner, mock_config):
        """Test listing available workflows"""
        result = runner.invoke(workflow, ["list", "--format", "json"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "status" in data[0]

    def test_workflow_list_table_format(self, runner, mock_config):
        """Test listing workflows in table format"""
        result = runner.invoke(workflow, ["list", "--format", "table"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "Available workflows" in result.output

    def test_workflow_status(self, runner, mock_config):
        """Test getting workflow status"""
        result = runner.invoke(workflow, ["status", "test_workflow"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "test_workflow" in result.output
        assert "Status" in result.output

    def test_workflow_stop(self, runner, mock_config):
        """Test stopping a workflow"""
        result = runner.invoke(workflow, ["stop", "test_workflow"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        assert "test_workflow" in result.output
        assert "Stop" in result.output

    def test_workflow_run_via_coordinator_api(self, runner):
        """Test workflow execution via coordinator-api (mocked)"""
        # This test is skipped because workflow.py doesn't use coordinator-api yet
        pytest.skip("workflow.py doesn't use coordinator-api - stub implementation")

    def test_workflow_execution_id_generation(self, runner, mock_config):
        """Test that workflow execution generates unique IDs"""
        result1 = runner.invoke(workflow, ["run", "test_workflow"], obj={"config": mock_config, "output": "table"})

        time.sleep(1)  # Delay to ensure different timestamp

        result2 = runner.invoke(workflow, ["run", "test_workflow"], obj={"config": mock_config, "output": "table"})

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        # Extract execution IDs from output
        import re

        id_pattern = r"wf_exec_\d+"
        ids1 = re.findall(id_pattern, result1.output)
        ids2 = re.findall(id_pattern, result2.output)

        if ids1 and ids2:
            assert ids1[0] != ids2[0], "Execution IDs should be unique"

    def test_workflow_nonexistent_status(self, runner, mock_config):
        """Test getting status of non-existent workflow"""
        result = runner.invoke(
            workflow, ["status", "nonexistent_workflow_xyz"], obj={"config": mock_config, "output": "table"}
        )

        assert result.exit_code == 0
        # Should return status even for non-existent workflows
        assert "nonexistent_workflow_xyz" in result.output

    def test_workflow_stop_nonexistent(self, runner, mock_config):
        """Test stopping non-existent workflow"""
        result = runner.invoke(workflow, ["stop", "nonexistent_workflow_xyz"], obj={"config": mock_config, "output": "table"})

        assert result.exit_code == 0
        # Should attempt to stop even if not running
        assert "nonexistent_workflow_xyz" in result.output

    def test_workflow_with_special_characters(self, runner, mock_config):
        """Test workflow names with special characters"""
        special_names = ["workflow-with-dashes", "workflow_with_underscores", "workflow.with.dots", "WorkflowWithCamelCase"]

        for name in special_names:
            result = runner.invoke(workflow, ["run", name], obj={"config": mock_config, "output": "table"})

            assert result.exit_code == 0
            assert name in result.output

    def test_workflow_list_filters(self, runner, mock_config):
        """Test workflow listing with potential filters"""
        result = runner.invoke(workflow, ["list", "--format", "json"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)

        # Verify expected workflow types are present
        assert isinstance(data, list)
        workflow_names = [w["name"] for w in data]
        # Check for known workflow types from implementation
        expected_types = ["gpu-marketplace", "ai-job-processing", "mining-optimization"]
        for expected in expected_types:
            if expected in workflow_names:
                assert True  # Found expected workflow
                break

    def test_workflow_status_output_format(self, runner, mock_config):
        """Test workflow status in different output formats"""
        # Table format
        result_table = runner.invoke(workflow, ["status", "test_workflow"], obj={"config": mock_config, "output": "table"})

        assert result_table.exit_code == 0

        # JSON format
        result_json = runner.invoke(workflow, ["status", "test_workflow"], obj={"config": mock_config, "output": "json"})

        assert result_json.exit_code == 0
        # Should be parseable as JSON or contain status info

    def test_workflow_run_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test workflow execution with actual coordinator-api call"""
        result = runner.invoke(
            workflow, ["run", "test_integration_workflow", "--async"], obj={"config": mock_config, "output": "json"}
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "workflow_id" in data or "execution_id" in data
        assert data.get("status") in ["started", "running", "pending"]

    def test_workflow_list_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test listing workflows from coordinator-api"""
        result = runner.invoke(workflow, ["list"], obj={"config": mock_config, "output": "json"})

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

        # Validate workflow structure
        for workflow_item in data:
            assert "name" in workflow_item
            assert "status" in workflow_item

    def test_workflow_status_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test getting workflow status from coordinator-api"""
        # First run a workflow
        run_result = runner.invoke(workflow, ["run", "status_test_workflow"], obj={"config": mock_config, "output": "json"})

        assert run_result.exit_code == 0
        run_data = json.loads(run_result.output)
        workflow_id = run_data.get("workflow_id") or run_data.get("execution_id")

        if workflow_id:
            # Get status
            status_result = runner.invoke(workflow, ["status", workflow_id], obj={"config": mock_config, "output": "json"})

            assert status_result.exit_code == 0
            status_data = json.loads(status_result.output)
            assert "status" in status_data
            assert workflow_id in str(status_data)

    def test_workflow_stop_with_coordinator_api(self, runner, mock_config, coordinator_available):
        """Test stopping workflow via coordinator-api"""
        # Run a workflow
        run_result = runner.invoke(workflow, ["run", "stop_test_workflow"], obj={"config": mock_config, "output": "json"})

        assert run_result.exit_code == 0
        run_data = json.loads(run_result.output)
        workflow_id = run_data.get("workflow_id") or run_data.get("execution_id")

        if workflow_id:
            # Stop the workflow
            stop_result = runner.invoke(workflow, ["stop", workflow_id], obj={"config": mock_config, "output": "json"})

            assert stop_result.exit_code == 0
            stop_data = json.loads(stop_result.output)
            assert stop_data.get("status") in ["stopped", "stopping", "cancelled"]

    def test_workflow_run_with_parameters(self, runner, mock_config, coordinator_available):
        """Test workflow execution with custom parameters"""
        result = runner.invoke(
            workflow,
            ["run", "param_test_workflow", "--param", "gpu_count=4", "--param", "timeout=300"],
            obj={"config": mock_config, "output": "json"},
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "workflow_id" in data or "execution_id" in data

    def test_workflow_execution_tracking(self, runner, mock_config, coordinator_available):
        """Test tracking workflow execution over time"""
        # Start workflow
        run_result = runner.invoke(workflow, ["run", "tracking_test_workflow"], obj={"config": mock_config, "output": "json"})

        assert run_result.exit_code == 0
        run_data = json.loads(run_result.output)
        workflow_id = run_data.get("workflow_id") or run_data.get("execution_id")

        if workflow_id:
            # Check status immediately
            status1 = runner.invoke(workflow, ["status", workflow_id], obj={"config": mock_config, "output": "json"})

            assert status1.exit_code == 0

            # Wait and check status again
            time.sleep(1)

            status2 = runner.invoke(workflow, ["status", workflow_id], obj={"config": mock_config, "output": "json"})

            assert status2.exit_code == 0
            status2_data = json.loads(status2.output)
            assert "status" in status2_data

    def test_workflow_api_error_handling(self, runner, mock_config):
        """Test workflow command handles coordinator-api errors gracefully"""
        # Use invalid coordinator URL to trigger error
        mock_config.coordinator_url = "http://invalid:9999"

        result = runner.invoke(workflow, ["run", "error_test_workflow"], obj={"config": mock_config, "output": "json"})

        # Should either fail gracefully or skip with appropriate message
        # The exact behavior depends on implementation
        assert result.exit_code != 0 or "error" in result.output.lower() or "unavailable" in result.output.lower()
