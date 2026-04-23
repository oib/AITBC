"""Unit tests for miner service"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess


import production_miner


@pytest.mark.unit
def test_classify_architecture_4090():
    """Test architecture classification for RTX 4090"""
    result = production_miner.classify_architecture("NVIDIA GeForce RTX 4090")
    assert result == "ada_lovelace"


@pytest.mark.unit
def test_classify_architecture_3080():
    """Test architecture classification for RTX 3080"""
    result = production_miner.classify_architecture("NVIDIA GeForce RTX 3080")
    assert result == "ampere"


@pytest.mark.unit
def test_classify_architecture_2080():
    """Test architecture classification for RTX 2080"""
    result = production_miner.classify_architecture("NVIDIA GeForce RTX 2080")
    assert result == "turing"


@pytest.mark.unit
def test_classify_architecture_1080():
    """Test architecture classification for GTX 1080"""
    result = production_miner.classify_architecture("NVIDIA GeForce GTX 1080")
    assert result == "pascal"


@pytest.mark.unit
def test_classify_architecture_a100():
    """Test architecture classification for A100"""
    result = production_miner.classify_architecture("NVIDIA A100")
    assert result == "datacenter"


@pytest.mark.unit
def test_classify_architecture_unknown():
    """Test architecture classification for unknown GPU"""
    result = production_miner.classify_architecture("Unknown GPU")
    assert result == "unknown"


@pytest.mark.unit
def test_classify_architecture_case_insensitive():
    """Test architecture classification is case insensitive"""
    result = production_miner.classify_architecture("nvidia rtx 4090")
    assert result == "ada_lovelace"


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_detect_cuda_version_success(mock_run):
    """Test CUDA version detection success"""
    mock_run.return_value = Mock(returncode=0, stdout="12.0")
    result = production_miner.detect_cuda_version()
    assert result == "12.0"


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_detect_cuda_version_failure(mock_run):
    """Test CUDA version detection failure"""
    mock_run.side_effect = Exception("nvidia-smi not found")
    result = production_miner.detect_cuda_version()
    assert result is None


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_get_gpu_info_success(mock_run):
    """Test GPU info retrieval success"""
    mock_run.return_value = Mock(
        returncode=0,
        stdout="NVIDIA GeForce RTX 4090, 24576, 1024, 45"
    )
    result = production_miner.get_gpu_info()
    assert result is not None
    assert result["name"] == "NVIDIA GeForce RTX 4090"
    assert result["memory_total"] == 24576
    assert result["memory_used"] == 1024
    assert result["utilization"] == 45


@pytest.mark.unit
@patch('production_miner.subprocess.run')
def test_get_gpu_info_failure(mock_run):
    """Test GPU info retrieval failure"""
    mock_run.side_effect = Exception("nvidia-smi not found")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch('production_miner.get_gpu_info')
@patch('production_miner.detect_cuda_version')
@patch('production_miner.classify_architecture')
def test_build_gpu_capabilities(mock_arch, mock_cuda, mock_gpu):
    """Test building GPU capabilities"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576}
    mock_cuda.return_value = "12.0"
    mock_arch.return_value = "ada_lovelace"
    
    result = production_miner.build_gpu_capabilities()
    assert result is not None
    assert "gpu" in result
    assert result["gpu"]["model"] == "RTX 4090"
    assert result["gpu"]["architecture"] == "ada_lovelace"
    assert result["gpu"]["edge_optimized"] is True


@pytest.mark.unit
@patch('production_miner.get_gpu_info')
def test_build_gpu_capabilities_no_gpu(mock_gpu):
    """Test building GPU capabilities when no GPU"""
    mock_gpu.return_value = None
    
    result = production_miner.build_gpu_capabilities()
    assert result is not None
    assert result["gpu"]["model"] == "Unknown GPU"
    assert result["gpu"]["architecture"] == "unknown"


@pytest.mark.unit
@patch('production_miner.classify_architecture')
def test_build_gpu_capabilities_edge_optimized(mock_arch):
    """Test edge optimization flag"""
    mock_arch.return_value = "ada_lovelace"
    
    with patch('production_miner.get_gpu_info') as mock_gpu, \
         patch('production_miner.detect_cuda_version') as mock_cuda:
        mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576}
        mock_cuda.return_value = "12.0"
        
        result = production_miner.build_gpu_capabilities()
        assert result["gpu"]["edge_optimized"] is True


@pytest.mark.unit
@patch('production_miner.classify_architecture')
def test_build_gpu_capabilities_not_edge_optimized(mock_arch):
    """Test edge optimization flag for non-edge GPU"""
    mock_arch.return_value = "pascal"
    
    with patch('production_miner.get_gpu_info') as mock_gpu, \
         patch('production_miner.detect_cuda_version') as mock_cuda:
        mock_gpu.return_value = {"name": "GTX 1080", "memory_total": 8192}
        mock_cuda.return_value = "11.0"
        
        result = production_miner.build_gpu_capabilities()
        assert result["gpu"]["edge_optimized"] is False


@pytest.mark.unit
@patch('production_miner.httpx.get')
def test_measure_coordinator_latency_success(mock_get):
    """Test coordinator latency measurement success"""
    mock_get.return_value = Mock(status_code=200)
    result = production_miner.measure_coordinator_latency()
    assert result >= 0


@pytest.mark.unit
@patch('production_miner.httpx.get')
def test_measure_coordinator_latency_failure(mock_get):
    """Test coordinator latency measurement failure"""
    mock_get.side_effect = Exception("Connection error")
    result = production_miner.measure_coordinator_latency()
    assert result == -1.0
