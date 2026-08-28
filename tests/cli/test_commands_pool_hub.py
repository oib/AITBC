"""
Pool Hub Commands Tests
Tests for pool_hub CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import patch

import pytest


class TestPoolHubCommands:
    """Test pool_hub command group"""

    def test_pool_hub_group_exists(self):
        """Test that pool_hub command group exists"""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert pool_hub is not None
        assert hasattr(pool_hub, "name")

    def test_pool_hub_group_name(self):
        """Test pool_hub group name"""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert pool_hub.name == "pool-hub"

    def test_pool_hub_group_has_status_subcommand(self):
        """The ``status`` subcommand is registered on the pool_hub group."""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert "status" in pool_hub.commands

    def test_pool_hub_group_has_sla_subcommand(self):
        """The ``sla`` subcommand is registered on the pool_hub group."""
        from aitbc_cli.commands.pool_hub import pool_hub

        assert "sla" in pool_hub.commands

    def test_pool_hub_commands_target_the_pool_hub_port(self):
        """Click option default is unset; hub vs follower URL is resolved at invoke time."""
        from aitbc_cli.commands import pool_hub as pool_hub_mod
        from aitbc_cli.commands.pool_hub import pool_hub

        for name in ("status", "sla"):
            option = next(p for p in pool_hub.commands[name].params if p.name == "pool_hub_url")
            assert option.default is None, f"{name} points at {option.default}"
        assert pool_hub_mod.DEFAULT_POOL_HUB_URL == "http://localhost:8210"

    def test_default_pool_hub_url_uses_localhost_on_hub(self, monkeypatch):
        from aitbc_cli.commands.pool_hub import _default_pool_hub_url

        monkeypatch.setenv("NODE_ROLE", "hub")
        assert _default_pool_hub_url() == "http://localhost:8210"

    def test_default_pool_hub_url_uses_hub_url_on_follower(self, monkeypatch):
        from aitbc_cli.commands.pool_hub import _default_pool_hub_url

        monkeypatch.delenv("HUB_POOL_HUB_URL", raising=False)
        monkeypatch.delenv("POOL_HUB_URL", raising=False)
        monkeypatch.delenv("NODE_ROLE", raising=False)
        monkeypatch.setenv("HUB_DISCOVERY_URL", "https://hub.example.net")
        monkeypatch.setattr("aitbc_cli.commands.pool_hub._is_hub_node", lambda: False)
        assert _default_pool_hub_url() == "http://hub.example.net/pool-hub"

    def test_default_pool_hub_url_falls_back_to_localhost_without_hub_config(self, monkeypatch):
        from aitbc_cli.commands.pool_hub import _default_pool_hub_url

        monkeypatch.delenv("HUB_POOL_HUB_URL", raising=False)
        monkeypatch.delenv("POOL_HUB_URL", raising=False)
        monkeypatch.setattr("aitbc.config.hub.hub_discovery_host", lambda: None)
        assert _default_pool_hub_url() == "http://localhost:8210"

    def test_default_pool_hub_url_uses_explicit_env(self, monkeypatch):
        from aitbc_cli.commands.pool_hub import _default_pool_hub_url

        monkeypatch.setenv("POOL_HUB_URL", "https://hub.example.net/pool-hub")
        assert _default_pool_hub_url() == "https://hub.example.net/pool-hub"

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_status_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``pool-hub status`` reads /health — a route Pool Hub actually serves."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "ok", "db": True, "redis": True, "miners_online": 3}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert mock_client.get.call_args[0][0] == "/health"

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_status_aborts_on_network_error(self, mock_http_class, runner):
        """``pool-hub status`` aborts on NetworkError rather than inventing pool counts."""
        from aitbc_cli.commands.pool_hub import pool_hub
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(pool_hub, ["status"])

        assert result.exit_code != 0
        assert "simulated" not in result.output

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_command(self, mock_http_class, runner, mock_blockchain_rpc):
        """``pool-hub sla`` reads /v1/sla/status — a route Pool Hub actually serves."""
        mock_client = mock_http_class.return_value
        mock_client.get.return_value = {"status": "healthy", "active_violations": 0}

        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["sla"])

        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        assert mock_client.get.call_args[0][0] == "/v1/sla/status"

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_with_pool_id_is_rejected(self, mock_http_class, runner):
        """``--pool-id`` is refused: Pool Hub reports SLA per miner and cannot filter by pool."""
        from aitbc_cli.commands.pool_hub import pool_hub

        result = runner.invoke(pool_hub, ["sla", "--pool-id", "my-pool"])

        assert result.exit_code != 0
        # It must not answer with unfiltered data as though the filter had applied.
        mock_http_class.return_value.get.assert_not_called()

    @patch("aitbc_cli.commands.pool_hub.AITBCHTTPClient")
    def test_pool_hub_sla_aborts_on_network_error(self, mock_http_class, runner):
        """``pool-hub sla`` aborts on NetworkError rather than inventing 100% compliance."""
        from aitbc_cli.commands.pool_hub import pool_hub
        from aitbc_cli.utils.http_client import NetworkError

        mock_client = mock_http_class.return_value
        mock_client.get.side_effect = NetworkError("connection refused")

        result = runner.invoke(pool_hub, ["sla"])

        assert result.exit_code != 0
        assert "simulated" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
