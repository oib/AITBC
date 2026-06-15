"""
Resource Handler Tests
Tests for resource command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestHandleResourceStatus:
    """Test handle_resource_status function"""

    @patch("handlers.resource.psutil")
    @patch("handlers.resource.logger")
    def test_handle_resource_status_json(self, mock_logger, mock_psutil):
        """Test resource status with JSON output"""
        mock_cpu = Mock()
        mock_cpu.percent = 45
        mock_psutil.cpu_percent.return_value = 45

        mock_memory = Mock()
        mock_memory.percent = 60
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_disk = Mock()
        mock_disk.percent = 70
        mock_psutil.disk_usage.return_value = mock_disk

        args = Mock()

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_status

        handle_resource_status(args, output_format, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.psutil")
    @patch("handlers.resource.logger")
    def test_handle_resource_status_text(self, mock_logger, mock_psutil):
        """Test resource status with text output"""
        mock_cpu = Mock()
        mock_cpu.percent = 45
        mock_psutil.cpu_percent.return_value = 45

        mock_memory = Mock()
        mock_memory.percent = 60
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_disk = Mock()
        mock_disk.percent = 70
        mock_psutil.disk_usage.return_value = mock_disk

        args = Mock()

        def output_format(args):
            return "text"

        mock_render = Mock()

        from handlers.resource import handle_resource_status

        handle_resource_status(args, output_format, mock_render)

        mock_render.assert_called_once()

    @patch("handlers.resource.psutil")
    @patch("handlers.resource.logger")
    def test_handle_resource_status_exception(self, mock_logger, mock_psutil):
        """Test resource status with exception"""
        mock_psutil.cpu_percent.side_effect = Exception("System error")

        args = Mock()

        def output_format(args):
            return "text"

        mock_render = Mock()

        from handlers.resource import handle_resource_status

        handle_resource_status(args, output_format, mock_render)

        mock_logger.error.assert_called()


class TestHandleResourceAllocate:
    """Test handle_resource_allocate function"""

    @patch("handlers.resource.os.getenv")
    @patch("handlers.resource.requests.post")
    @patch("handlers.resource.logger")
    def test_handle_resource_allocate_success(self, mock_logger, mock_post, mock_getenv):
        mock_getenv.return_value = "test-api-key"
        """Test successful resource allocation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_token": "token123"}
        mock_post.return_value = mock_response

        args = Mock()
        args.agent_id = "miner1"
        args.cpu = 4
        args.memory = 8192

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_allocate

        handle_resource_allocate(args, render_mapping)

        mock_post.assert_called_once()
        mock_logger.info.assert_called()

    @patch("handlers.resource.os.getenv")
    @patch("handlers.resource.requests.post")
    @patch("handlers.resource.logger")
    def test_handle_resource_allocate_defaults(self, mock_logger, mock_post, mock_getenv):
        mock_getenv.return_value = "test-api-key"
        """Test resource allocation with default values"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"session_token": "token123"}
        mock_post.return_value = mock_response

        args = Mock()
        args.agent_id = None
        args.cpu = None
        args.memory = None

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_allocate

        handle_resource_allocate(args, render_mapping)

        mock_post.assert_called_once()

    @patch("handlers.resource.os.getenv")
    @patch("handlers.resource.requests.post")
    @patch("handlers.resource.logger")
    def test_handle_resource_allocate_exception(self, mock_logger, mock_post, mock_getenv):
        mock_getenv.return_value = "test-api-key"
        """Test resource allocation with exception"""
        mock_post.side_effect = Exception("Connection error")

        args = Mock()
        args.agent_id = "miner1"
        args.cpu = 4
        args.memory = 8192

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_allocate

        handle_resource_allocate(args, render_mapping)

        mock_logger.error.assert_called()


class TestHandleResourceMonitor:
    """Test handle_resource_monitor function"""

    @patch("handlers.resource.logger")
    def test_handle_resource_monitor_defaults(self, mock_logger):
        """Test resource monitor with default values"""
        args = Mock()
        args.interval = None
        args.duration = None

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_monitor

        handle_resource_monitor(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.logger")
    def test_handle_resource_monitor_custom(self, mock_logger):
        """Test resource monitor with custom values"""
        args = Mock()
        args.interval = 10
        args.duration = 60

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_monitor

        handle_resource_monitor(args, render_mapping)

        mock_logger.info.assert_called()


class TestHandleResourceOptimize:
    """Test handle_resource_optimize function"""

    @patch("handlers.resource.logger")
    def test_handle_resource_optimize_default(self, mock_logger):
        """Test resource optimization with default target"""
        args = Mock()
        args.target = None

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_optimize

        handle_resource_optimize(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.logger")
    def test_handle_resource_optimize_custom(self, mock_logger):
        """Test resource optimization with custom target"""
        args = Mock()
        args.target = "memory"

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_optimize

        handle_resource_optimize(args, render_mapping)

        mock_logger.info.assert_called()


class TestHandleResourceBenchmark:
    """Test handle_resource_benchmark function"""

    @patch("handlers.resource.logger")
    def test_handle_resource_benchmark_cpu(self, mock_logger):
        """Test CPU benchmark"""
        args = Mock()
        args.type = "cpu"

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_benchmark

        handle_resource_benchmark(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.logger")
    def test_handle_resource_benchmark_memory(self, mock_logger):
        """Test memory benchmark"""
        args = Mock()
        args.type = "memory"

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_benchmark

        handle_resource_benchmark(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.logger")
    def test_handle_resource_benchmark_default(self, mock_logger):
        """Test benchmark with default type"""
        args = Mock()
        args.type = None

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_benchmark

        handle_resource_benchmark(args, render_mapping)

        mock_logger.info.assert_called()

    @patch("handlers.resource.logger")
    def test_handle_resource_benchmark_exception(self, mock_logger):
        """Test benchmark with exception"""
        args = Mock()
        args.type = "invalid"

        def render_mapping(title, data):
            pass

        from handlers.resource import handle_resource_benchmark

        handle_resource_benchmark(args, render_mapping)

        mock_logger.info.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
