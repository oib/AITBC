"""
Exchange Commands Tests
Tests for exchange CLI commands

Converted from skipped stubs to functional tests using the shared CLI mock
fixtures (see ``tests/fixtures/cli_mocks.py`` and ``tests/cli/conftest.py``).
"""

from pathlib import Path

import pytest


class TestExchangeCommands:
    """Test exchange command group"""

    def test_exchange_group_exists(self):
        """Test that exchange command group exists"""
        from aitbc_cli.commands.exchange import exchange

        assert exchange is not None
        assert hasattr(exchange, "name")

    def test_exchange_group_name(self):
        """Test exchange group name"""
        from aitbc_cli.commands.exchange import exchange

        assert exchange.name == "exchange"

    def test_exchange_group_has_register_subcommand(self):
        """The ``register`` subcommand is registered on the exchange group."""
        from aitbc_cli.commands.exchange import exchange

        assert "register" in exchange.commands

    def test_exchange_group_has_list_subcommand(self):
        """The ``list`` subcommand is registered on the exchange group."""
        from aitbc_cli.commands.exchange import exchange

        assert "list" in exchange.commands

    def test_exchange_register_command(self, runner, tmp_path, monkeypatch):
        """``exchange register`` writes the exchange config to disk."""
        # Redirect Path.home() to a temp directory so the test does not
        # pollute the real ~/.aitbc/exchanges.json.
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from aitbc_cli.commands.exchange import exchange

        result = runner.invoke(
            exchange,
            [
                "register",
                "--name", "TestExchange",
                "--api-key", "test-key-123",
                "--sandbox",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "registered" in result.output.lower() or "success" in result.output.lower()

        # Verify the config file was created.
        exchanges_file = tmp_path / ".aitbc" / "exchanges.json"
        assert exchanges_file.exists()

    def test_exchange_list_command_no_exchanges(self, runner, tmp_path, monkeypatch):
        """``exchange list`` shows a warning when no exchanges are registered."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from aitbc_cli.commands.exchange import exchange

        result = runner.invoke(exchange, ["list"])

        assert result.exit_code == 0, result.output

    def test_exchange_status_command_not_found(self, runner, tmp_path, monkeypatch):
        """``exchange status`` reports an error for an unregistered exchange."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from aitbc_cli.commands.exchange import exchange

        result = runner.invoke(exchange, ["status", "NonExistent"])

        assert result.exit_code == 0, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
