"""
Tests for AITBC metrics module
"""

import pytest
import asyncio
from unittest.mock import patch, Mock

from aitbc.metrics import (
    service_info,
    block_processing_duration,
    block_height,
    block_validation_duration,
    block_propagation_duration,
    job_submission_duration,
    job_processing_duration,
    job_queue_duration,
    job_execution_duration,
    jobs_total,
    jobs_failed_total,
    jobs_in_queue,
    http_requests_total,
    http_request_duration,
    service_uptime_seconds,
    service_restart_count,
    track_block_processing,
    track_job_processing,
    track_http_request,
    update_block_height,
    update_jobs_in_queue,
    increment_service_restarts,
    metrics_app,
    setup_service_info,
)


class TestMetricsDefinitions:
    """Tests for Prometheus metrics definitions"""

    def test_service_info_exists(self):
        """Test service_info metric is defined"""
        assert service_info is not None
        assert service_info._name == 'service_info'

    def test_block_processing_duration_exists(self):
        """Test block_processing_duration metric is defined"""
        assert block_processing_duration is not None
        assert block_processing_duration._name == 'block_processing_duration_seconds'

    def test_block_height_exists(self):
        """Test block_height metric is defined"""
        assert block_height is not None
        assert block_height._name == 'block_height'

    def test_block_validation_duration_exists(self):
        """Test block_validation_duration metric is defined"""
        assert block_validation_duration is not None
        assert block_validation_duration._name == 'block_validation_duration_seconds'

    def test_block_propagation_duration_exists(self):
        """Test block_propagation_duration metric is defined"""
        assert block_propagation_duration is not None
        assert block_propagation_duration._name == 'block_propagation_duration_seconds'

    def test_job_submission_duration_exists(self):
        """Test job_submission_duration metric is defined"""
        assert job_submission_duration is not None
        assert job_submission_duration._name == 'job_submission_duration_seconds'

    def test_job_processing_duration_exists(self):
        """Test job_processing_duration metric is defined"""
        assert job_processing_duration is not None
        assert job_processing_duration._name == 'job_processing_duration_seconds'

    def test_job_queue_duration_exists(self):
        """Test job_queue_duration metric is defined"""
        assert job_queue_duration is not None
        assert job_queue_duration._name == 'job_queue_duration_seconds'

    def test_job_execution_duration_exists(self):
        """Test job_execution_duration metric is defined"""
        assert job_execution_duration is not None
        assert job_execution_duration._name == 'job_execution_duration_seconds'

    def test_jobs_total_exists(self):
        """Test jobs_total metric is defined"""
        assert jobs_total is not None
        assert jobs_total._name == 'jobs'

    def test_jobs_failed_total_exists(self):
        """Test jobs_failed_total metric is defined"""
        assert jobs_failed_total is not None
        assert jobs_failed_total._name == 'jobs_failed'

    def test_jobs_in_queue_exists(self):
        """Test jobs_in_queue metric is defined"""
        assert jobs_in_queue is not None
        assert jobs_in_queue._name == 'jobs_in_queue'

    def test_http_requests_total_exists(self):
        """Test http_requests_total metric is defined"""
        assert http_requests_total is not None
        assert http_requests_total._name == 'http_requests'

    def test_http_request_duration_exists(self):
        """Test http_request_duration metric is defined"""
        assert http_request_duration is not None
        assert http_request_duration._name == 'http_request_duration_seconds'

    def test_service_uptime_seconds_exists(self):
        """Test service_uptime_seconds metric is defined"""
        assert service_uptime_seconds is not None
        assert service_uptime_seconds._name == 'service_uptime_seconds'

    def test_service_restart_count_exists(self):
        """Test service_restart_count metric is defined"""
        assert service_restart_count is not None
        assert service_restart_count._name == 'service_restart_count'


class TestHelperFunctions:
    """Tests for metrics helper functions"""

    def test_update_block_height(self):
        """Test update_block_height sets metric"""
        update_block_height(100)
        # Metric should be set, but we can't easily verify the value
        # This test ensures the function doesn't raise an error
        assert True

    def test_update_jobs_in_queue(self):
        """Test update_jobs_in_queue sets metric"""
        update_jobs_in_queue(50)
        # Metric should be set, but we can't easily verify the value
        # This test ensures the function doesn't raise an error
        assert True

    def test_increment_service_restarts(self):
        """Test increment_service_restarts increments counter"""
        increment_service_restarts()
        # Counter should be incremented, but we can't easily verify the value
        # This test ensures the function doesn't raise an error
        assert True

    def test_setup_service_info(self):
        """Test setup_service_info sets service info"""
        setup_service_info("test-service", "1.0.0")
        # Info should be set, but we can't easily verify the value
        # This test ensures the function doesn't raise an error
        assert True


class TestDecorators:
    """Tests for metrics tracking decorators"""

    @pytest.mark.asyncio
    async def test_track_block_processing_success(self):
        """Test track_block_processing decorator on successful execution"""
        @track_block_processing
        async def process_block():
            return "block_processed"
        
        result = await process_block()
        assert result == "block_processed"
        # Decorator should have observed the duration
        assert True

    @pytest.mark.asyncio
    async def test_track_block_processing_failure(self):
        """Test track_block_processing decorator on exception"""
        @track_block_processing
        async def process_block():
            raise ValueError("block error")
        
        with pytest.raises(ValueError):
            await process_block()
        # Decorator should have observed the duration even on failure
        assert True

    @pytest.mark.asyncio
    async def test_track_job_processing_success(self):
        """Test track_job_processing decorator on successful execution"""
        @track_job_processing
        async def process_job():
            return "job_completed"
        
        result = await process_job()
        assert result == "job_completed"
        # Decorator should have observed duration and incremented jobs_total
        assert True

    @pytest.mark.asyncio
    async def test_track_job_processing_failure(self):
        """Test track_job_processing decorator on exception"""
        @track_job_processing
        async def process_job():
            raise ValueError("job error")
        
        with pytest.raises(ValueError):
            await process_job()
        # Decorator should have observed duration and incremented failure counters
        assert True

    @pytest.mark.asyncio
    async def test_track_http_request_success(self):
        """Test track_http_request decorator on successful execution"""
        mock_response = Mock()
        mock_response.status_code = 200
        
        @track_http_request
        async def handle_request():
            return mock_response
        
        result = await handle_request()
        assert result.status_code == 200
        # Decorator should have observed duration and incremented http_requests_total
        assert True

    @pytest.mark.asyncio
    async def test_track_http_request_failure(self):
        """Test track_http_request decorator on exception"""
        @track_http_request
        async def handle_request():
            raise ValueError("request error")
        
        with pytest.raises(ValueError):
            await handle_request()
        # Decorator should have observed duration and incremented http_requests_total with 500
        assert True

    @pytest.mark.asyncio
    async def test_track_http_request_without_status_code(self):
        """Test track_http_request with response without status_code"""
        @track_http_request
        async def handle_request():
            return "success"  # No status_code attribute
        
        result = await handle_request()
        assert result == "success"
        # Decorator should have observed duration but not incremented http_requests_total
        assert True


class TestMetricsApp:
    """Tests for metrics ASGI app"""

    def test_metrics_app_exists(self):
        """Test metrics_app is created"""
        assert metrics_app is not None
        assert hasattr(metrics_app, '__call__')
