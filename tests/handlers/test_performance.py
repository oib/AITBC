"""
Performance Handler Tests
Tests for performance command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402
from handlers.performance import (  # noqa: E402
    handle_performance_benchmark,
    handle_performance_optimize,
    handle_performance_tune,
)


class TestHandlePerformanceBenchmark:
    """Test handle_performance_benchmark function"""

    @patch("handlers.performance.logger")
    def test_handle_performance_benchmark_json(self, mock_logger):
        """Test benchmark with JSON output format"""
        args = Mock()

        def output_format(args):
            return "json"

        handle_performance_benchmark(args, output_format, None)

        mock_logger.info.assert_called()
        # Check that JSON was logged
        logged_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("tps" in call for call in logged_calls)

    @patch("handlers.performance.logger")
    def test_handle_performance_benchmark_text(self, mock_logger):
        """Test benchmark with text output format"""
        args = Mock()

        def output_format(args):
            return "text"

        handle_performance_benchmark(args, output_format, None)

        mock_logger.info.assert_called()
        # Check that text format was used
        logged_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Performance Benchmark:" in call for call in logged_calls)


class TestHandlePerformanceOptimize:
    """Test handle_performance_optimize function"""

    @patch("handlers.performance.logger")
    def test_handle_performance_optimize_default_target(self, mock_logger):
        """Test optimization with default target"""
        args = Mock()
        args.target = "general"

        def render_mapping(title, data):
            pass

        handle_performance_optimize(args, render_mapping)

        mock_logger.info.assert_called()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "general" in logged_msg

    @patch("handlers.performance.logger")
    def test_handle_performance_optimize_custom_target(self, mock_logger):
        """Test optimization with custom target"""
        args = Mock()
        args.target = "database"

        def render_mapping(title, data):
            pass

        handle_performance_optimize(args, render_mapping)

        mock_logger.info.assert_called()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "database" in logged_msg

    @patch("handlers.performance.logger")
    def test_handle_performance_optimize_calls_render_mapping(self, mock_logger):
        """Test that render_mapping is called"""
        args = Mock()
        args.target = "general"

        mock_render = Mock()

        handle_performance_optimize(args, mock_render)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert "Optimization:" in call_args[0][0]


class TestHandlePerformanceTune:
    """Test handle_performance_tune function"""

    @patch("handlers.performance.logger")
    def test_handle_performance_tune_defaults(self, mock_logger):
        """Test tuning with default parameters"""
        args = Mock()
        args.parameters = False
        args.aggressive = False

        def render_mapping(title, data):
            pass

        handle_performance_tune(args, render_mapping)

        mock_logger.info.assert_called()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "Performance tuning applied" in logged_msg

    @patch("handlers.performance.logger")
    def test_handle_performance_tune_with_parameters(self, mock_logger):
        """Test tuning with parameters enabled"""
        args = Mock()
        args.parameters = True
        args.aggressive = False

        def render_mapping(title, data):
            pass

        handle_performance_tune(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.performance.logger")
    def test_handle_performance_tune_aggressive(self, mock_logger):
        """Test tuning with aggressive mode"""
        args = Mock()
        args.parameters = False
        args.aggressive = True

        def render_mapping(title, data):
            pass

        handle_performance_tune(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.performance.logger")
    def test_handle_performance_tune_calls_render_mapping(self, mock_logger):
        """Test that render_mapping is called"""
        args = Mock()
        args.parameters = True
        args.aggressive = True

        mock_render = Mock()

        handle_performance_tune(args, mock_render)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert "Tuning:" in call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
