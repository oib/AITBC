"""Regression tests for HERMES-RESIDUAL-1 (#1683) + HERMES-OUT-1 (#1666).

- A cancelled /run task (client disconnect, service shutdown) must kill the
  child's whole process group — previously only TimeoutError triggered the
  killpg path, so a cancelled run leaked a detached hermes with no timeout.
- stdout/stderr are drained with a byte cap: communicate() used to buffer
  the child's entire output in RAM (unbounded per stream, x4 concurrent).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

# Same unique-module-name convention as test_proc_group_kill.py.
_spec = importlib.util.spec_from_file_location("aitbc_hermes_main_bounds", Path(__file__).resolve().parents[1] / "main.py")
hermes = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["aitbc_hermes_main_bounds"] = hermes
_spec.loader.exec_module(hermes)

HermesRunRequest = hermes.HermesRunRequest


def _patch_hermes(monkeypatch: pytest.MonkeyPatch, fake: Path) -> None:
    monkeypatch.setattr(hermes, "_HERMES_PATH", str(fake))
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])


@pytest.mark.asyncio
async def test_cancellation_kills_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancelling the run task kills the child AND its in-group grandchild."""
    pidfile = tmp_path / "hermes.pid"
    gcpidfile = tmp_path / "grandchild.pid"
    fake = tmp_path / "fake-hermes"
    fake.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nsleep 300 & echo $! > {gcpidfile}\nexec sleep 300\n")
    fake.chmod(0o755)
    _patch_hermes(monkeypatch, fake)

    task = asyncio.create_task(hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=300)))
    # Wait until the fake has spawned and recorded both pids.
    for _ in range(200):
        if pidfile.exists() and gcpidfile.exists():
            break
        await asyncio.sleep(0.05)
    assert pidfile.exists() and gcpidfile.exists()
    pid = int(pidfile.read_text().strip())
    gcpid = int(gcpidfile.read_text().strip())

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The reap inside the cancel path completes before CancelledError
    # propagates, so both pids must already be gone (killpg covered the
    # grandchild because it stayed in the child's process group).
    for dead_pid in (pid, gcpid):
        with pytest.raises(ProcessLookupError):
            os.kill(dead_pid, 0)


@pytest.mark.asyncio
async def test_stdout_is_capped_and_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Output beyond _HERMES_MAX_OUTPUT_BYTES is truncated, not buffered whole."""
    fake = tmp_path / "fake-hermes"
    fake.write_text("#!/bin/sh\nhead -c 20000 /dev/zero | tr '\\0' 'a'\n")
    fake.chmod(0o755)
    _patch_hermes(monkeypatch, fake)
    monkeypatch.setattr(hermes, "_HERMES_MAX_OUTPUT_BYTES", 1024)

    start = time.monotonic()
    resp = await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=30))
    elapsed = time.monotonic() - start

    body = json.loads(resp.body)
    assert body["output_truncated"] is True
    # 'a' * 20000 stripped -> capped at the 1024-byte retention limit.
    assert len(body["text"]) == 1024
    assert body["text"] == "a" * 1024
    # And it must still complete promptly — no unbounded buffering stall.
    assert elapsed < 30


@pytest.mark.asyncio
async def test_small_output_not_flagged_truncated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Output under the cap keeps output_truncated=False."""
    fake = tmp_path / "fake-hermes"
    fake.write_text("#!/bin/sh\nprintf 'hello hermes\\n'\n")
    fake.chmod(0o755)
    _patch_hermes(monkeypatch, fake)
    monkeypatch.setattr(hermes, "_HERMES_MAX_OUTPUT_BYTES", 1024)

    resp = await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=30))
    body = json.loads(resp.body)
    assert body["text"] == "hello hermes"
    assert body["output_truncated"] is False


@pytest.mark.asyncio
async def test_mid_run_failure_kills_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1683 residual: a non-timeout mid-run failure (e.g. a pipe error inside
    the bounded drain) must kill the child too — the BaseException path does
    the same killpg+reap as timeout/cancel, then propagates."""
    pidfile = tmp_path / "hermes.pid"
    fake = tmp_path / "fake-hermes"
    fake.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 300\n")
    fake.chmod(0o755)
    _patch_hermes(monkeypatch, fake)

    async def boom(proc, limit):
        # Wait until the child has recorded its pid, then fail mid-run.
        for _ in range(200):
            if pidfile.exists():
                break
            await asyncio.sleep(0.05)
        raise RuntimeError("simulated pipe failure")

    monkeypatch.setattr(hermes, "_communicate_bounded", boom)

    with pytest.raises(RuntimeError, match="simulated pipe failure"):
        await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=300))

    # killpg+reap ran before the exception propagated: the child is gone.
    pid = int(pidfile.read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_timeout_still_504s_with_bounded_drain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The #1473 timeout path still works after the communicate() rewrite."""
    fake = tmp_path / "fake-hermes"
    fake.write_text("#!/bin/sh\nsetsid sleep 300 &\nexec sleep 300\n")
    fake.chmod(0o755)
    _patch_hermes(monkeypatch, fake)
    monkeypatch.setattr(hermes, "_POST_KILL_DRAIN_SECONDS", 1.0)

    start = time.monotonic()
    with pytest.raises(HTTPException) as exc_info:
        await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=1))
    elapsed = time.monotonic() - start

    assert exc_info.value.status_code == 504
    assert elapsed < 30
