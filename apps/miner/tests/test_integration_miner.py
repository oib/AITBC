"""Integration tests for miner service.

These patched ``production_miner.httpx.get`` / ``.post`` and asserted on ``Mock(status_code=…,
json=…)``. The module goes through ``aitbc.network.AITBCHTTPClient``, whose ``get``/``post``
return **parsed JSON** and raise ``NetworkError`` rather than reporting a status code — so the
old mocks described a interface the code never touches. They failed to collect at all from
2026-07-07 (V23-10a), which is why the drift was never reported.

``poll_for_jobs`` is the exception: it is the one function still calling ``requests``
directly, so its tests patch that.
"""

from unittest.mock import Mock, patch

import production_miner
import pytest
import requests
from aitbc.exceptions import NetworkError


@pytest.mark.integration
def test_check_ollama_success(mock_http):
    """Ollama reachable with models installed."""
    with mock_http(get={"models": [{"name": "llama3.2:latest"}, {"name": "mistral:latest"}]}):
        available, models = production_miner.check_ollama()

    assert available is True
    assert models == ["llama3.2:latest", "mistral:latest"]


@pytest.mark.integration
def test_check_ollama_failure(mock_http):
    """An empty response body means Ollama is not answering usefully."""
    with mock_http(get=None):
        available, models = production_miner.check_ollama()

    assert available is False
    assert models == []


@pytest.mark.integration
def test_check_ollama_exception(mock_http):
    """NetworkError is the failure the client actually raises."""
    with mock_http(get=NetworkError("Connection refused")):
        available, models = production_miner.check_ollama()

    assert available is False
    assert models == []


async def _no_sleep(_seconds):
    return None


@pytest.mark.integration
@patch("production_miner.build_gpu_capabilities")
def test_register_miner_success(mock_build, mock_http):
    """A session token comes back."""
    mock_build.return_value = {"gpus": [{"name": "RTX 4090"}]}

    with mock_http(post={"session_token": "test-token-123"}):
        assert production_miner.register_miner() == "test-token-123"


@pytest.mark.integration
@patch("production_miner.build_gpu_capabilities")
def test_register_miner_without_session_token_is_a_failure(mock_build, mock_http):
    """Registration that returns 200 and no token is not a success.

    The old test drove this with ``Mock(status_code=400)``, which the current code never
    inspects -- it would have passed whatever the module did.
    """
    mock_build.return_value = {"gpus": [{"name": "RTX 4090"}]}

    with mock_http(post={"registered": True}):
        assert production_miner.register_miner() is None


@pytest.mark.integration
@patch("production_miner.build_gpu_capabilities")
def test_register_miner_exception(mock_build, mock_http):
    mock_build.return_value = {"gpus": [{"name": "RTX 4090"}]}

    with mock_http(post=NetworkError("Connection error")):
        assert production_miner.register_miner() is None


@pytest.mark.integration
@patch("production_miner.get_gpu_info")
@patch("production_miner.classify_architecture")
@patch("production_miner.measure_coordinator_latency")
def test_send_heartbeat_with_gpu(mock_latency, mock_arch, mock_gpu, mock_http):
    """The heartbeat carries the real GPU stats, not just any body."""
    mock_gpu.return_value = {"name": "RTX 4090", "memory_total": 24576, "memory_used": 1024, "utilization": 45}
    mock_arch.return_value = "ada_lovelace"
    mock_latency.return_value = 50.0

    with mock_http(post={"ok": True}) as client:
        production_miner.send_heartbeat()

    client.instance.post.assert_called_once()
    body = client.instance.post.call_args.kwargs["json"]
    assert body["gpu_utilization"] == 45
    assert body["memory_used"] == 1024
    assert body["architecture"] == "ada_lovelace"
    assert body["edge_optimized"] is True
    assert body["network_latency_ms"] == 50.0


