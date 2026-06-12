"""
Workflow Handler Tests
Tests for workflow command handlers
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest
from handlers.workflow import (
    handle_workflow_create,
    handle_workflow_monitor,
    handle_workflow_schedule,
)


class TestHandleWorkflowCreate:
    """Test handle_workflow_create function"""

    @patch('handlers.workflow.requests.post')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_create_success(self, mock_logger, mock_post):
        """Test successful workflow creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job_123"}
        mock_post.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"
        args.template = "custom"
        args.model = "llama2:7b"
        args.prompt = "Hello"

        def render_mapping(title, data):
            pass

        handle_workflow_create(args, render_mapping)

        mock_post.assert_called_once()
        mock_logger.info.assert_called()

    @patch('handlers.workflow.requests.post')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_create_defaults(self, mock_logger, mock_post):
        """Test workflow creation with default values"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job_123"}
        mock_post.return_value = mock_response

        args = Mock()
        # Don't set attributes - they'll be None by default from getattr

        def render_mapping(title, data):
            pass

        handle_workflow_create(args, render_mapping)

        mock_post.assert_called_once()

    @patch('handlers.workflow.requests.post')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_create_http_error(self, mock_logger, mock_post):
        """Test workflow creation with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_post.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"
        args.template = "custom"
        args.model = "llama2:7b"
        args.prompt = "Hello"

        def render_mapping(title, data):
            pass

        handle_workflow_create(args, render_mapping)

        mock_logger.error.assert_called()

    @patch('handlers.workflow.requests.post')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_create_exception(self, mock_logger, mock_post):
        """Test workflow creation with exception"""
        mock_post.side_effect = Exception("Connection error")

        args = Mock()
        args.name = "test-workflow"
        args.template = "custom"
        args.model = "llama2:7b"
        args.prompt = "Hello"

        def render_mapping(title, data):
            pass

        handle_workflow_create(args, render_mapping)

        mock_logger.error.assert_called()


class TestHandleWorkflowSchedule:
    """Test handle_workflow_schedule function"""

    @patch('handlers.workflow.logger')
    def test_handle_workflow_schedule_with_params(self, mock_logger):
        """Test workflow scheduling with parameters"""
        args = Mock()
        args.name = "daily-inference"
        args.cron = "0 9 * * *"
        args.command = "aitbc workflow run daily-inference"

        def render_mapping(title, data):
            pass

        handle_workflow_schedule(args, render_mapping)

        mock_logger.info.assert_called()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "scheduled" in logged_msg

    @patch('handlers.workflow.logger')
    def test_handle_workflow_schedule_defaults(self, mock_logger):
        """Test workflow scheduling with default values"""
        args = Mock()
        args.name = None
        args.cron = None
        args.command = None

        def render_mapping(title, data):
            pass

        handle_workflow_schedule(args, render_mapping)

        mock_logger.info.assert_called()

    @patch('handlers.workflow.logger')
    def test_handle_workflow_schedule_calls_render_mapping(self, mock_logger):
        """Test that render_mapping is called"""
        args = Mock()
        args.name = "test-workflow"
        args.cron = "0 9 * * *"
        args.command = "test command"

        mock_render = Mock()

        handle_workflow_schedule(args, mock_render)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        assert "Schedule:" in call_args[0][0]


class TestHandleWorkflowMonitor:
    """Test handle_workflow_monitor function"""

    @patch('handlers.workflow.requests.get')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_monitor_success_json(self, mock_logger, mock_get):
        """Test workflow monitoring with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"state": "RUNNING"},
                {"state": "COMPLETED"},
                {"state": "FAILED"},
                {"state": "RUNNING"}
            ]
        }
        mock_get.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_workflow_monitor(args, output_format, render_mapping)

        mock_get.assert_called_once()
        mock_logger.info.assert_called()

    @patch('handlers.workflow.requests.get')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_monitor_success_text(self, mock_logger, mock_get):
        """Test workflow monitoring with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"state": "RUNNING"},
                {"state": "COMPLETED"}
            ]
        }
        mock_get.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_workflow_monitor(args, output_format, mock_render)

        mock_get.assert_called_once()
        mock_render.assert_called_once()

    @patch('handlers.workflow.requests.get')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_monitor_empty_jobs(self, mock_logger, mock_get):
        """Test workflow monitoring with no jobs"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_workflow_monitor(args, output_format, mock_render)

        mock_get.assert_called_once()
        mock_render.assert_called_once()

    @patch('handlers.workflow.requests.get')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_monitor_http_error(self, mock_logger, mock_get):
        """Test workflow monitoring with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response

        args = Mock()
        args.name = "test-workflow"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_workflow_monitor(args, output_format, mock_render)

        mock_logger.error.assert_called()
        mock_render.assert_called_once()

    @patch('handlers.workflow.requests.get')
    @patch('handlers.workflow.logger')
    def test_handle_workflow_monitor_exception(self, mock_logger, mock_get):
        """Test workflow monitoring with exception"""
        mock_get.side_effect = Exception("Connection error")

        args = Mock()
        args.name = "test-workflow"

        def output_format(args):
            return "text"

        mock_render = Mock()

        handle_workflow_monitor(args, output_format, mock_render)

        mock_logger.error.assert_called()
        mock_render.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
