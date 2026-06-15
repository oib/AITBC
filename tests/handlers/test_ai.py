"""
AI Handler Tests
Tests for AI job submission and management handlers
"""

from unittest.mock import Mock, patch

import pytest
from handlers.ai import (
    handle_ai_distribution_stats,
    handle_ai_job,
    handle_ai_jobs,
    handle_ai_service_list,
    handle_ai_service_status,
    handle_ai_service_test,
    handle_ai_stats,
    handle_ai_status,
    handle_ai_submit,
)


class TestHandleAiSubmit:
    """Test handle_ai_submit function"""

    @patch("handlers.ai.requests.post")
    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_submit_success(self, mock_exit, mock_click, mock_post):
        """Test successful AI job submission"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job_123", "status": "submitted"}
        mock_post.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.wallet_name = "wallet1"
        args.wallet = None
        args.job_type_arg = "llama2"
        args.job_type = None
        args.prompt_arg = "test prompt"
        args.prompt = None
        args.payment_arg = None
        args.payment = None
        args.coordinator_url = None
        args.model = None
        args.parameters = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def render_mapping(title, data):
            pass

        handle_ai_submit(args, "http://localhost:8006", "http://localhost:8203", first, read_password, render_mapping)

        mock_post.assert_called_once()

    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_submit_missing_params(self, mock_exit, mock_click):
        """Test AI job submission with missing parameters"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.wallet_name = None
        args.wallet = None
        args.job_type_arg = None
        args.job_type = None
        args.prompt_arg = None
        args.prompt = None

        def first(*args):
            return args[0] if args else None

        def read_password(args, field):
            return "password"

        def render_mapping(title, data):
            pass

        handle_ai_submit(args, "http://localhost:8006", "http://localhost:8203", first, read_password, render_mapping)

        mock_exit.assert_called_with(1)


class TestHandleAiJobs:
    """Test handle_ai_jobs function"""

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    def test_handle_ai_jobs_json(self, mock_click, mock_get):
        """Test AI jobs list with JSON output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"job_id": "job_1", "model": "llama2", "status": "completed"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.coordinator_url = "http://localhost:8203"
        args.chain_id = None
        args.limit = 10

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_ai_jobs(args, "http://localhost:8006", "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    def test_handle_ai_jobs_text(self, mock_click, mock_get):
        """Test AI jobs list with text output"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"job_id": "job_1", "model": "llama2", "status": "completed"}]
        mock_get.return_value = mock_response

        args = Mock()
        args.coordinator_url = "http://localhost:8203"
        args.chain_id = None
        args.limit = 10

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_jobs(args, "http://localhost:8006", "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    def test_handle_ai_jobs_error_stub(self, mock_click, mock_get):
        """Test AI jobs list with error returning stub data"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        args = Mock()
        args.coordinator_url = "http://localhost:8203"
        args.chain_id = None
        args.limit = 10

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_jobs(args, "http://localhost:8006", "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()


class TestHandleAiJob:
    """Test handle_ai_job function"""

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_job_success(self, mock_exit, mock_click, mock_get):
        """Test successful AI job details query"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job_1", "model": "llama2", "status": "completed"}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.job_id_arg = "job_1"
        args.job_id = None

        def first(*args):
            return args[0] if args else None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_job(args, "http://localhost:8006", output_format, render_mapping, first)

        mock_get.assert_called_once()

    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_job_missing_id(self, mock_exit, mock_click):
        """Test AI job details with missing job ID"""
        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None
        args.job_id_arg = None
        args.job_id = None

        def first(*args):
            return args[0] if args else None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_job(args, "http://localhost:8006", output_format, render_mapping, first)

        mock_exit.assert_called_with(1)


