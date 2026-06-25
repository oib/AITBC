"""
AI Commands Tests
Tests for ai CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestAICommands:
    """Test ai command group"""

    def test_ai_group_exists(self):
        """Test that ai command group exists"""
        from aitbc_cli.commands.ai import ai

        assert ai is not None
        assert hasattr(ai, "name")

    def test_ai_group_name(self):
        """Test ai group name"""
        from aitbc_cli.commands.ai import ai

        assert ai.name == "ai"

    def test_ai_group_has_submit_subcommand(self):
        """The ``submit`` subcommand is registered on the ai group."""
        from aitbc_cli.commands.ai import ai

        assert "submit" in ai.commands

    def test_ai_group_has_jobs_subcommand(self):
        """The ``jobs`` subcommand is registered on the ai group."""
        from aitbc_cli.commands.ai import ai

        assert "jobs" in ai.commands

    def test_ai_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the ai group."""
        from aitbc_cli.commands.ai import ai

        assert "status" in ai.commands

    def test_ai_group_has_results_subcommand(self):
        """The ``results`` subcommand is registered on the ai group."""
        from aitbc_cli.commands.ai import ai

        assert "results" in ai.commands

    def test_ai_group_has_service_group(self):
        """The ``service`` subgroup is registered on the ai group."""
        from aitbc_cli.commands.ai import ai

        assert "service" in ai.commands

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_submit_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai submit`` posts the job payload to the coordinator."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"job_id": "job_test_123", "status": "queued"}

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            [
                "submit",
                "--wallet", "test-wallet",
                "--type", "inference",
                "--prompt", "Hello world",
                "--payment", "5.0",
                "--coordinator-url", "http://coordinator:8006",
            ],
        )

        assert result.exit_code == 0, result.output
        mock_client.post.assert_called_once()
        posted_path = mock_client.post.call_args[0][0]
        posted_body = mock_client.post.call_args.kwargs.get("json")
        assert "/api/v1/jobs" in posted_path
        assert posted_body["job_type"] == "inference"
        assert posted_body["prompt"] == "Hello world"
        assert posted_body["payment"] == 5.0
        assert "job_test_123" in result.output

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_jobs_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai jobs`` lists jobs from the coordinator."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"items": [{"job_id": "j1"}, {"job_id": "j2"}]}

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(ai, ["jobs", "--limit", "2", "--coordinator-url", "http://coordinator:8006"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        _, kwargs = mock_client.get.call_args
        assert kwargs.get("params", {}).get("limit") == 2

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_status_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai status`` fetches a single job's status."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"job_id": "job_test_123", "state": "completed"}

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            ["status", "--job-id", "job_test_123", "--coordinator-url", "http://coordinator:8006"],
        )

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert "/api/v1/jobs/job_test_123" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_status_requires_job_id(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai status`` without a job id aborts."""
        mock_get_config.return_value = mock_config

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(ai, ["status", "--coordinator-url", "http://coordinator:8006"])

        assert result.exit_code != 0

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_results_command(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai results`` fetches job results."""
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"job_id": "job_test_123", "result": "ok"}

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            ["results", "--job-id", "job_test_123", "--coordinator-url", "http://coordinator:8006"],
        )

        assert result.exit_code == 0, result.output
        assert "/api/v1/jobs/job_test_123/results" in mock_client.get.call_args[0][0]

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_ai_submit_network_error_aborts(self, mock_get_config, mock_http_class, runner, mock_config):
        """``ai submit`` aborts on a NetworkError."""
        from aitbc_cli.commands.ai import ai
        from aitbc_cli.utils.http_client import NetworkError

        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = NetworkError("connection refused")

        result = runner.invoke(
            ai,
            ["submit", "--coordinator-url", "http://coordinator:8006", "--prompt", "x"],
        )

        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
