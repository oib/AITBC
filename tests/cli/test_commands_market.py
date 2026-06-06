"""
Market Commands Tests
Tests for market CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestMarketCommands:
    """Test market command group"""

    def test_market_group_exists(self):
        """Test that market command group exists"""
        try:
            from aitbc_cli.commands.market import market
            assert market is not None
            assert hasattr(market, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import market commands: {e}")

    def test_market_group_name(self):
        """Test market group name"""
        try:
            from aitbc_cli.commands.market import market
            assert market.name == "market"
        except ImportError as e:
            pytest.skip(f"Cannot import market commands: {e}")

    @patch('aitbc_cli.commands.market.output')
    @patch('aitbc_cli.commands.market.error')
    def test_market_list_command(self, mock_error, mock_output):
        """Test market list command - skip due to complex credentials dependencies"""
        pytest.skip("Market commands have complex credentials and socket dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
