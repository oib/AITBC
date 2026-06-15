"""
Analytics Handler Tests
Tests for analytics command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402
from handlers.analytics import (  # noqa: E402
    handle_analytics_export,
    handle_analytics_metrics,
    handle_analytics_optimize,
    handle_analytics_predict,
    handle_analytics_report,
)


class TestHandleAnalyticsMetrics:
    """Test handle_analytics_metrics function"""

    @patch("handlers.analytics.logger")
    def test_handle_analytics_metrics_json(self, mock_logger):
        """Test analytics metrics with JSON output"""
        args = Mock()
        args.period = "24h"

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_analytics_metrics(args, "http://localhost:8006", output_format, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_metrics_text(self, mock_logger):
        """Test analytics metrics with text output"""
        args = Mock()
        args.period = "7d"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_analytics_metrics(args, "http://localhost:8006", output_format, mock_render)

        mock_render.assert_called_once()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_metrics_default_period(self, mock_logger):
        """Test analytics metrics with default period"""
        args = Mock()
        args.period = None

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_analytics_metrics(args, "http://localhost:8006", output_format, mock_render)

        mock_render.assert_called_once()


class TestHandleAnalyticsReport:
    """Test handle_analytics_report function"""

    @patch("handlers.analytics.logger")
    def test_handle_analytics_report_json(self, mock_logger):
        """Test analytics report with JSON output"""
        args = Mock()
        args.report_type = "all"

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_analytics_report(args, "http://localhost:8006", output_format, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_report_text(self, mock_logger):
        """Test analytics report with text output"""
        args = Mock()
        args.report_type = "summary"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_analytics_report(args, "http://localhost:8006", output_format, mock_render)

        mock_render.assert_called_once()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_report_default_type(self, mock_logger):
        """Test analytics report with default report type"""
        args = Mock()
        args.report_type = None

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_analytics_report(args, "http://localhost:8006", output_format, mock_render)

        mock_render.assert_called_once()


class TestHandleAnalyticsExport:
    """Test handle_analytics_export function"""

    @patch("handlers.analytics.logger")
    def test_handle_analytics_export_csv(self, mock_logger):
        """Test analytics export with CSV format"""
        args = Mock()
        args.format = "csv"

        def render_mapping(title, data):
            pass

        handle_analytics_export(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_export_json_format(self, mock_logger):
        """Test analytics export with JSON format"""
        args = Mock()
        args.format = "json"

        def render_mapping(title, data):
            pass

        handle_analytics_export(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_export_default_format(self, mock_logger):
        """Test analytics export with default format"""
        args = Mock()
        args.format = None

        def render_mapping(title, data):
            pass

        handle_analytics_export(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()


class TestHandleAnalyticsPredict:
    """Test handle_analytics_predict function"""

    @patch("handlers.analytics.logger")
    def test_handle_analytics_predict_defaults(self, mock_logger):
        """Test analytics predict with default values"""
        args = Mock()
        args.model = None
        args.target = None

        def render_mapping(title, data):
            pass

        handle_analytics_predict(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_predict_custom(self, mock_logger):
        """Test analytics predict with custom values"""
        args = Mock()
        args.model = "transformer"
        args.target = "resource-usage"

        def render_mapping(title, data):
            pass

        handle_analytics_predict(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()


class TestHandleAnalyticsOptimize:
    """Test handle_analytics_optimize function"""

    @patch("handlers.analytics.logger")
    def test_handle_analytics_optimize_defaults(self, mock_logger):
        """Test analytics optimize with default values"""
        args = Mock()
        args.parameters = None
        args.target = None

        def render_mapping(title, data):
            pass

        handle_analytics_optimize(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.analytics.logger")
    def test_handle_analytics_optimize_custom(self, mock_logger):
        """Test analytics optimize with custom values"""
        args = Mock()
        args.parameters = True
        args.target = "throughput"

        def render_mapping(title, data):
            pass

        handle_analytics_optimize(args, "http://localhost:8006", render_mapping)

        mock_logger.info.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
