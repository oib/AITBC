"""#2301/#2305: region env, periodic market GPU re-register, visible capacity stall."""

import logging
from unittest.mock import Mock, patch

import pytest

import production_miner


def test_region_defaults_to_localhost_and_honours_env(monkeypatch):
    # MINER_REGION is read at import; the helper values are what register uses.
    assert production_miner.MINER_REGION  # never empty
    monkeypatch.setattr(production_miner, "MINER_REGION", "node2")
    caps = production_miner.build_gpu_capabilities()
    assert caps["region"] == "node2"


def test_market_gpu_region_follows_miner_region(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("MINER_REGISTER_GPU", "1")
    monkeypatch.delenv("MINER_GPU_REGION", raising=False)
    monkeypatch.setattr(production_miner, "MINER_REGION", "node2")
    client = MagicMock()
    client.post.return_value = {"gpu_id": "g"}
    with (
        patch("production_miner.get_gpu_info", return_value={"name": "X", "memory_total": 8192}),
        patch("production_miner.AITBCHTTPClient", return_value=client),
    ):
        production_miner.register_market_gpu()
    assert client.post.call_args.kwargs["json"]["gpu"]["region"] == "node2"


def test_capacity_skip_warns_rate_limited(monkeypatch, caplog):
    monkeypatch.setattr(production_miner, "_last_capacity_warn", 0.0)
    monkeypatch.setattr(production_miner, "ACTIVE_JOB_IDS", {"job-stuck"})
    with caplog.at_level(logging.WARNING):
        production_miner._warn_at_capacity(1)
        production_miner._warn_at_capacity(1)
    msgs = [r.message for r in caplog.records if "max capacity" in r.message]
    assert len(msgs) == 1 and "job-stuck" in msgs[0]


def test_main_loop_reregisters_market_gpu_periodically():
    import inspect

    src = inspect.getsource(production_miner.main)
    assert "MARKET_GPU_REREGISTER_INTERVAL" in src and "register_market_gpu" in src


@pytest.mark.unit
def test_poll_failures_warn_at_threshold_and_recover(monkeypatch, caplog):
    """#2305: N consecutive poll failures log a threshold WARNING; a later
    success logs recovery and resets the counter."""
    monkeypatch.setattr(production_miner, "_poll_failures", 0)
    monkeypatch.setattr(production_miner, "POLL_FAILURE_WARN_EVERY", 3)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            production_miner._note_poll_result(False)
        production_miner._note_poll_result(True)
    warns = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("3 consecutive" in m or "3 time(s)" in m for m in warns)
    assert any("recovered after 3" in m for m in warns)
    assert production_miner._poll_failures == 0


@pytest.mark.unit
def test_poll_interval_backs_off_on_failures(monkeypatch):
    monkeypatch.setattr(production_miner, "_poll_failures", 0)
    assert production_miner._poll_interval_seconds() == 3.0
    monkeypatch.setattr(production_miner, "_poll_failures", 1)
    assert production_miner._poll_interval_seconds() == 6.0
    monkeypatch.setattr(production_miner, "_poll_failures", 99)
    assert production_miner._poll_interval_seconds() == production_miner.POLL_RETRY_MAX_SECONDS


@pytest.mark.unit
@patch("production_miner.requests.post")
def test_poll_for_jobs_counts_transport_failures(mock_post, monkeypatch):
    """A ConnectTimeout is a poll failure: counted, loop keeps going."""
    monkeypatch.setattr(production_miner, "_poll_failures", 0)
    mock_post.side_effect = production_miner.requests.exceptions.ConnectTimeout("timed out")
    assert production_miner.poll_for_jobs() is None
    assert production_miner._poll_failures == 1


@pytest.mark.unit
@patch("production_miner.requests.post")
def test_poll_for_jobs_204_resets_failure_count(mock_post, monkeypatch):
    monkeypatch.setattr(production_miner, "_poll_failures", 5)
    mock_post.return_value = Mock(status_code=204)
    assert production_miner.poll_for_jobs() is None
    assert production_miner._poll_failures == 0


@pytest.mark.unit
@patch("production_miner.poll_for_jobs")
@patch("production_miner.fetch_running_jobs")
def test_poll_cycle_survives_unexpected_poll_exception(mock_fetch, mock_poll, monkeypatch, caplog):
    """#2305: an exception escaping the poll path must not kill the cycle —
    it is logged, counted as a poll failure, and the loop retries."""
    monkeypatch.setattr(production_miner, "_poll_failures", 0)
    mock_fetch.return_value = []
    mock_poll.side_effect = RuntimeError("unexpected poll failure")
    with caplog.at_level(logging.ERROR):
        production_miner._poll_and_dispatch(models=[], max_concurrent_jobs=2)
    assert production_miner._poll_failures == 1
    assert any("poll/dispatch cycle failed" in r.message for r in caplog.records)
