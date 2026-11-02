"""#827: one escrow's release/refund is serialised across RPC *worker processes* on sqlite.

``escrow_mutation`` took its cross-worker lock only on Postgres; every node's chain.db is
sqlite, so a second ``--workers`` process was never excluded. These tests run real
processes against one file-backed sqlite database: the exclusion, the timeout, a
crashed holder, and the stripe choice that has to be the same in every process.
"""

import asyncio
import fcntl
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import pytest
from aitbc_chain.contracts import escrow_txn
from aitbc_chain.contracts.escrow_txn import LOCK_DIR_NAME, LOCK_STRIPES, EscrowBusy, escrow_mutation, lock_stripe
from sqlalchemy import create_engine
from sqlmodel import Session

# A child process: takes the lock for JOB on the sqlite file DB, logs enter/exit/busy lines.
_CHILD = r"""
import asyncio, os, sys, time
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlmodel import Session
from aitbc_chain.contracts import escrow_txn

db, job, log, hold, timeout, mode = sys.argv[1:7]
os.environ["ESCROW_MUTATION_LOCK_TIMEOUT_SECONDS"] = timeout
engine = create_engine(f"sqlite:///{db}")


@contextmanager
def scope():
    with Session(engine) as session:
        yield session


def note(word):
    with open(log, "a") as fh:
        fh.write(f"{word} {os.getpid()} {time.time()}\n")


async def main():
    try:
        async with escrow_txn.escrow_mutation(job, scope):
            note("enter")
            if mode == "hang":
                time.sleep(120)
            await asyncio.sleep(float(hold))
            note("exit")
    except escrow_txn.EscrowBusy:
        note("busy")


asyncio.run(main())
"""


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}


class _Procs:
    def __init__(self, db: Path, log: Path) -> None:
        self.db, self.log, self.procs = db, log, []

    def start(self, job: str, hold: float = 0.0, timeout: int = 30, mode: str = "run") -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(self.db), job, str(self.log), str(hold), str(timeout), mode],
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.procs.append(proc)
        return proc

    def lines(self) -> list[tuple[str, int, float]]:
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_text().splitlines():
            word, pid, at = line.split()
            out.append((word, int(pid), float(at)))
        return out

    def at(self, word: str, pid: int) -> float | None:
        return next((t for w, p, t in self.lines() if w == word and p == pid), None)

    def kill_all(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)


