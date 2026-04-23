"""Edge case and error handling tests for miner service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch


import production_miner


@pytest.mark.unit
def test_classify_architecture_empty_string():
    """Test architecture classification with empty string"""
    result = production_miner.classify_architecture("")
    assert result == "unknown"


@pytest.mark.unit
def test_classify_architecture_special_characters():
    """Test architecture classification with special characters"""
    result = production_miner.classify_architecture("NVIDIA@#$%GPU")
    assert result == "unknown"


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_detect_cuda_version_timeout(mock_run):
    """Test CUDA version detection with timeout"""
    mock_run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 5)
    result = production_miner.detect_cuda_version()
    assert result is None


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_get_gpu_info_malformed_output(mock_run):
    """Test GPU info with malformed output"""
    mock_run.return_value = Mock(returncode=0, stdout="malformed,data")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_get_gpu_info_empty_output(mock_run):
    """Test GPU info with empty output"""
    mock_run.return_value = Mock(returncode=0, stdout="")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch('production_miner.get_gpu_info')
def test_build_gpu_capabilities_negative_memory(mock_gpu):
    """Test building GPU capabilities with negative memory"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": -24576}
    with patch('production_miner.detect_cuda_version') as mock_cuda, \
         patch('production_miner.classify_architecture') as mock_arch:
        mock_cuda.return_value = "12.0"
        mock_arch.return_value = "ada_lovelace"
        
        result = production_miner.build_gpu_capabilities()
        assert result["gpu"]["memory_gb"] == -24576


@pytest.mark.unit
@patch('production_miner.get_gpu_info')
def test_build_gpu_capabilities_zero_memory(mock_gpu):
    """Test building GPU capabilities with zero memory"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 0}
    with patch('production_miner.detect_cuda_version') as mock_cuda, \
         patch('production_miner.classify_architecture') as mock_arch:
        mock_cuda.return_value = "12.0"
        mock_arch.return_value = "ada_lovelace"
        
        result = production_miner.build_gpu_capabilities()
        assert result["gpu"]["memory_gb"] == 0


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_check_ollama_empty_models(mock_get):
    """Test Ollama check with empty models list"""
    mock_get.return_value = Mock(status_code=200, json=lambda: {"models": []})
    available, models = production_miner.check_ollama()
    assert available is True
    assert len(models) == 0


@pytest.mark.integration
@patch('production_miner.httpx.get')
def test_check_ollama_malformed_response(mock_get):
    """Test Ollama check with malformed response"""
    mock_get.return_value = Mock(status_code=200, json=lambda: {})
    available, models = production_miner.check_ollama()
    assert available is True
    assert len(models) == 0


@pytest.mark.integration
@patch('production_miner.submit_result')
@patch('production_miner.httpx.post')
def test_execute_job_empty_payload(mock_post, mock_submit):
    """Test executing job with empty payload"""
    mock_post.return_value = Mock(status_code=200, json=lambda: {"response": "test"})
    
    job = {"job_id": "job_123", "payload": {}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False


@pytest.mark.integration
@patch('production_miner.submit_result')
def test_execute_job_missing_job_id(mock_submit):
    """Test executing job with missing job_id"""
    job = {"payload": {"type": "inference"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False


@pytest.mark.integration
@patch('production_miner.submit_result')
@patch('production_miner.httpx.post')
def test_execute_job_model_fallback(mock_post, mock_submit):
    """Test executing job with model fallback to first available"""
    mock_post.return_value = Mock(status_code=200, json=lambda: {"response": "test"})
    
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "nonexistent"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is True


@pytest.mark.integration
@patch('production_miner.submit_result')
def test_execute_job_timeout(mock_submit):
    """Test executing job with timeout"""
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}
    
    with patch('production_miner.httpx.post') as mock_post:
        mock_post.side_effect = Exception("Timeout")
        result = production_miner.execute_job(job, ["llama3.2:latest"])
        assert result is False


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_poll_for_jobs_malformed_response(mock_post):
    """Test polling for jobs with malformed response"""
    mock_post.return_value = Mock(status_code=200, json=lambda: {})
    result = production_miner.poll_for_jobs()
    assert result is not None


@pytest.mark.integration
@patch('production_miner.httpx.post')
def test_submit_result_malformed_response(mock_post):
    """Test submitting result with malformed response"""
    mock_post.return_value = Mock(status_code=500, text="Error")
    production_miner.submit_result("job_123", {"result": {"status": "completed"}})
    assert mock_post.called
