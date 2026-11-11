"""Tests for the coder-C defect batch on the miner (#1483-#1488).

Covers: buyer-controlled path parameters in job executors, the fabricated
ram_gb registration field, duplicate job dispatch, executor state-file
handling, quote expiry/cap, and sweep resilience.
"""

import time

import agent_task_executor as ate
import production_miner as pm
import pytest

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


# --- #1483: path parameters -------------------------------------------------


@pytest.mark.unit
def test_safe_name_accepts_plain_tokens() -> None:
    assert pm._safe_name("mp4", "bin") == "mp4"
    assert pm._safe_name(".mp4", "bin") == "mp4"
    assert pm._safe_name("3gp", "bin") == "3gp"


@pytest.mark.unit
def test_safe_name_rejects_traversal_and_separators() -> None:
    for bad in ("../evil", "a/b", "a\\b", "..", "", None, "x" * 40, "mp4;rm"):
        assert pm._safe_name(bad, "bin") == "bin"


@pytest.mark.unit
def test_require_safe_name_rejects_traversal() -> None:
    for bad in ("../../etc/cron.d/x", "mp4/../../tmp/evil", "a b", ""):
        with pytest.raises(Exception, match="Invalid output_format"):
            pm._require_safe_name(bad, "output_format")
    assert pm._require_safe_name("webm", "output_format") == "webm"


@pytest.mark.unit
def test_reencode_rejects_traversal_output_format(tmp_path, monkeypatch):
    """A payload output_format with separators fails the job before ffmpeg runs."""
    captured = {}

    def fake_download(url, dest):
        captured["input"] = dest

    def fake_ffmpeg(input_path, output_path, output_format=None):
        captured["output"] = output_path
        return {"output_format": output_format, "stderr": "ok"}

    monkeypatch.setattr(pm, "_download_media", fake_download)
    monkeypatch.setattr(pm, "_run_ffmpeg", fake_ffmpeg)

    job = {
        "job_id": "j-trav",
        "payload": {"type": "reencode", "url": "https://example.com/v.mp4", "output_format": "mp4/../../tmp/evil"},
    }
    submitted = []
    monkeypatch.setattr(pm, "_submit_failure", lambda jid, err: submitted.append((jid, err)))
    monkeypatch.setattr(pm, "_submit_success", lambda *a, **k: submitted.append(("success", a)))

    result = pm.execute_job(job, [])
    assert result is False
    assert "output" not in captured  # ffmpeg never ran
    assert submitted and submitted[0][0] == "j-trav"


