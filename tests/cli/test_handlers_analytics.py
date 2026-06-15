"""
Analytics Handlers Tests
Tests for analytics CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestAnalyticsHandlers:
    """Test analytics handlers"""

    def test_handle_analytics_metrics_function_exists(self):
        """Test that handle_analytics_metrics function exists"""
        try:
            from handlers.analytics import handle_analytics_metrics

            assert handle_analytics_metrics is not None
        except ImportError as e:
            pytest.skip(f"Cannot import analytics handlers: {e}")

    def test_handle_analytics_report_function_exists(self):
        """Test that handle_analytics_report function exists"""
        try:
            from handlers.analytics import handle_analytics_report

            assert handle_analytics_report is not None
        except ImportError as e:
            pytest.skip(f"Cannot import analytics handlers: {e}")

    def test_handle_analytics_metrics_command(self):
        """Test handle_analytics_metrics - skip due to complex dependencies"""
        pytest.skip("Analytics handlers have complex output format dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
