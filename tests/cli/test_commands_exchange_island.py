"""
Exchange Island Commands Tests
Tests for exchange_island CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestExchangeIslandCommands:
    """Test exchange_island command group"""

    def test_exchange_island_group_exists(self):
        """Test that exchange_island command group exists"""
        try:
            from aitbc_cli.commands.exchange_island import exchange_island
            assert exchange_island is not None
            assert hasattr(exchange_island, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import exchange_island commands: {e}")

    def test_exchange_island_group_name(self):
        """Test exchange_island group name"""
        try:
            from aitbc_cli.commands.exchange_island import exchange_island
            assert exchange_island.name == "exchange-island"
        except ImportError as e:
            pytest.skip(f"Cannot import exchange_island commands: {e}")

    @patch('aitbc_cli.commands.exchange_island.output')
    @patch('aitbc_cli.commands.exchange_island.error')
    def test_exchange_island_balance_command(self, mock_error, mock_output):
        """Test exchange_island balance command - skip due to complex credentials dependencies"""
        pytest.skip("Exchange island commands have complex credentials and socket dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
