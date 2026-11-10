"""Regression test for HERMES-PROC-1 (#1473).

On max_time timeout the run must kill the whole process group: the agent
runs with start_new_session=True, so grandchildren (tool subprocesses)
share its process group. Killing only the direct child leaves grandchildren
holding the stdout/stderr pipes and communicate() blocks until they exit —
the enforced time bound is then a lie.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as hermes
from main import HermesRunRequest


@pytest.mark.asyncio
async def test_timeout_kills_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A timed-out run returns 504 promptly even when a grandchild holds the pipes."""
    fake = tmp_path / "fake-hermes"
    # Spawns a background child that inherits stdout/stderr, then sleeps
    # itself — exactly the shape that used to hang communicate() for the
    # grandchild's full lifetime after proc.kill().
    fake.write_text("#!/bin/sh\nsleep 300 &\nexec sleep 300\n")
    fake.chmod(0o755)

    monkeypatch.setattr(hermes, "_HERMES_PATH", str(fake))
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])

    request = HermesRunRequest(prompt="x", max_time=1)
    start = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        await hermes._run_hermes_inner(request)
    elapsed = time.monotonic() - start

    assert exc_info.value.status_code == 504
    # communicate() must not wait out the grandchildren's 300s sleeps.
    assert elapsed < 60


@pytest.mark.asyncio
async def test_timeout_bounds_drain_past_group_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A grandchild that escaped the process group cannot stretch the bound.

    ``setsid`` puts the sleeper in a new session AND a new process group, so
    os.killpg(proc.pid) cannot reach it; it keeps the inherited pipes open
    forever. The post-kill drain is capped by _POST_KILL_DRAIN_SECONDS, so
    the 504 still returns promptly (#1473 residual).
    """
    fake = tmp_path / "fake-hermes"
    fake.write_text("#!/bin/sh\nsetsid sleep 300 &\nexec sleep 300\n")
    fake.chmod(0o755)

    monkeypatch.setattr(hermes, "_HERMES_PATH", str(fake))
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])
    monkeypatch.setattr(hermes, "_POST_KILL_DRAIN_SECONDS", 1.0)

    request = HermesRunRequest(prompt="x", max_time=1)
    start = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        await hermes._run_hermes_inner(request)
    elapsed = time.monotonic() - start

    assert exc_info.value.status_code == 504
    # 1s max_time + ~1s drain bound — nowhere near the escapee's 300s sleep.
    assert elapsed < 30