class TestHandleAiStats:
    """Test handle_ai_stats function"""

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_stats_success(self, mock_exit, mock_click, mock_get):
        """Test successful AI stats query"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_jobs": 100, "active_jobs": 10}
        mock_get.return_value = mock_response

        args = Mock()
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_stats(args, "http://localhost:8006", output_format, render_mapping)

        mock_get.assert_called_once()


class TestHandleAiDistributionStats:
    """Test handle_ai_distribution_stats function"""

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    @patch("sys.exit")
    def test_handle_ai_distribution_stats_success(self, mock_exit, mock_click, mock_get):
        """Test successful distribution stats query"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_tasks": 50, "pending": 5}
        mock_get.return_value = mock_response

        args = Mock()
        args.coordinator_url = "http://localhost:8203"

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_distribution_stats(args, "http://localhost:8203", output_format, render_mapping)

        mock_get.assert_called_once()


class TestHandleAiServiceList:
    """Test handle_ai_service_list function"""

    @patch("sys.exit")
    def test_handle_ai_service_list_success(self, mock_exit):
        """Test successful AI service list"""
        args = Mock()

        def ai_operations(action):
            return {"services": ["service1", "service2"]}

        def render_mapping(title, data):
            pass

        handle_ai_service_list(args, ai_operations, render_mapping)


class TestHandleAiServiceStatus:
    """Test handle_ai_service_status function"""

    @patch("sys.exit")
    def test_handle_ai_service_status_success(self, mock_exit):
        """Test successful AI service status"""
        args = Mock()
        args.name = "service1"

        def ai_operations(action, **kwargs):
            return {"name": "service1", "status": "running"}

        def render_mapping(title, data):
            pass

        handle_ai_service_status(args, ai_operations, render_mapping)

    @patch("sys.exit")
    def test_handle_ai_service_status_no_name(self, mock_exit):
        """Test AI service status without name"""
        args = Mock()
        args.name = None

        def ai_operations(action, **kwargs):
            return {"status": "running"}

        def render_mapping(title, data):
            pass

        handle_ai_service_status(args, ai_operations, render_mapping)


class TestHandleAiServiceTest:
    """Test handle_ai_service_test function"""

    @patch("sys.exit")
    def test_handle_ai_service_test_success(self, mock_exit):
        """Test successful AI service test"""
        args = Mock()
        args.name = "service1"

        def ai_operations(action, **kwargs):
            return {"name": "service1", "test": "passed"}

        def render_mapping(title, data):
            pass

        handle_ai_service_test(args, ai_operations, render_mapping)


class TestHandleAiStatus:
    """Test handle_ai_status function"""

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    def test_handle_ai_status_both_operational(self, mock_click, mock_get):
        """Test AI status with both services operational"""
        mock_coordinator_response = Mock()
        mock_coordinator_response.status_code = 200
        mock_coordinator_response.json.return_value = {"status": "healthy", "version": "1.0"}

        mock_ai_response = Mock()
        mock_ai_response.status_code = 200
        mock_ai_response.json.return_value = {"status": "operational"}

        mock_get.side_effect = [mock_coordinator_response, mock_ai_response]

        args = Mock()
        args.coordinator_url = "http://localhost:8203"
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        def output_format(args):
            return "text"

        def render_mapping(title, data):
            pass

        handle_ai_status(args, "http://localhost:8203", "http://localhost:8006", output_format, render_mapping)

        assert mock_get.call_count == 2

    @patch("handlers.ai.requests.get")
    @patch("handlers.ai.click")
    def test_handle_ai_status_json(self, mock_click, mock_get):
        """Test AI status with JSON output"""
        mock_coordinator_response = Mock()
        mock_coordinator_response.status_code = 200
        mock_coordinator_response.json.return_value = {"status": "healthy"}

        mock_ai_response = Mock()
        mock_ai_response.status_code = 200
        mock_ai_response.json.return_value = {"status": "operational"}

        mock_get.side_effect = [mock_coordinator_response, mock_ai_response]

        args = Mock()
        args.coordinator_url = "http://localhost:8203"
        args.rpc_url = "http://localhost:8006"
        args.chain_id = None

        def output_format(args):
            return "json"

        def render_mapping(title, data):
            pass

        handle_ai_status(args, "http://localhost:8203", "http://localhost:8006", output_format, render_mapping)

        assert mock_get.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
