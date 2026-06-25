"""
Economics Commands Tests
Tests for economics CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

import pytest


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

    def test_economics_distributed_command(self, runner):
        """``economics distributed`` outputs simulated optimization data."""
        from aitbc_cli.commands.economics import economics

        result = runner.invoke(economics, ["distributed"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    def test_economics_distributed_command_with_cost_optimize(self, runner):
        """``economics distributed --cost-optimize`` enables cost optimization."""
        from aitbc_cli.commands.economics import economics

        result = runner.invoke(economics, ["distributed", "--cost-optimize"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    def test_economics_model_command(self, runner):
        """``economics model`` outputs simulated modeling data."""
        from aitbc_cli.commands.economics import economics

        result = runner.invoke(economics, ["model"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output

    def test_economics_market_command(self, runner):
        """``economics market`` outputs simulated market analysis data."""
        from aitbc_cli.commands.economics import economics

        result = runner.invoke(economics, ["market"])

        assert result.exit_code == 0, result.output
        assert "simulated" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
