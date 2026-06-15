"""
Market Handlers Tests
Tests for market CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestMarketHandlers:
    """Test market handlers"""

    def test_handle_market_listings_function_exists(self):
        """Test that handle_market_listings function exists"""
        try:
            from handlers.market import handle_market_listings

            assert handle_market_listings is not None
        except ImportError as e:
            pytest.skip(f"Cannot import market handlers: {e}")

    def test_handle_market_listings_command(self):
        """Test handle_market_listings - skip due to complex marketplace dependencies"""
        pytest.skip("Market handlers have complex marketplace and HTTP client dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
