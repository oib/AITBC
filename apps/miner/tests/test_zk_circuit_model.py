"""#2330: registered ZK circuit models (e.g. linear-1) execute locally on the
miner — they are not Ollama models, so the #1788 availability check must not
reject them. The coordinator generates the Groth16 proof itself; the miner
only has to run the deterministic circuit and report the requested model.
"""

import json

import agent_task_executor as ate
import production_miner as pm
import pytest

from aitbc.zk_model_circuits import LINEAR_MODEL, get_model, text_to_field_array


def _inference_job(model_marker, prompt="hello"):
    payload = {"type": "inference", "prompt": prompt}
    if model_marker is not None:
        payload["model"] = model_marker
    return {"job_id": "j-zk", "payload": payload}


def _capture_results(monkeypatch):
    submitted = []
    monkeypatch.setattr(pm, "submit_result", lambda jid, res: submitted.append((jid, res)))
    monkeypatch.setattr(pm, "get_gpu_info", lambda: None)
    monkeypatch.setattr(pm, "build_tee_quote", lambda *a, **k: None)
    return submitted


@pytest.mark.unit
def test_circuit_model_executes_without_ollama(monkeypatch, mock_http):
    """model='linear-1' completes with no Ollama call and reports the requested
    circuit model — even when the miner's available_models list is empty."""
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "should not happen", "eval_count": 1}) as client_class:
        assert pm.execute_job(_inference_job("linear-1"), []) is True
    client_class.assert_not_called()
    result = submitted[0][1]["result"]
    assert result["status"] == "completed"
    assert result["model"] == "linear-1"
    expected = LINEAR_MODEL.compute_output(text_to_field_array("hello", LINEAR_MODEL.input_len))
    assert json.loads(result["output"]) == expected


@pytest.mark.unit
def test_circuit_model_resolves_by_model_id(monkeypatch, mock_http):
    """get_model() also resolves the integer model_id; the result still names
    the canonical circuit."""
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "x"}):
        assert pm.execute_job(_inference_job("0"), []) is True
    assert submitted[0][1]["result"]["model"] == "linear-1"


@pytest.mark.unit
def test_unregistered_model_still_fails(monkeypatch, mock_http):
    """#1788 stays intact: a name that is neither an Ollama model nor a
    registered circuit still fails the job."""
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "x"}):
        assert pm.execute_job(_inference_job("not-a-model"), ["llama3.2:latest"]) is False
    assert submitted[0][1]["result"]["status"] == "failed"
    assert "not-a-model" in submitted[0][1]["result"]["error"]


@pytest.mark.unit
def test_agent_executor_ollama_circuit_model():
    """The agent-task 'ollama' handler applies the same circuit path before the
    /api/tags availability guard."""
    out = ate._exec_ollama({"model": "linear-1"}, b'{"prompt": "hi"}')
    data = json.loads(out)
    assert data["model"] == "linear-1"
    circuit = get_model("linear-1")
    assert data["output"] == circuit.compute_output(text_to_field_array("hi", circuit.input_len))


@pytest.mark.unit
def test_agent_executor_ollama_unregistered_model_fails():
    """Unregistered names still hit the availability guard and fail closed."""
    # No ollama reachable in tests: the tags probe itself raises (wrapped as
    # "availability check failed"), or — if a miner happened to be up — the
    # name is absent and it fails "not available". Either way: ValueError.
    with pytest.raises(ValueError, match="model"):
        ate._exec_ollama({"model": "definitely-not-a-model"}, b'{"prompt": "hi"}')
