"""Edge case and error handling tests for miner service"""

import subprocess
from unittest.mock import Mock, patch

import production_miner
import pytest
from aitbc.exceptions import NetworkError


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
@patch("production_miner.subprocess.run")
def test_detect_cuda_version_timeout(mock_run):
    """Test CUDA version detection with timeout"""
    mock_run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 5)
    result = production_miner.detect_cuda_version()
    assert result is None


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_get_gpu_info_malformed_output(mock_run):
    """Test GPU info with malformed output"""
    mock_run.return_value = Mock(returncode=0, stdout="malformed,data")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_get_gpu_info_empty_output(mock_run):
    """Test GPU info with empty output"""
    mock_run.return_value = Mock(returncode=0, stdout="")
    result = production_miner.get_gpu_info()
    assert result is None


@pytest.mark.unit
@patch("production_miner.get_gpu_info")
def test_build_gpu_capabilities_negative_memory(mock_gpu):
    """Test building GPU capabilities with negative memory"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": -24576}
    with (
        patch("production_miner.detect_cuda_version") as mock_cuda,
        patch("production_miner.classify_architecture") as mock_arch,
    ):
        mock_cuda.return_value = "12.0"
        mock_arch.return_value = "ada_lovelace"

        result = production_miner.build_gpu_capabilities()
        # memory_mb, and the value is passed through unvalidated -- recording that rather
        # than asserting a "memory_gb" key this function has never produced.
        assert result["gpus"][0]["memory_mb"] == -24576


@pytest.mark.unit
@patch("production_miner.get_gpu_info")
def test_build_gpu_capabilities_zero_memory(mock_gpu):
    """Test building GPU capabilities with zero memory"""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 0}
    with (
        patch("production_miner.detect_cuda_version") as mock_cuda,
        patch("production_miner.classify_architecture") as mock_arch,
    ):
        mock_cuda.return_value = "12.0"
        mock_arch.return_value = "ada_lovelace"

        result = production_miner.build_gpu_capabilities()
        assert result["gpus"][0]["memory_mb"] == 0


@pytest.mark.integration
def test_check_ollama_empty_models(mock_http):
    """Ollama running with nothing installed: available, no models."""
    with mock_http(get={"models": []}):
        available, models = production_miner.check_ollama()

    assert available is True
    assert models == []


@pytest.mark.integration
def test_check_ollama_malformed_response(mock_http):
    """A response with no "models" key is treated as no models, not as a crash.

    Note the boundary this sits next to: an *empty* dict is falsy, so it takes the "not
    responding" branch and reports unavailable. A non-empty response missing "models" is
    reachable-but-empty, which is what this covers.
    """
    with mock_http(get={"unexpected": "shape"}):
        available, models = production_miner.check_ollama()

    assert available is True
    assert models == []


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_empty_payload(mock_submit, mock_http):
    """No job type at all is unsupported, and is reported rather than guessed at."""
    with mock_http(post={"response": "test"}):
        job = {"job_id": "job_123", "payload": {}}
        assert production_miner.execute_job(job, ["llama3.2:latest"]) is False

    assert mock_submit.call_args.args[1]["result"]["status"] == "failed"


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_missing_job_id(mock_submit):
    """Test executing job with missing job_id"""
    job = {"payload": {"type": "inference"}}
    result = production_miner.execute_job(job, ["llama3.2:latest"])
    assert result is False


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_model_fallback(mock_submit, mock_http):
    """An unavailable model falls back to the first installed one, and says which it used."""
    with mock_http(post={"response": "test"}):
        job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "nonexistent"}}
        assert production_miner.execute_job(job, ["llama3.2:latest"]) is True

    assert mock_submit.call_args.args[1]["result"]["model"] == "llama3.2:latest"


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_timeout(mock_submit, mock_http):
    """A timeout fails the job and reports the reason, rather than propagating."""
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}

    with mock_http(post=NetworkError("Timeout")):
        assert production_miner.execute_job(job, ["llama3.2:latest"]) is False

    assert "Timeout" in mock_submit.call_args.args[1]["result"]["error"]


@pytest.mark.integration
@patch("production_miner.requests.post")
def test_poll_for_jobs_malformed_response(mock_post):
    """A 200 with an empty body is "no job", not a job.

    The old test asserted ``result is not None``. The code returns None -- ``if job and
    job.get("job_id")`` is false for ``{}`` -- and returning a job-shaped None-ish object to
    the mining loop would be the bug, so the code is right.
    """
    mock_post.return_value = Mock(status_code=200, json=lambda: {})

    assert production_miner.poll_for_jobs() is None


@pytest.mark.integration
def test_submit_result_malformed_response(mock_http):
    """An empty response body is logged as a failure and does not raise."""
    with mock_http(post=None) as client:
        production_miner.submit_result("job_123", {"result": {"status": "completed"}})

    assert client.instance.post.called
