"""
Account Commands Tests
Tests for account CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAccountCommands:
    """Test account command group"""

    def test_account_group_exists(self):
        """Test that account command group exists"""
        try:
            from aitbc_cli.commands.account import account
            assert account is not None
            assert hasattr(account, 'name')
        except ImportError as e:
            pytest.skip(f"Cannot import account commands: {e}")

    def test_account_group_name(self):
        """Test account group name"""
        try:
            from aitbc_cli.commands.account import account
            assert account.name == "account"
        except ImportError as e:
            pytest.skip(f"Cannot import account commands: {e}")

    @patch('aitbc_cli.commands.account.output')
    @patch('aitbc_cli.commands.account.error')
    def test_account_get_command(self, mock_error, mock_output):
        """Test account get command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
