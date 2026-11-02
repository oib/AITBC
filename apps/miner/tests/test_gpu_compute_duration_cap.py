"""Phase-0 pin for GPU-COMPUTE-DURATION-1 (#805).

`_execute_gpu_compute` takes `duration_seconds`/`duration_hours` from the
buyer's payload unchecked and sleeps the whole span in 5 s chunks without
ever re-checking the job's deadline: a 3600 s payload holds the reservation
past `expires_at` and there is no configured maximum.

Desired behaviour (pinned here): the duration is clamped to
min(requested, job ttl remaining, GPU_COMPUTE_MAX_SECONDS) and validated as
a finite positive number, and the sleep loop stops early once the job's
expires_at passes. These tests FAIL on current main — a 10**8 s request is
held and the loop ignores the deadline; that is the bug demonstration.
"""

import time
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