def _wait(predicate: Callable[[], bool], timeout: float = 30.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


@pytest.fixture
def procs(tmp_path):
    db = tmp_path / "chain.db"
    create_engine(f"sqlite:///{db}").dispose()
    helper = _Procs(db, tmp_path / "events.log")
    yield helper
    helper.kill_all()


def _finish(proc: subprocess.Popen) -> None:
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0, out.decode()


# ---- the stripe -----------------------------------------------------------------------


def test_stripe_is_stable_across_processes_and_hash_seeds():
    """hash() is randomised per process; a stripe taken from it would exclude nothing."""
    jobs = ["job-1", "job-2", "0xabc", "x" * 200]
    code = f"from aitbc_chain.contracts.escrow_txn import lock_stripe; print(*(lock_stripe(j) for j in {jobs!r}))"
    seen = set()
    for seed in ("1", "2", "random"):
        out = subprocess.run(
            [sys.executable, "-c", code], env={**_env(), "PYTHONHASHSEED": seed}, capture_output=True, text=True, check=True
        )
        seen.add(out.stdout.strip())
    assert seen == {" ".join(str(lock_stripe(j)) for j in jobs)}


def test_stripe_is_in_range_and_spreads_jobs():
    stripes = {lock_stripe(f"job-{i}") for i in range(2000)}
    assert all(0 <= s < LOCK_STRIPES for s in stripes)
    assert len(stripes) > LOCK_STRIPES * 0.9


# ---- two real processes ---------------------------------------------------------------


def test_second_process_waits_for_the_first_and_never_overlaps(procs):
    first = procs.start("job-x", hold=1.0)
    _wait(lambda: procs.at("enter", first.pid) is not None, what="first process to take the lock")
    second = procs.start("job-x", hold=0.2)
    _finish(first)
    _finish(second)

    assert procs.at("exit", first.pid) is not None and procs.at("exit", second.pid) is not None
    assert procs.at("enter", second.pid) >= procs.at("exit", first.pid), "the second worker ran inside the first's hold"


def test_second_process_gives_up_with_busy_after_the_timeout(procs):
    first = procs.start("job-x", hold=60.0)
    _wait(lambda: procs.at("enter", first.pid) is not None, what="first process to take the lock")
    second = procs.start("job-x", timeout=1)
    _finish(second)

    assert any(w == "busy" and p == second.pid for w, p, _ in procs.lines())
    assert procs.at("enter", second.pid) is None, "the busy caller's body must never run"


def test_a_killed_holder_does_not_leave_the_escrow_locked(procs):
    first = procs.start("job-x", mode="hang")
    _wait(lambda: procs.at("enter", first.pid) is not None, what="first process to take the lock")
    killed_at = time.time()
    os.kill(first.pid, signal.SIGKILL)
    second = procs.start("job-x", timeout=20)
    _finish(second)

    assert procs.at("enter", second.pid) is not None
    assert procs.at("enter", second.pid) - killed_at < 15


def test_jobs_on_different_stripes_do_not_wait_for_each_other(procs):
    job_a = "job-a"
    job_b = next(f"job-b{i}" for i in range(100) if lock_stripe(f"job-b{i}") != lock_stripe(job_a))
    first = procs.start(job_a, hold=60.0)
    _wait(lambda: procs.at("enter", first.pid) is not None, what="first process to take the lock")
    second = procs.start(job_b, hold=0.1)
    _finish(second)

    assert procs.at("exit", second.pid) is not None, "a job on another stripe was held up by the first"
    assert procs.at("exit", first.pid) is None, "the first holder is still inside its hold"


# ---- in-process behaviour of the file lock ---------------------------------------------


@pytest.fixture
def file_scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")

    @contextmanager
    def _scope():
        with Session(engine) as session:
            yield session

    return _scope, tmp_path


@pytest.mark.asyncio
async def test_lock_files_are_created_beside_the_database(file_scope):
    scope, tmp_path = file_scope
    async with escrow_mutation("job-1", scope):
        files = list((tmp_path / LOCK_DIR_NAME).iterdir())
    assert [f.name for f in files] == [f"stripe-{lock_stripe('job-1'):03d}.lock"]
    assert (tmp_path / LOCK_DIR_NAME).stat().st_mode & 0o777 == 0o700
    assert files[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="counts open fds through /proc")
async def test_no_file_descriptor_leaks_on_success_or_error(file_scope):
    scope, _ = file_scope
    async with escrow_mutation("warm-up", scope):
        pass
    before = len(os.listdir("/proc/self/fd"))
    for i in range(50):
        async with escrow_mutation(f"job-{i}", scope):
            pass
    for i in range(10):
        with pytest.raises(RuntimeError):
            async with escrow_mutation(f"job-{i}", scope):
                raise RuntimeError("handler failed")
    assert len(os.listdir("/proc/self/fd")) == before


@contextmanager
def _flock_held(path: Path):
    """Hold the stripe's flock from this process, on its own open file description."""
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="counts open fds through /proc")
async def test_no_file_descriptor_leaks_when_the_file_lock_times_out(file_scope, monkeypatch):
    scope, tmp_path = file_scope
    monkeypatch.setattr(escrow_txn, "lock_timeout_seconds", lambda: 0.05)
    async with escrow_mutation("job-1", scope):
        pass
    stripe = tmp_path / LOCK_DIR_NAME / f"stripe-{lock_stripe('job-1'):03d}.lock"
    with _flock_held(stripe):
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(10):
            with pytest.raises(EscrowBusy):
                async with escrow_mutation("job-1", scope):
                    pytest.fail("the busy caller must never run its body")
        assert len(os.listdir("/proc/self/fd")) == before
    async with escrow_mutation("job-1", scope):
        pass


@pytest.mark.asyncio
async def test_busy_in_process_releases_nothing_it_did_not_take(file_scope, monkeypatch):
    scope, _ = file_scope
    monkeypatch.setattr(escrow_txn, "lock_timeout_seconds", lambda: 0.05)
    async with escrow_mutation("job-1", scope):
        with pytest.raises(EscrowBusy):
            async with escrow_mutation("job-1", scope):
                pytest.fail("the busy caller must never run its body")
        # The holder still holds: a third caller is busy too, not let in by the failed one.
        with pytest.raises(EscrowBusy):
            async with escrow_mutation("job-1", scope):
                pytest.fail("the busy caller must never run its body")
    async with escrow_mutation("job-1", scope):
        pass


@pytest.mark.asyncio
async def test_an_unusable_lock_directory_fails_closed(file_scope, caplog):
    scope, tmp_path = file_scope
    (tmp_path / LOCK_DIR_NAME).write_text("not a directory")
    with pytest.raises(OSError):
        async with escrow_mutation("job-1", scope):
            pytest.fail("the body must not run unlocked")
    assert "Escrow lock file" in caplog.text
    # The in-process lock was given back: nothing is stuck behind the failure.
    assert len(escrow_txn._process_locks) == 0 or not any(lock.locked() for lock in escrow_txn._process_locks.values())


@pytest.mark.asyncio
async def test_in_memory_sqlite_takes_no_file_lock(monkeypatch):
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @contextmanager
    def scope():
        with Session(engine) as session:
            yield session

    async def _no_file_lock(*args, **kwargs):
        pytest.fail("an in-memory database has no file to lock beside")

    monkeypatch.setattr(escrow_txn, "_acquire_file_lock", _no_file_lock)
    async with escrow_mutation("job-1", scope):
        await asyncio.sleep(0)
