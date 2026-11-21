"""#2317: a resumed gpu_compute rental holds only the remaining purchased time.

Before the fix a miner restart re-dispatched the RUNNING job and
``_execute_gpu_compute`` re-held the FULL ``duration_seconds`` while the
coordinator's ``expires_at`` kept ticking from the original claim — the rental
could be cut short and the provider went unpaid.

The running-jobs/poll dispatch shape now carries
``gpu_compute: {started_at, duration_seconds, rental_deadline}``. When present
the miner holds ``min(started_at + duration_seconds - now, MAX)`` and breaks at
``rental_deadline`` instead of ``expires_at``. Missing fields (older
coordinator) fall back to the previous behaviour.
"""

from __future__ import annotations

from unittest.mock import patch

import production_miner as pm
import pytest

MAX_ENV = "GPU_COMPUTE_MAX_SECONDS"


def _job(*, gpu_compute=None, expires_at=None, duration_seconds=100):
    payload = {"type": "gpu_compute", "task": "general_compute", "duration_seconds": duration_seconds}
    job = {"job_id": "j1", "payload": payload}
    if gpu_compute is not None:
        job["gpu_compute"] = gpu_compute
    if expires_at is not None:
        job["expires_at"] = expires_at
    return job


def _run(job, monkeypatch, max_env="3600"):
    """Run the rental against a fake clock; return (sleeps, submitted extra)."""
    monkeypatch.setenv(MAX_ENV, max_env)
    clock = {"now": 1_000_000.0}
    slept = []

    def _sleep(s):
        slept.append(s)
        clock["now"] += s

    with (
        patch.object(pm, "_gpu_snapshot", return_value={}),
        patch.object(pm, "_submit_success") as submit,
        patch.object(pm.time, "sleep", _sleep),
        patch.object(pm.time, "time", lambda: clock["now"]),
    ):
        pm._execute_gpu_compute(job)
    return slept, submit.call_args.args[3]


def test_resumed_rental_holds_only_remaining_seconds(monkeypatch):
    """40 s into a 100 s rental, a restart holds ~60 s — not the full 100."""
    now = 1_000_000.0
    job = _job(
        gpu_compute={"started_at": now - 40, "duration_seconds": 100, "rental_deadline": now + 1000},
        expires_at=now - 10,  # queue deadline already past — must not matter
    )
    slept, extra = _run(job, monkeypatch)
    assert sum(slept) == pytest.approx(60, abs=5)
    assert extra["duration_seconds"] == pytest.approx(60, abs=5)
    assert extra["requested_seconds"] == 100


def test_fresh_dispatch_with_window_holds_purchased_span(monkeypatch):
    """Claim→dispatch latency trims the hold slightly; never exceeds it."""
    now = 1_000_000.0
    job = _job(
        gpu_compute={"started_at": now - 2, "duration_seconds": 100, "rental_deadline": now + 1000},
        expires_at=now + 5000,
    )
    slept, extra = _run(job, monkeypatch)
    assert 90 <= sum(slept) <= 100
    assert extra["duration_seconds"] == pytest.approx(sum(slept), abs=0.001)


def test_rental_deadline_breaks_before_expires_at(monkeypatch):
    """The break uses rental_deadline, not a later expires_at."""
    now = 1_000_000.0
    job = _job(
        gpu_compute={"started_at": now - 1, "duration_seconds": 3600, "rental_deadline": now + 12},
        expires_at=now + 100_000,  # far later — must be ignored
    )
    slept, extra = _run(job, monkeypatch)
    assert sum(slept) < 100
    assert extra["duration_seconds"] == sum(slept)


def test_window_without_started_at_falls_back_to_full_hold(monkeypatch):
    """gpu_compute present but no started_at (legacy row) → old behaviour."""
    now = 1_000_000.0
    job = _job(
        gpu_compute={"duration_seconds": 100, "rental_deadline": now + 1000},
        expires_at=now + 5000,
    )
    slept, _ = _run(job, monkeypatch)
    assert sum(slept) == 100


def test_no_window_falls_back_to_expires_at_deadline(monkeypatch):
    """No gpu_compute block at all → the expires_at deadline still applies."""
    now = 1_000_000.0
    job = _job(expires_at=now + 12)
    slept, _ = _run(job, monkeypatch)
    assert sum(slept) < 100  # 5 s chunks: deadline seen at the ~15 s check


def test_remaining_past_window_submits_without_hold(monkeypatch):
    """Rental window already closed → hold 0 and submit immediately."""
    now = 1_000_000.0
    job = _job(
        gpu_compute={"started_at": now - 200, "duration_seconds": 100, "rental_deadline": now + 30},
        expires_at=now - 10,
    )
    slept, extra = _run(job, monkeypatch)
    assert slept == []
    assert extra["duration_seconds"] == 0