@pytest.mark.unit
def test_reencode_output_path_stays_in_tmp(tmp_path, monkeypatch):
    """A valid output_format produces output.<fmt> inside the temp dir."""
    captured = {}

    def fake_download(url, dest):
        pass

    def fake_ffmpeg(input_path, output_path, output_format=None):
        captured["output"] = output_path
        captured["fmt"] = output_format
        return {"output_format": output_format, "stderr": "ok"}

    monkeypatch.setattr(pm, "_download_media", fake_download)
    monkeypatch.setattr(pm, "_run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(pm, "_submit_success", lambda *a, **k: None)
    monkeypatch.setattr(pm, "build_tee_quote", lambda *a, **k: None)

    job = {"job_id": "j-ok", "payload": {"type": "reencode", "url": "https://example.com/v.mp4", "output_format": "webm"}}
    assert pm.execute_job(job, []) is True
    assert captured["fmt"] == "webm"
    assert captured["output"].endswith("output.webm")
    assert ".." not in captured["output"]


@pytest.mark.unit
def test_transcribe_input_ext_is_sanitised(monkeypatch):
    """A hostile filename cannot steer the input path outside tmp."""
    captured = {}

    def fake_download(url, dest):
        captured["input"] = dest

    def fake_whisper(path, model="base", **kw):
        return "text"

    monkeypatch.setattr(pm, "_download_media", fake_download)
    monkeypatch.setattr(pm, "_run_whisper", fake_whisper)
    monkeypatch.setattr(pm, "_submit_success", lambda *a, **k: None)
    monkeypatch.setattr(pm, "build_tee_quote", lambda *a, **k: None)

    job = {
        "job_id": "j-tr",
        "payload": {"type": "transcribe", "url": "https://example.com/x", "filename": "../../etc/passwd.mp4"},
    }
    assert pm.execute_job(job, []) is True
    assert captured["input"].endswith("input.mp4")
    assert "passwd" not in captured["input"]


# --- #1484: fabricated ram_gb ------------------------------------------------


@pytest.mark.unit
def test_total_ram_gb_is_measured_not_hardcoded() -> None:
    ram = pm._total_ram_gb()
    assert isinstance(ram, float)
    assert ram > 0


@pytest.mark.unit
def test_register_data_uses_measured_ram(monkeypatch) -> None:
    monkeypatch.setattr(pm, "get_gpu_info", lambda: None)
    monkeypatch.setattr(pm, "build_gpu_capabilities", lambda: {"price": "0.01", "supported_tasks": []})
    monkeypatch.setattr(pm, "_total_ram_gb", lambda: 42.5)
    data = pm.build_pool_hub_register_data()
    assert data["ram_gb"] == 42.5


# --- #1485: duplicate dispatch ----------------------------------------------


@pytest.mark.unit
def test_claim_job_slot_dedups() -> None:
    pm.ACTIVE_JOB_IDS.discard("j-dup")
    assert pm._claim_job_slot("j-dup") is True
    assert pm._claim_job_slot("j-dup") is False
    pm.ACTIVE_JOB_IDS.discard("j-dup")


# --- #1486/#1487/#1488: agent_task_executor ----------------------------------


@pytest.mark.unit
def test_load_state_logs_and_defaults_on_corrupt(tmp_path, monkeypatch, caplog) -> None:
    bad = tmp_path / "state.json"
    bad.write_text("{not json")
    monkeypatch.setattr(ate, "STATE_PATH", bad)
    with caplog.at_level("WARNING"):
        state = ate._load_state()
    assert state == {"done": [], "quotes": {}}
    assert any("unreadable" in r.message for r in caplog.records)


@pytest.mark.unit
def test_load_state_missing_file_is_quiet(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(ate, "STATE_PATH", tmp_path / "absent.json")
    with caplog.at_level("WARNING"):
        assert ate._load_state() == {"done": [], "quotes": {}}
    assert not caplog.records


@pytest.mark.unit
def test_prune_quotes_expires_stale_and_caps(monkeypatch) -> None:
    monkeypatch.setattr(ate, "_QUOTE_TTL_SECONDS", 100.0)
    monkeypatch.setattr(ate, "_QUOTE_MAX_ENTRIES", 3)
    now = time.time()
    quotes = {
        "fresh": {"quoted_at": now},
        "stale": {"quoted_at": now - 1000},
        "bad-ts": {"quoted_at": "not-a-number"},
        "q1": {"quoted_at": now - 50},
        "q2": {"quoted_at": now - 40},
        "q3": {"quoted_at": now - 30},
        "q4": {"quoted_at": now - 20},
    }
    live = ate._prune_quotes(quotes)
    assert "stale" not in live and "bad-ts" not in live
    assert len(live) == 3  # cap keeps the newest three
    assert "fresh" in live and "q1" not in live


@pytest.mark.unit
def test_escrow_reject_reason_survives_bad_fields(monkeypatch) -> None:
    """Non-numeric amount / None agent must reject, not raise (#1488)."""
    monkeypatch.setattr(
        ate,
        "_task_escrow_status",
        lambda task_id: {
            "escrow_status": "locked",
            "tx_hash_lock": "0xabc",
            "agent": PROVIDER,
            "amount": "not-a-number",
        },
    )
    reason = ate._escrow_reject_reason("t1", PROVIDER, {"price": "0.01"})
    assert reason == "escrow amount unreadable"

    # agent present-but-None must also reject cleanly, not raise AttributeError.
    monkeypatch.setattr(
        ate,
        "_task_escrow_status",
        lambda task_id: {"escrow_status": "locked", "tx_hash_lock": "0xabc", "agent": None, "amount": 10**18},
    )
    reason = ate._escrow_reject_reason("t1", PROVIDER, {"price": "0.01"})
    assert reason is not None and reason.startswith("escrow pays")


@pytest.mark.unit
def test_inbox_message_exception_does_not_abort_sweep(monkeypatch) -> None:
    """A handler crash leaves the message unread but does not propagate."""
    state = {"done": [], "quotes": {}}
    stats = {"quoted": 0, "rejected": 0, "executed": 0, "failed": 0}
    message = {
        "message_id": "m-poison",
        "message_type": "task_request",
        "sender": "buyer",
        "content": {"task_id": "t"},
    }

    def boom(*a, **k):
        raise RuntimeError("poison")

    monkeypatch.setattr(ate, "_handle_task_request", boom)
    monkeypatch.setattr(ate, "_mark_read", lambda mid: None)
    # Must not raise; message must NOT be marked done (retried next sweep).
    ate._process_inbox_message(message, state["done"], PROVIDER, {}, state, stats)
    assert "m-poison" not in state["done"]


# --- #1788: silent model substitution ---------------------------------------


def _inference_job(model_marker):
    payload = {"type": "inference", "prompt": "hello"}
    if model_marker is not None:
        payload["model"] = model_marker
    return {"job_id": "j-model", "payload": payload}


def _capture_results(monkeypatch):
    submitted = []
    monkeypatch.setattr(pm, "submit_result", lambda jid, res: submitted.append((jid, res)))
    monkeypatch.setattr(pm, "get_gpu_info", lambda: None)
    monkeypatch.setattr(pm, "build_tee_quote", lambda *a, **k: None)
    return submitted


@pytest.mark.unit
def test_requested_model_unavailable_fails_instead_of_substituting(monkeypatch, mock_http):
    """An explicit model request that this miner cannot serve must fail the
    job — not silently run a different model under the buyer's payment."""
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "should not happen", "eval_count": 1}):
        assert pm.execute_job(_inference_job("huge-model:70b"), ["llama3.2:latest"]) is False
    assert submitted and submitted[0][1]["result"]["status"] == "failed"
    assert "huge-model:70b" in submitted[0][1]["result"]["error"]


@pytest.mark.unit
def test_requested_model_available_runs_and_reports_it(monkeypatch, mock_http):
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "hi", "eval_count": 3}):
        assert pm.execute_job(_inference_job("llama3.2:latest"), ["llama3.2:latest", "qwen3:8b"]) is True
    result = submitted[0][1]["result"]
    assert result["status"] == "completed"
    assert result["model"] == "llama3.2:latest"


@pytest.mark.unit
def test_unspecified_model_falls_back_and_reports_actual(monkeypatch, mock_http):
    """No model requested: availability-first fallback stays, but the result
    names the model that actually ran."""
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "hi", "eval_count": 2}):
        assert pm.execute_job(_inference_job(None), ["qwen3:8b"]) is True
    result = submitted[0][1]["result"]
    assert result["status"] == "completed"
    assert result["model"] == "qwen3:8b"


@pytest.mark.unit
def test_no_models_available_fails(monkeypatch, mock_http):
    submitted = _capture_results(monkeypatch)
    with mock_http(post={"response": "x"}):
        assert pm.execute_job(_inference_job("anything"), []) is False
    assert submitted[0][1]["result"]["status"] == "failed"
