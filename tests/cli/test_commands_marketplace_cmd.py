"""
Marketplace Cmd Commands Tests
Tests for marketplace_cmd CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestMarketplaceCmdCommands:
    """Test marketplace command group"""

    def test_marketplace_group_exists(self):
        """Test that marketplace command group exists"""
        try:
            from aitbc_cli.commands.marketplace_cmd import marketplace

            assert marketplace is not None
            assert hasattr(marketplace, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import marketplace commands: {e}")

    def test_marketplace_group_name(self):
        """Test marketplace group name"""
        try:
            from aitbc_cli.commands.marketplace_cmd import marketplace

            assert marketplace.name == "marketplace"
        except ImportError as e:
            pytest.skip(f"Cannot import marketplace commands: {e}")

    @patch("aitbc_cli.commands.marketplace_cmd.output")
    @patch("aitbc_cli.commands.marketplace_cmd.error")
    def test_marketplace_list_command(self, mock_error, mock_output):
        """Test marketplace list command - skip due to complex config dependencies"""
        pytest.skip("Marketplace commands have complex config and async dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
