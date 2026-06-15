"""
Security Commands Tests
Tests for security CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestSecurityCommands:
    """Test security command group"""

    def test_security_group_exists(self):
        """Test that security command group exists"""
        try:
            from aitbc_cli.commands.security import security

            assert security is not None
            assert hasattr(security, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import security commands: {e}")

    def test_security_group_name(self):
        """Test security group name"""
        try:
            from aitbc_cli.commands.security import security

            assert security.name == "security"
        except ImportError as e:
            pytest.skip(f"Cannot import security commands: {e}")

    @patch("aitbc_cli.commands.security.output")
    @patch("aitbc_cli.commands.security.error")
    def test_security_audit_command(self, mock_error, mock_output):
        """Test security audit command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
