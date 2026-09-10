"""Unit tests for miner service"""

from unittest.mock import Mock, patch

import production_miner
import pytest
from aitbc.exceptions import NetworkError


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
@patch("production_miner.subprocess.run")
def test_detect_cuda_version_success(mock_run):
    """Test CUDA version detection success"""
    mock_run.return_value = Mock(returncode=0, stdout="12.0")
    result = production_miner.detect_cuda_version()
    assert result == "12.0"


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_detect_cuda_version_failure(mock_run):
    """Test CUDA version detection failure"""
    mock_run.side_effect = Exception("nvidia-smi not found")
    result = production_miner.detect_cuda_version()
    assert result is None


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_get_gpu_info_success(mock_run):
    """Test GPU info retrieval success"""
    mock_run.return_value = Mock(returncode=0, stdout="NVIDIA GeForce RTX 4090, 24576, 1024, 45")
    result = production_miner.get_gpu_info()
    assert result is not None
    assert result["name"] == "NVIDIA GeForce RTX 4090"
    assert result["memory_total"] == 24576
    assert result["memory_used"] == 1024
    assert result["utilization"] == 45


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_get_gpu_info_failure(mock_run):
    """Test GPU info retrieval failure"""
    mock_run.side_effect = Exception("nvidia-smi not found")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch("production_miner.get_gpu_info")
