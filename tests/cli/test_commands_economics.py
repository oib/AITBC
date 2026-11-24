"""
Economics Commands Tests
Tests for economics CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from unittest.mock import MagicMock

import pytest


def _dead_fleet(monkeypatch):
    """Point every economics probe at 'not configured'.

    The commands resolve live service URLs from the host config — on a
    provisioned node a source answers ``ok`` and the honest-refusal path
    never runs (#2940). Empty URLs record 'not configured' in ``sources``.
    """
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    config = MagicMock()
    for attr in (
        "coordinator_api_url",
        "market_service_url",
        "hub_discovery_url",
        "exchange_service_url",
        "blockchain_rpc_url",
        "hub_blockchain_rpc_url",
    ):
        setattr(config, attr, "")
    config.timeout = 1
    config.api_key = None
    monkeypatch.setattr("aitbc_cli.commands.economics.get_config", lambda: config)


class TestEconomicsCommands:
    """Test economics command group"""

    def test_economics_group_exists(self):
        """Test that economics command group exists"""
        from aitbc_cli.commands.economics import economics

        assert economics is not None
        assert hasattr(economics, "name")

    def test_economics_group_name(self):
        """Test economics group name"""
        from aitbc_cli.commands.economics import economics

        assert economics.name == "economics"

    def test_economics_group_has_distributed_subcommand(self):
        """The ``distributed`` subcommand is registered on the economics group."""
        from aitbc_cli.commands.economics import economics

        assert "distributed" in economics.commands

    def test_economics_group_has_model_subcommand(self):
        """The ``model`` subcommand is registered on the economics group."""
        from aitbc_cli.commands.economics import economics

        assert "model" in economics.commands

    def test_economics_group_has_market_subcommand(self):
        """The ``market`` subcommand is registered on the economics group."""
        from aitbc_cli.commands.economics import economics

        assert "market" in economics.commands

    def test_economics_distributed_command(self, runner, monkeypatch):
        """``economics distributed`` refuses honestly with no live backends."""
        from aitbc_cli.commands.economics import economics

        _dead_fleet(monkeypatch)
        result = runner.invoke(economics, ["distributed"])

        assert result.exit_code != 0
        assert "No live" in result.output

    def test_economics_distributed_command_with_cost_optimize(self, runner, monkeypatch):
        """``economics distributed --cost-optimize`` parses and still refuses honestly."""
        from aitbc_cli.commands.economics import economics

        _dead_fleet(monkeypatch)
        result = runner.invoke(economics, ["distributed", "--cost-optimize"])

        assert result.exit_code != 0
        assert "No live" in result.output

    def test_economics_model_command(self, runner, monkeypatch):
        """``economics model`` refuses honestly with no live backends."""
        from aitbc_cli.commands.economics import economics

        _dead_fleet(monkeypatch)
        result = runner.invoke(economics, ["model"])

        assert result.exit_code != 0
        assert "No live" in result.output

    def test_economics_market_command(self, runner, monkeypatch):
        """``economics market`` refuses honestly with no live backends."""
        from aitbc_cli.commands.economics import economics

        _dead_fleet(monkeypatch)
        result = runner.invoke(economics, ["market"])

        assert result.exit_code != 0
        assert "No live" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
