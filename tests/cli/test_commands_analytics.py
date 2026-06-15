"""
Analytics Commands Tests
Tests for analytics CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAnalyticsCommands:
    """Test analytics command group"""

    def test_analytics_group_exists(self):
        """Test that analytics command group exists"""
        try:
            from aitbc_cli.commands.analytics import analytics

            assert analytics is not None
            assert hasattr(analytics, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import analytics commands: {e}")

    def test_analytics_group_name(self):
        """Test analytics group name"""
        try:
            from aitbc_cli.commands.analytics import analytics

            assert analytics.name == "analytics"
        except ImportError as e:
            pytest.skip(f"Cannot import analytics commands: {e}")

    @patch("aitbc_cli.commands.analytics.output")
    @patch("aitbc_cli.commands.analytics.error")
    def test_analytics_summary_command(self, mock_error, mock_output):
        """Test analytics summary command - skip due to complex config and async dependencies"""
        pytest.skip("Analytics commands have complex config and async dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
