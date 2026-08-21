"""Tests for the aitbc pool-hub CLI commands."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestPoolHubCommands:
    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_status_shows_miners_online(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {
            "status": "ok",
            "db": True,
            "redis": True,
            "miners_online": 1,
        }

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code == 0, result.output
        assert "miners_online" in result.output
        assert "1" in result.output

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_status_uses_localhost_8210_by_default(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "ok", "miners_online": 0}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code == 0, result.output
        call = mock_client.get.call_args
        assert call[0][0] == "/health"
        assert call.kwargs.get("base_url") is None
        assert mock_http_class.call_args.kwargs["base_url"] == "http://localhost:8210"

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_status_allows_url_override(self, mock_http_class, runner):
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "ok", "miners_online": 2}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["status", "--pool-hub-url", "http://aitbc3:8210"])

        assert result.exit_code == 0, result.output
        assert mock_http_class.call_args.kwargs["base_url"] == "http://aitbc3:8210"
