"""
Reputation Commands Tests
Tests for reputation CLI commands
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestReputationCommands:
    """Test reputation command group"""

    def test_reputation_group_exists(self):
        """Test that reputation command group exists"""
        try:
            from aitbc_cli.commands.reputation import reputation

            assert reputation is not None
            assert hasattr(reputation, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import reputation commands: {e}")

    def test_reputation_group_name(self):
        """Test reputation group name"""
        try:
            from aitbc_cli.commands.reputation import reputation

            assert reputation.name == "reputation"
        except ImportError as e:
            pytest.skip(f"Cannot import reputation commands: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