@pytest.mark.integration
@patch("production_miner.get_gpu_info")
@patch("production_miner.classify_architecture")
@patch("production_miner.measure_coordinator_latency")
def test_send_heartbeat_without_gpu(mock_latency, mock_arch, mock_gpu, mock_http):
    """No GPU still heartbeats, with zeroed stats rather than omitted ones."""
    mock_gpu.return_value = None
    mock_latency.return_value = 12.5

    with mock_http(post={"ok": True}) as client:
        production_miner.send_heartbeat()

    body = client.instance.post.call_args.kwargs["json"]
    assert body["gpu_utilization"] == 0
    assert body["memory_total"] == 0
    assert body["architecture"] == "unknown"
    assert body["edge_optimized"] is False


@pytest.mark.integration
def test_submit_result_success(mock_http):
    with mock_http(post={"accepted": True}) as client:
        production_miner.submit_result("job_123", {"result": {"status": "completed"}})

    client.instance.post.assert_called_once()
    assert client.instance.post.call_args.args[0] == "/v1/miners/job_123/result"


@pytest.mark.integration
def test_submit_result_survives_a_network_error(mock_http):
    """Submission failure must not propagate -- it would kill the mining loop."""
    with mock_http(post=NetworkError("Server error")):
        production_miner.submit_result("job_123", {"result": {"status": "completed"}})


# Patch `requests.post`, not `requests`: replacing the module wholesale makes
# `requests.exceptions.HTTPError` a MagicMock, and `except <MagicMock>` raises
# "catching classes that do not inherit from BaseException".


@pytest.mark.integration
@patch("production_miner.requests.post")
def test_poll_for_jobs_success(mock_post):
    """poll_for_jobs is the one function still on requests directly."""
    mock_post.return_value = Mock(status_code=200, json=lambda: {"job_id": "job_123", "payload": {"type": "inference"}})

    result = production_miner.poll_for_jobs()

    assert result is not None
    assert result["job_id"] == "job_123"


@pytest.mark.integration
@patch("production_miner.requests.post")
def test_poll_for_jobs_no_job(mock_post):
    """204 means no work, not an error -- and returns before raise_for_status."""
    mock_post.return_value = Mock(status_code=204)

    assert production_miner.poll_for_jobs() is None


@pytest.mark.integration
@patch("production_miner.requests.post")
def test_poll_for_jobs_failure(mock_post):
    """A real HTTPError, so the module's own except clause is the one exercised."""
    error = requests.exceptions.HTTPError("Server error")
    error.response = Mock(status_code=500)
    mock_post.return_value = Mock(status_code=500, raise_for_status=Mock(side_effect=error))

    assert production_miner.poll_for_jobs() is None


@pytest.mark.integration
@patch("production_miner.submit_result")
@patch("production_miner.get_gpu_info")
def test_execute_job_inference_success(mock_gpu, mock_submit, mock_http):
    mock_gpu.return_value = {"utilization": 80, "memory_used": 4096}

    with mock_http(post={"response": "Test output", "eval_count": 100}):
        job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}
        assert production_miner.execute_job(job, ["llama3.2:latest"]) is True

    submitted = mock_submit.call_args.args[1]
    assert submitted["result"]["status"] == "completed"
    assert submitted["result"]["output"] == "Test output"
    assert submitted["result"]["tokens_processed"] == 100


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_inference_no_models(mock_submit):
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test"}}

    assert production_miner.execute_job(job, []) is False
    assert mock_submit.call_args.args[1]["result"]["status"] == "failed"


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_unsupported_type(mock_submit):
    job = {"job_id": "job_123", "payload": {"type": "unsupported"}}

    assert production_miner.execute_job(job, ["llama3.2:latest"]) is False
    assert mock_submit.called


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_ollama_error(mock_submit, mock_http):
    """An empty Ollama response fails the job and reports why."""
    with mock_http(post=None):
        job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test", "model": "llama3.2:latest"}}
        assert production_miner.execute_job(job, ["llama3.2:latest"]) is False

    assert mock_submit.call_args.args[1]["result"]["error"] == "Ollama error"


@pytest.mark.integration
@patch("production_miner.submit_result")
def test_execute_job_exception(mock_submit):
    """No models available raises inside the try and is reported as a failed job."""
    job = {"job_id": "job_123", "payload": {"type": "inference", "prompt": "test"}}

    assert production_miner.execute_job(job, []) is False
    assert mock_submit.call_args.args[1]["result"]["status"] == "failed"
