"""
Coin Requests Commands Tests
Tests for coin_requests CLI commands
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestCoinRequestsCommands:
    """Test coin_requests command group"""

    def test_coin_requests_group_exists(self):
        """Test that coin_requests command group exists"""
        pytest.skip("Coin requests commands have complex Hermes service and DB dependencies")

    def test_coin_requests_group_name(self):
        """Test coin_requests group name"""
        pytest.skip("Coin requests commands have complex Hermes service and DB dependencies")

    def test_coin_requests_list_command(self):
        """Test coin_requests list command - skip due to complex Hermes service dependencies"""
        pytest.skip("Coin requests commands have complex Hermes service and DB dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