@patch("production_miner.detect_cuda_version")
@patch("production_miner.classify_architecture")
def test_build_gpu_capabilities(mock_arch, mock_cuda, mock_gpu):
    """Test building GPU capabilities"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576}
    mock_cuda.return_value = "12.0"
    mock_arch.return_value = "ada_lovelace"

    result = production_miner.build_gpu_capabilities()
    assert result is not None
    assert "gpus" in result, "the coordinator reads capabilities['gpus']"
    assert len(result["gpus"]) == 1
    gpu = result["gpus"][0]
    assert gpu["name"] == "RTX 4090"
    assert gpu["architecture"] == "ada_lovelace"
    assert gpu["edge_optimized"] is True
    assert result["cuda"] == "12.0"


@pytest.mark.unit
@patch("production_miner.get_gpu_info")
def test_build_gpu_capabilities_no_gpu(mock_gpu):
    """Test building GPU capabilities when no GPU"""
    mock_gpu.return_value = None

    result = production_miner.build_gpu_capabilities()
    assert result is not None
    # No GPU means an empty list, not an entry describing a GPU that is not there.
    assert result["gpus"] == []
    assert result["platform"] == "CPU"


@pytest.mark.unit
@patch("production_miner.classify_architecture")
def test_build_gpu_capabilities_edge_optimized(mock_arch):
    """Test edge optimization flag"""
    mock_arch.return_value = "ada_lovelace"

    with patch("production_miner.get_gpu_info") as mock_gpu, patch("production_miner.detect_cuda_version") as mock_cuda:
        mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576}
        mock_cuda.return_value = "12.0"

        result = production_miner.build_gpu_capabilities()
        assert result["gpus"][0]["edge_optimized"] is True


@pytest.mark.unit
@patch("production_miner.classify_architecture")
def test_build_gpu_capabilities_not_edge_optimized(mock_arch):
    """Test edge optimization flag for non-edge GPU"""
    mock_arch.return_value = "pascal"

    with patch("production_miner.get_gpu_info") as mock_gpu, patch("production_miner.detect_cuda_version") as mock_cuda:
        mock_gpu.return_value = {"name": "GTX 1080", "memory_total": 8192}
        mock_cuda.return_value = "11.0"

        result = production_miner.build_gpu_capabilities()
        assert result["gpus"][0]["edge_optimized"] is False


@pytest.mark.unit
def test_measure_coordinator_latency_success(mock_http):
    """A reachable coordinator yields a non-negative round trip in milliseconds."""
    with mock_http(get={"status": "healthy"}):
        assert production_miner.measure_coordinator_latency() >= 0


@pytest.mark.unit
def test_measure_coordinator_latency_failure(mock_http):
    """-1.0 is the sentinel for unreachable, and NetworkError is what the client raises."""
    with mock_http(get=NetworkError("Connection error")):
        assert production_miner.measure_coordinator_latency() == -1.0


@pytest.mark.unit
@patch("production_miner.submit_result")
@patch("production_miner.build_tee_quote", return_value=None)
@patch(
    "production_miner.get_gpu_info",
    return_value={"name": "NVIDIA GeForce RTX 4060 Ti", "memory_total": 16380, "memory_used": 1000, "utilization": 20},
)
@patch(
    "production_miner._gpu_snapshot",
    return_value={"name": "NVIDIA GeForce RTX 4060 Ti", "utilization": 20, "memory_used_mb": 1000, "memory_total_mb": 16380},
)
@patch("production_miner.time.sleep")
def test_execute_job_gpu_compute(mock_sleep, mock_snapshot, mock_gpu_info, mock_tee, mock_submit):
    """A gpu_compute/general_compute rental sleeps for the requested duration and snapshots GPU start/end."""
    job = {
        "job_id": "job-gpu-123",
        "payload": {
            "type": "gpu_compute",
            "task": "general_compute",
            "duration_hours": 0.05,
            "gpu_count": 1,
        },
    }
    assert production_miner.execute_job(job, []) is True
    mock_submit.assert_called_once()
    result = mock_submit.call_args[0][1]
    assert result["result"]["status"] == "completed"
    assert result["result"]["output"] == "GPU rental completed: general_compute for 180s"
    assert result["result"]["duration_seconds"] == 180
    assert result["result"]["gpu_used"] is True
    assert result["result"]["gpu_start"] == mock_snapshot.return_value
    assert result["result"]["gpu_end"] == mock_snapshot.return_value
    assert result["metrics"]["memory_peak"] == 2048


@pytest.mark.unit
@patch("production_miner.get_gpu_info", return_value=None)
@patch("production_miner.measure_coordinator_latency", return_value=12.0)
@patch("production_miner.AITBCHTTPClient")
def test_send_heartbeat_reports_inflight(mock_client, mock_latency, mock_gpu):
    """send_heartbeat reports the number of running jobs as inflight / current_jobs."""
    mock_client.return_value.post.return_value = True
    production_miner.ACTIVE_JOB_IDS.add("job-abc")
    try:
        production_miner.send_heartbeat()
        payload = mock_client.return_value.post.call_args.kwargs["json"]
        assert payload["inflight"] == 1
        assert payload["current_jobs"] == 1
    finally:
        production_miner.ACTIVE_JOB_IDS.clear()


@pytest.mark.unit
@patch("production_miner.get_gpu_info", return_value=None)
@patch("production_miner.measure_coordinator_latency", return_value=5.0)
def test_build_pool_hub_heartbeat_data_reports_current_jobs(mock_latency, mock_gpu):
    """build_pool_hub_heartbeat_data reports the number of running jobs as current_jobs."""
    production_miner.ACTIVE_JOB_IDS.add("job-xyz")
    try:
        data = production_miner.build_pool_hub_heartbeat_data()
        assert data["current_jobs"] == 1
    finally:
        production_miner.ACTIVE_JOB_IDS.clear()


@pytest.mark.unit
def test_download_media_decodes_data_uri(tmp_path):
    """_download_media decodes a base64 data: URI and writes it to disk."""
    import base64

    dest = tmp_path / "output.bin"
    data = b"hello worker"
    uri = f"data:application/octet-stream;base64,{base64.b64encode(data).decode()}"
    production_miner._download_media(uri, str(dest))
    assert dest.read_bytes() == data


@pytest.mark.unit
def test_download_media_rejects_unsupported_schemes():
    """_download_media raises an error for unsupported URL schemes."""
    with pytest.raises(Exception, match="unsupported URL scheme"):
        production_miner._download_media("ftp://example.com/file.mp3", "/tmp/output.bin")
