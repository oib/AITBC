"""Tests for aitbc ai submit --wait."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestAISubmitWait:
    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_submit_wait_polls_until_completed(self, mock_get_config, mock_http_class, runner, mock_config):
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"job_id": "job_123", "status": "queued"}
        mock_client.get.side_effect = [
            {"state": "QUEUED", "job_id": "job_123"},
            {"state": "RUNNING", "job_id": "job_123"},
            {"state": "COMPLETED", "job_id": "job_123", "payment_status": "released"},
            {"result": "hello", "receipt": {"tx_hash": "0xabc"}},
        ]

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            [
                "submit",
                "--wait",
                "--timeout",
                "10",
                "--poll-interval",
                "0.1",
                "--prompt",
                "hello",
            ],
        )

        assert result.exit_code == 0, result.output
        assert mock_client.get.call_count >= 3
        assert mock_client.get.call_args_list[-1][0][0] == "/v1/jobs/job_123/result"
        assert "COMPLETED" in result.output

    @patch("aitbc_cli.commands.ai.AITBCHTTPClient")
    @patch("aitbc_cli.commands.ai.get_config")
    def test_submit_wait_failed_state(self, mock_get_config, mock_http_class, runner, mock_config):
        mock_get_config.return_value = mock_config
        mock_client = mock_http_class.return_value
        mock_client.post.return_value = {"job_id": "job_123", "status": "queued"}
        mock_client.get.side_effect = [
            {"state": "QUEUED"},
            {"state": "FAILED", "job_id": "job_123", "error": "out of gas"},
        ]

        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            ["submit", "--wait", "--timeout", "5", "--poll-interval", "0.1", "--prompt", "hello"],
        )

        assert result.exit_code == 0, result.output
        assert "FAILED" in result.output
