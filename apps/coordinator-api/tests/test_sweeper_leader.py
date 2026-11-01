"""One sweeper runner per host (COORD-SWEEPERS-PER-WORKER-1, #769).

Every uvicorn worker runs the lifespan; only the worker holding the host-wide
flock starts the sweepers, and the others retry it from a standby task. The
lock tests use real processes where process death matters: the kernel drops
a flock when its holder dies, and that is the whole takeover mechanism.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import pytest

from coordinator_api import main as cmain
from coordinator_api.contexts.infrastructure.routers import admin
from coordinator_api.core import sweeper_leader as sl

# A second worker: takes the lock, reports its role, then holds it until killed.
_HOLDER = """
import sys
from coordinator_api.core.sweeper_leader import SweeperLeaderLock
lock = SweeperLeaderLock(sys.argv[1])
print("leader" if lock.try_lead() else "standby", flush=True)
sys.stdin.read()
"""


def _spawn_holder(path: str) -> tuple[subprocess.Popen[str], str]:
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert proc.stdout is not None
    return proc, proc.stdout.readline().strip()


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


class _TaskManagerSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, tuple]] = []

    async def start_task(self, name, coro, *args, **kwargs) -> None:
        self.calls.append((name, coro, args))


@pytest.fixture
def lock_path(tmp_path) -> str:
    return str(tmp_path / "coordinator-sweepers.lock")


@pytest.fixture
def started(monkeypatch) -> list[object]:
    """Replace _start_sweepers with a recorder of the task manager it was given."""
    calls: list[object] = []

    async def _record(task_manager) -> None:
        calls.append(task_manager)

    monkeypatch.setattr(cmain, "_start_sweepers", _record)
    return calls


@pytest.mark.unit
class TestLeaderLock:
    def test_a_second_process_stands_by(self, lock_path):
        first, first_role = _spawn_holder(lock_path)
        try:
            second, second_role = _spawn_holder(lock_path)
            _stop(second)
        finally:
            _stop(first)
        assert (first_role, second_role) == ("leader", "standby")

    def test_the_standby_leads_once_the_leader_process_dies(self, lock_path):
        holder, role = _spawn_holder(lock_path)
        mine = sl.SweeperLeaderLock(lock_path)
        try:
            assert role == "leader"
            assert mine.try_lead() is False
            assert mine.role == sl.ROLE_STANDBY
            assert mine.leader_pid() == holder.pid

            holder.kill()  # a crash, not a clean shutdown: nothing releases the lock
            holder.wait(timeout=10)

            assert mine.try_lead() is True
            assert mine.role == sl.ROLE_LEADER
            assert mine.leader_pid() == os.getpid()
            assert os.path.exists(lock_path)  # the file is never unlinked
        finally:
            _stop(holder)
            mine.abandon()

    def test_two_locks_in_one_process_still_exclude(self, lock_path):
        a, b = sl.SweeperLeaderLock(lock_path), sl.SweeperLeaderLock(lock_path)
        try:
            assert a.try_lead() is True
            assert b.try_lead() is False
            assert a.try_lead() is True  # the leader keeps leading
        finally:
            a.abandon()
            b.abandon()

    def test_an_unusable_lock_path_sweeps_unguarded(self, tmp_path):
        lock = sl.SweeperLeaderLock(str(tmp_path / "no-such-dir" / "coordinator-sweepers.lock"))
        assert lock.try_lead() is True
        assert lock.role == sl.ROLE_UNGUARDED

    def test_disabled_runs_the_sweepers_even_when_another_worker_leads(self, lock_path):
        holder = sl.SweeperLeaderLock(lock_path)
        off = sl.SweeperLeaderLock(lock_path, enabled=False)
        try:
            assert holder.try_lead() is True
            assert off.try_lead() is True
            assert off.role == sl.ROLE_DISABLED
        finally:
            holder.abandon()


@pytest.mark.unit
class TestSettings:
    @pytest.mark.parametrize(
        ("raw", "expected"), [(None, True), ("true", True), ("false", False), ("0", False), ("off", False)]
    )
    def test_leader_enabled(self, monkeypatch, raw, expected):
        if raw is None:
            monkeypatch.delenv("COORDINATOR_SWEEPER_LEADER_ENABLED", raising=False)
        else:
            monkeypatch.setenv("COORDINATOR_SWEEPER_LEADER_ENABLED", raw)
        assert sl.leader_enabled() is expected

    @pytest.mark.parametrize(("raw", "expected"), [(None, 30.0), ("0.2", 0.2), ("junk", 30.0), ("0", 0.1)])
    def test_standby_retry_seconds(self, monkeypatch, raw, expected):
        if raw is None:
            monkeypatch.delenv("COORDINATOR_SWEEPER_STANDBY_RETRY_SECONDS", raising=False)
        else:
            monkeypatch.setenv("COORDINATOR_SWEEPER_STANDBY_RETRY_SECONDS", raw)
        assert sl.standby_retry_seconds() == expected

    def test_get_leader_lock_reads_the_environment_once(self, monkeypatch, lock_path):
        monkeypatch.setattr(sl, "_leader_lock", None)
        monkeypatch.setenv("COORDINATOR_SWEEPER_LEADER_LOCK_PATH", lock_path)
        monkeypatch.setenv("COORDINATOR_SWEEPER_LEADER_ENABLED", "false")
        lock = sl.get_leader_lock()
        assert (lock.path, lock.enabled, lock.role) == (lock_path, False, sl.ROLE_PENDING)
        assert sl.get_leader_lock() is lock


@pytest.mark.unit
class TestStartup:
    async def test_two_workers_start_the_sweepers_once_and_the_standby_takes_over(self, monkeypatch, lock_path, started):
        monkeypatch.setenv("COORDINATOR_SWEEPER_STANDBY_RETRY_SECONDS", "0.1")
        worker_a, worker_b = sl.SweeperLeaderLock(lock_path), sl.SweeperLeaderLock(lock_path)
        tm_a, tm_b = _TaskManagerSpy(), _TaskManagerSpy()
        try:
            monkeypatch.setattr(sl, "get_leader_lock", lambda: worker_a)
            await cmain._start_sweepers_when_leader(tm_a)
            monkeypatch.setattr(sl, "get_leader_lock", lambda: worker_b)
            await cmain._start_sweepers_when_leader(tm_b)

            assert started == [tm_a]
            assert [(name, coro) for name, coro, _ in tm_b.calls] == [("sweeper_standby", cmain._sweeper_standby)]
            assert tm_b.calls[0][2] == (tm_b, worker_b, 0.1)

            standby = asyncio.create_task(cmain._sweeper_standby(*tm_b.calls[0][2]))
            await asyncio.sleep(0.35)
            assert started == [tm_a]  # A still holds the lock

            worker_a.abandon()  # as if worker A died
            await asyncio.wait_for(standby, timeout=5)
            assert started == [tm_a, tm_b]
            assert worker_b.role == sl.ROLE_LEADER
        finally:
            worker_a.abandon()
            worker_b.abandon()

    async def test_an_unusable_lock_still_starts_the_sweepers(self, monkeypatch, tmp_path, started):
        lock = sl.SweeperLeaderLock(str(tmp_path / "no-such-dir" / "coordinator-sweepers.lock"))
        monkeypatch.setattr(sl, "get_leader_lock", lambda: lock)
        tm = _TaskManagerSpy()
        await cmain._start_sweepers_when_leader(tm)
        assert started == [tm]
        assert tm.calls == []

    async def test_disabled_starts_the_sweepers_in_every_worker(self, monkeypatch, lock_path, started):
        workers = [sl.SweeperLeaderLock(lock_path, enabled=False) for _ in range(2)]
        managers = [_TaskManagerSpy(), _TaskManagerSpy()]
        for worker, tm in zip(workers, managers, strict=True):
            monkeypatch.setattr(sl, "get_leader_lock", lambda worker=worker: worker)
            await cmain._start_sweepers_when_leader(tm)
        assert started == managers
        assert all(tm.calls == [] for tm in managers)


class _FakeRegistry:
    def __init__(self, statuses):
        self._statuses = statuses

    def get_task_status(self):
        return dict(self._statuses)


class _Sweeper:
    def __init__(self):
        self.interval_seconds = 60


@pytest.mark.unit
class TestAdminReport:
    def _report(self, monkeypatch, lock, statuses):
        import coordinator_api.core.lifecycle as lifecycle

        specs = [("on", lambda: True, _Sweeper, "enabled"), ("off", lambda: False, _Sweeper, "disabled")]
        monkeypatch.setattr(lifecycle, "get_task_manager", lambda: _FakeRegistry(statuses))
        monkeypatch.setattr(admin, "_sweeper_specs", lambda: specs)
        monkeypatch.setattr(admin, "_extra_config", lambda name: {})
        monkeypatch.setattr(sl, "get_leader_lock", lambda: lock)
        return admin.collect_sweeper_report()

    def test_a_standby_worker_reports_standby_not_degraded(self, monkeypatch, lock_path):
        leader, standby = sl.SweeperLeaderLock(lock_path), sl.SweeperLeaderLock(lock_path)
        try:
            assert leader.try_lead() is True
            assert standby.try_lead() is False
            report = self._report(monkeypatch, standby, {"sweeper_standby": "running"})
        finally:
            leader.abandon()
        by_name = {entry["name"]: entry for entry in report["sweepers"]}
        assert (report["leader"], report["sweeper_role"], report["leader_pid"]) == (False, "standby", os.getpid())
        assert by_name["on"]["status"] == f"standby (sweeper leader pid {os.getpid()})"
        assert by_name["on"]["healthy"] is True
        assert by_name["off"]["status"] == "disabled"
        assert report["degraded"] == []
        assert report["other_tasks"] == [{"name": "sweeper_standby", "status": "running"}]

    def test_the_leader_keeps_the_existing_classification(self, monkeypatch, lock_path):
        leader = sl.SweeperLeaderLock(lock_path)
        try:
            assert leader.try_lead() is True
            report = self._report(monkeypatch, leader, {})
        finally:
            leader.abandon()
        assert (report["leader"], report["sweeper_role"]) == (True, "leader")
        assert report["sweepers"][0]["status"] == "not started"
        assert report["degraded"] == ["on"]
