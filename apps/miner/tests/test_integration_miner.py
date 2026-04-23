"""Integration tests for miner service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


import production_miner


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_check_ollama_success(mock_get):
    """Test Ollama check success"""
    mock_get.return_value = Mock(
        status_code=200,
        json=lambda: {"models": [{"name": "llama3.2:latest"}, {"name": "mistral:latest"}]}
    )
    available, models = production_miner.check_ollama()
    assert available is True
    assert len(models) == 2
    assert "llama3.2:latest" in models


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_check_ollama_failure(mock_get):
    """Test Ollama check failure"""
    mock_get.return_value = Mock(status_code=500)
    available, models = production_miner.check_ollama()
    assert available is False
    assert len(models) == 0


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_check_ollama_exception(mock_get):
    """Test Ollama check with exception"""
    mock_get.side_effect = Exception("Connection refused")
    available, models = production_miner.check_ollama()
    assert available is False
    assert len(models) == 0


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_wait_for_coordinator_success(mock_get):
    """Test waiting for coordinator success"""
    mock_get.return_value = Mock(status_code=200)
    result = production_miner.wait_for_coordinator()
    assert result is True


@pytest.mark.integration
@patch('production_miner.httpx.get')
@patch('production_miner.time.sleep')
def test_wait_for_coordinator_failure(mock_sleep, mock_get):
    """Test waiting for coordinator failure after max retries"""
    mock_get.side_effect = Exception("Connection refused")
    result = production_miner.wait_for_coordinator()
    assert result is False


@pytest.mark.integration
@patch('production_miner.httpx.post')
@patch('production_miner.build_gpu_capabilities')
def test_register_miner_success(mock_build, mock_post):
    """Test miner registration success"""
    mock_build.return_value = {"gpu": {"model": "RTX 4090"}}
    mock_post.return_value = Mock(
        status_code=200,
        json=lambda: {"session_token": "test-token-123"}
    )
    result = production_miner.register_miner()
    assert result == "test-token-123"


@pytest.mark.integration
@patch('production_miner.httpx.post')
@patch('production_miner.build_gpu_capabilities')
def test_register_miner_failure(mock_build, mock_post):
    """Test miner registration failure"""
    mock_build.return_value = {"gpu": {"model": "RTX 4090"}}
    mock_post.return_value = Mock(status_code=400, text="Bad request")
    result = production_miner.register_miner()
    assert result is None


@pytest.mark.integration
@patch('production_miner.httpx.post')
@patch('production_miner.build_gpu_capabilities')
def test_register_miner_exception(mock_build, mock_post):
    """Test miner registration with exception"""
    mock_build.return_value = {"gpu": {"model": "RTX 4090"}}
    mock_post.side_effect = Exception("Connection error")
    result = production_miner.register_miner()
    assert result is None


@pytest.mark.integration
@patch('production_miner.httpx.post')
@patch('production_miner.get_gpu_info')
@patch('production_miner.classify_architecture')
@patch('production_miner.measure_coordinator_latency')
def test_send_heartbeat_with_gpu(mock_latency, mock_arch, mock_gpu, mock_post):
    """Test sending heartbeat with GPU info"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576, "memory_used": 1024, "utilization": 45}
    mock_arch.return_value = "ada_lovelace"
    mock_latency.return_value = 50.0
    mock_post.return_value = Mock(status_code=200)
    
    production_miner.send_heartbeat()
    assert mock_post.called


@pytest.mark.integration
@patch('production_miner.httpx.post')
@patch('production_miner.get_gpu_info')
@patch('production_miner.classify_architecture')
@patch('production_miner.measure_coordinator_latency')
def test_send_heartbeat_without_gpu(mock_latency, mock_arch, mock_gpu, mock_post):
    """Test sending heartbeat without GPU info"""
    mock_gpu.return_value = None
    mock_post.return_value = Mock(status_code=200)
    
    production_miner.send_heartbeat()
    assert mock_post.called


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_submit_result_success(mock_post):
    """Test submitting job result success"""
    mock_post.return_value = Mock(status_code=200)
    production_miner.submit_result("job_123", {"result": {"status": "completed"}})
    assert mock_post.called


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_submit_result_failure(mock_post):
    """Test submitting job result failure"""
    mock_post.return_value = Mock(status_code=500, text="Server error")
    production_miner.submit_result("job_123", {"result": {"status": "completed"}})
    assert mock_post.called


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_poll_for_jobs_success(mock_post):
    """Test polling for jobs success"""
    mock_post.return_value = Mock(
        status_code=200,
        json=lambda: {"job_id": "job_123", "payload": {"type": "inference"}}
    )
    result = production_miner.poll_for_jobs()
    assert result is not None
    assert result["job_id"] == "job_123"


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_poll_for_jobs_no_job(mock_post):
    """Test polling for jobs when no job available"""
    mock_post.return_value = Mock(status_code=204)
    result = production_miner.poll_for_jobs()
    assert result is None


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_poll_for_jobs_failure(mock_post):
    """Test polling for jobs failure"""
    mock_post.return_value = Mock(status_code=500, text="Server error")
    result = production_miner.poll_for_jobs()
    assert result is None


@pytest.mark.integration
@patch('production_miner.submit_result')
@patch('production_miner.httpx.post')
@patch('production_miner.get_gpu_info')
def test_execute_job_inference_success(mock_gpu, mock_post, mock_submit):
    """Test executing inference job success"""
    mock_gpu.return_value = {"utilization": 80, "memory_used": 4096}
    mock_post.return_value = Mock(
        status_code=200,
        json=lambda: {"response": "Test output", "eval_count": 100}
    )
    
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is True
    assert mock_submit.called


@pytest.mark.integration
@patch('production_miner.submit_result')
@patch('production_miner.httpx.post')
def test_execute_job_inference_no_models(mock_post, mock_submit):
    """Test executing inference job with no available models"""
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test"}}
    result = production_miner.execute_job(job, [])
    assert result is False
    assert mock_submit.called


@pytest.mark.integration
@patch('production_miner.submit_result')
def test_execute_job_unsupported_type(mock_submit):
    """Test executing unsupported job type"""
    job = {"job_id": "job_123", "payload": {"type": "unsupported"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False
    assert mock_submit.called


@pytest.mark.integration
@patch('production_miner.submit_result')
@patch('production_miner.httpx.post')
def test_execute_job_ollama_error(mock_post, mock_submit):
    """Test executing job when Ollama returns error"""
    mock_post.return_value = Mock(status_code=500, text="Ollama error")
    
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False
    assert mock_submit.called


@pytest.mark.integration
@patch('production_miner.submit_result')
def test_execute_job_exception(mock_submit):
    """Test executing job with exception"""
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False
    assert mock_submit.called
