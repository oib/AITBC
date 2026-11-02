"""Phase-0 pin for GPU-COMPUTE-DURATION-1 (#805).

`_execute_gpu_compute` takes `duration_seconds`/`duration_hours` from the
buyer's payload unchecked and sleeps the whole span in 5 s chunks without
ever re-checking the job's deadline: a 3600 s payload holds the reservation
past `expires_at` and there is no configured maximum.

Behaviour pinned here: the duration is clamped to GPU_COMPUTE_MAX_SECONDS and
validated as a finite, non-negative number, and the sleep loop stops early once
the job's expires_at passes. Before the fix a 10**8 s request was held and the
loop ignored the deadline.
"""

import time
from datetime import UTC, datetime
from unittest.mock import patch

import production_miner as pm
import pytest

MAX_ENV = "GPU_COMPUTE_MAX_SECONDS"


def _job(duration_seconds=None, duration_hours=None, expires_in=None):
    payload = {"task": "general_compute"}
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    if duration_hours is not None:
        payload["duration_hours"] = duration_hours
    job = {"job_id": "j1", "payload": payload}
    if expires_in is not None:
        job["expires_at"] = time.time() + expires_in
    return job


def test_duration_clamped_to_configured_max(monkeypatch):
    monkeypatch.setenv(MAX_ENV, "10")
    slept = []
    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success"),
        patch.object(pm, "build_tee_quote", return_value=None),
        patch.object(pm.time, "sleep", lambda s: slept.append(s)),
    ):
        pm._execute_gpu_compute(_job(duration_seconds=10**8))
    assert sum(slept) <= 10, f"held for {sum(slept)}s of a 10**8 s request"


def test_unbounded_duration_gets_default_max(monkeypatch):
    monkeypatch.setenv(MAX_ENV, "10")
    slept = []
    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success"),
        patch.object(pm, "build_tee_quote", return_value=None),
        patch.object(pm.time, "sleep", lambda s: slept.append(s)),
    ):
        pm._execute_gpu_compute(_job(duration_seconds=10**8))
    assert sum(slept) <= 10


def test_loop_stops_at_job_deadline(monkeypatch):
    """expires_at mid-run must cut the hold, not sleep the payload's span."""
    monkeypatch.setenv(MAX_ENV, "3600")
    job = _job(duration_seconds=3600, expires_in=0)  # already past
    slept = []
    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success"),
        patch.object(pm, "build_tee_quote", return_value=None),
        patch.object(pm.time, "sleep", lambda s: slept.append(s)),
    ):
        pm._execute_gpu_compute(job)
    assert sum(slept) < 3600, "sleep loop ignored the job deadline"


def test_nonfinite_or_negative_duration_rejected(monkeypatch):
    monkeypatch.setenv(MAX_ENV, "3600")
    with pytest.raises((ValueError, TypeError)):
        pm._execute_gpu_compute(_job(duration_seconds=float("nan")))
    with pytest.raises((ValueError, TypeError)):
        pm._execute_gpu_compute(_job(duration_seconds=-50))


def _run(job, monkeypatch, max_env="3600"):
    """Run the rental with sleep patched; return (sleeps, submitted result extra)."""
    monkeypatch.setenv(MAX_ENV, max_env)
    slept = []
    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success") as submit,
        patch.object(pm, "build_tee_quote", return_value=None),
        patch.object(pm.time, "sleep", lambda s: slept.append(s)),
    ):
        pm._execute_gpu_compute(job)
    return slept, submit.call_args.args[3]


def test_normal_request_runs_its_full_span(monkeypatch):
    slept, extra = _run(_job(duration_seconds=100), monkeypatch)
    assert sum(slept) == 100 and len(slept) == 20
    assert extra["duration_seconds"] == 100 and extra["requested_seconds"] == 100


