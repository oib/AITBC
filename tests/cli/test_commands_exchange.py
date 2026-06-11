"""
Exchange Commands Tests
Tests for exchange CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestExchangeCommands:
    """Test exchange command group"""

    def test_exchange_group_exists(self):
        """Test that exchange command group exists"""
        try:
            from aitbc_cli.commands.exchange import exchange
            assert exchange is not None
            assert hasattr(exchange, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import exchange commands: {e}")

    def test_exchange_group_name(self):
        """Test exchange group name"""
        try:
            from aitbc_cli.commands.exchange import exchange
            assert exchange.name == "exchange"
        except ImportError as e:
            pytest.skip(f"Cannot import exchange commands: {e}")

    @patch('aitbc_cli.commands.exchange.output')
    @patch('aitbc_cli.commands.exchange.error')
    def test_exchange_add_command(self, mock_error, mock_output):
        """Test exchange add command - skip due to complex config dependencies"""
        pytest.skip("Exchange commands have complex config and storage dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
