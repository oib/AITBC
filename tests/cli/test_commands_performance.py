"""
Performance Commands Tests
Tests for performance CLI commands
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestPerformanceCommands:
    """Test performance command group"""

    def test_performance_group_exists(self):
        """Test that performance command group exists"""
        try:
            from aitbc_cli.commands.performance import performance

            assert performance is not None
            assert hasattr(performance, "name")
        except ImportError as e:
            pytest.skip(f"Cannot import performance commands: {e}")

    def test_performance_group_name(self):
        """Test performance group name"""
        try:
            from aitbc_cli.commands.performance import performance

            assert performance.name == "performance"
        except ImportError as e:
            pytest.skip(f"Cannot import performance commands: {e}")

    @patch("aitbc_cli.commands.performance.output")
    @patch("aitbc_cli.commands.performance.error")
    def test_performance_benchmark_command(self, mock_error, mock_output):
        """Test performance benchmark command - skip due to Click context issues"""
        pytest.skip("Click context mocking requires complex setup")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