def test_clamped_result_reports_held_and_requested(monkeypatch):
    slept, extra = _run(_job(duration_seconds=10**8), monkeypatch, max_env="10")
    assert sum(slept) == 10
    assert extra["duration_seconds"] == 10 and extra["requested_seconds"] == 10**8


def test_hours_form_is_converted_and_clamped(monkeypatch):
    slept, _ = _run(_job(duration_hours=0.001), monkeypatch)  # 3.6 s
    assert 3.5 < sum(slept) < 3.7
    slept, _ = _run(_job(duration_hours=1e6), monkeypatch, max_env="15")
    assert sum(slept) == 15


def test_huge_int_and_infinite_hours_do_not_blow_up(monkeypatch):
    slept, _ = _run(_job(duration_seconds=10**400), monkeypatch, max_env="5")
    assert sum(slept) == 5
    slept, _ = _run(_job(duration_hours=1e308), monkeypatch, max_env="5")  # *3600 -> inf
    assert sum(slept) == 5


def test_no_duration_keeps_the_default_hold(monkeypatch):
    slept, extra = _run(_job(), monkeypatch)
    assert sum(slept) == 60 and extra["requested_seconds"] == 60
    slept, _ = _run(_job(duration_seconds=0), monkeypatch)
    assert sum(slept) == 60


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), True, "30", [5], {"s": 1}])
def test_other_bad_durations_are_rejected(monkeypatch, bad):
    monkeypatch.setenv(MAX_ENV, "3600")
    with pytest.raises((ValueError, TypeError)):
        pm._execute_gpu_compute(_job(duration_seconds=bad))


def test_bad_hours_are_rejected(monkeypatch):
    monkeypatch.setenv(MAX_ENV, "3600")
    for bad in (-1, float("nan"), "2"):
        with pytest.raises((ValueError, TypeError)):
            pm._execute_gpu_compute(_job(duration_hours=bad))


def test_deadline_passing_mid_run_ends_the_hold(monkeypatch):
    clock = {"now": 1000.0}
    job = {"job_id": "j1", "payload": {"duration_seconds": 3600}, "expires_at": 1000.0 + 12}
    slept = []

    def _sleep(s):
        slept.append(s)
        clock["now"] += s

    monkeypatch.setenv(MAX_ENV, "3600")
    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success") as submit,
        patch.object(pm, "build_tee_quote", return_value=None),
        patch.object(pm.time, "sleep", _sleep),
        patch.object(pm.time, "time", lambda: clock["now"]),
    ):
        pm._execute_gpu_compute(job)
    assert sum(slept) == 15  # 5 s chunks: 12 s deadline is seen at the 15 s check
    assert submit.call_args.args[3]["duration_seconds"] == 15


def test_iso_deadline_is_honoured(monkeypatch):
    past = datetime.fromtimestamp(time.time() - 60, UTC).isoformat()
    job = {"job_id": "j1", "payload": {"duration_seconds": 3600}, "expires_at": past}
    slept, _ = _run(job, monkeypatch)
    assert slept == []
    naive = datetime.fromtimestamp(time.time() - 60, UTC).replace(tzinfo=None).isoformat()
    slept, _ = _run({**job, "expires_at": naive}, monkeypatch)
    assert slept == []


@pytest.mark.parametrize("junk", ["not a date", None, True, float("nan"), [1]])
def test_unusable_deadline_is_ignored_not_fatal(monkeypatch, junk):
    job = {"job_id": "j1", "payload": {"duration_seconds": 10}, "expires_at": junk}
    slept, _ = _run(job, monkeypatch)
    assert sum(slept) == 10


def test_invalid_ceiling_env_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv(MAX_ENV, "lots")
    assert pm._gpu_compute_max_seconds() == 3600
    monkeypatch.setenv(MAX_ENV, "0")
    assert pm._gpu_compute_max_seconds() == 1
    monkeypatch.delenv(MAX_ENV)
    assert pm._gpu_compute_max_seconds() == 3600
