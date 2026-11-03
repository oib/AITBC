"""One escrow's release/refund, serialised across every RPC worker (#780 step c).

The RPC runs ``--workers N`` processes and each used to guard a release with an
``asyncio.Lock`` that only its own process could see, so two workers could both
pass the "is it still locked?" read and both settle. ``escrow_mutation`` replaces
that with a transaction-scoped Postgres advisory lock keyed on the job, the same
precedent as the mempool's slot lock (``mempool._slot_advisory_lock``): it
serialises every process that talks to the database, and Postgres drops it when the
transaction ends -- commit, rollback, or a dead connection -- so a crashed worker can
never leave an escrow locked.

The handler takes the lock *before* it reads the row, so the second caller waits,
then sees what the first committed (``released_at`` set) and answers "already
released" instead of settling again. The row write goes through the same
transaction (``EscrowMutation.write``): the mutation and the lock release are one
commit, with no window between them.

Not on Postgres (the chain database of every node, which is sqlite): an in-process
``asyncio.Lock`` per job queues the callers of one worker, and an ``fcntl.flock`` on a
lock file beside ``chain.db`` excludes the other workers (#827). The in-process lock
alone is not enough: the RPC runs ``--workers N`` processes against one ``chain.db``,
and a second process never sees the first one's ``asyncio.Lock``.

The file lock is per-job (one file per ``sha256(job_id)`` under
job id), so the lock directory stays a fixed size and no file is ever unlinked while
another process may be opening it. The stripe must be a stable hash: Python's own
``hash()`` is randomised per process, which would give each worker a different stripe
and exclude nothing. The kernel drops a ``flock`` when its process dies, so a crashed
worker cannot leave an escrow locked, and nothing waits on sqlite's database-wide
writer lock. ``BEGIN IMMEDIATE`` (the sketch for step c) would, held across the
settlement submit -- an HTTP round trip to the same node -- stall the block producer
and every other writer, so it is deliberately not used.

A lock file that cannot be created or opened fails the mutation (it is logged and
raised, never skipped): running unlocked would be the bug this exists to prevent. An
in-memory or file-less sqlite database (the unit tests) has nothing to lock and keeps
the in-process lock alone.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import time
import weakref
import hashlib
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, NamedTuple

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# One key space for release and refund: they settle the same escrow and must exclude
# each other, not just themselves.
LOCK_KEY_PREFIX = "escrow_release:"

# How long a caller waits for another worker's release/refund of the same escrow
# before giving up with EscrowBusy. A settlement submit is one signed HTTP round trip,
# so a holder normally lets go within seconds; the bound exists so a hung holder
# cannot pin every retry behind it.
LOCK_TIMEOUT_ENV = "ESCROW_MUTATION_LOCK_TIMEOUT_SECONDS"
DEFAULT_LOCK_TIMEOUT_SECONDS = 30

_PG_LOCK_NOT_AVAILABLE = "55P03"

# Cross-process lock for a file-backed sqlite chain.db (#827, keyed per-job in
# #834): one lock file per job hash in LOCK_DIR_NAME beside the database,
# polled without blocking a thread. Stripe files (a fixed modulo key space)
# let two unrelated escrows collide — the loser polled the whole timeout for
# a busy it had nothing to do with. Per-job files remove the collision class;
# they are never unlinked while held (an unlinked inode and a fresh open at
# the same path are different locks), so the directory just grows one tiny
# file per escrow ever settled.
LOCK_DIR_NAME = "escrow-locks"
_FLOCK_POLL_SECONDS = 0.05

# In-process fallback (non-Postgres). Weak values: a lock nobody holds or waits on is
# dropped, so the map does not grow with every job ever released.
_process_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


class EscrowBusy(Exception):
    """Another worker holds this escrow's release/refund lock and did not let go in time."""


def lock_timeout_seconds() -> int:
    raw = os.environ.get(LOCK_TIMEOUT_ENV, "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_LOCK_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_LOCK_TIMEOUT_SECONDS


def _is_lock_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code == _PG_LOCK_NOT_AVAILABLE


SessionScope = Callable[[], AbstractContextManager[Session]]


def _default_scope() -> AbstractContextManager[Session]:
    from ..database import session_scope

    return session_scope()


class EscrowMutation:
    """The held lock. ``session`` is the lock-holding transaction on Postgres, else None."""

    def __init__(self, job_id: str, session: Session | None, scope: SessionScope) -> None:
        self.job_id = job_id
        self.session = session
        self._scope = scope

    async def write(self, fn: Callable[[Session], None]) -> None:
        """Run a row write inside the lock's transaction, or in its own where there is none.

        ``fn`` receives the session and must not commit: on Postgres the commit happens
        when the lock is released, so the write and the release are one step; elsewhere
        this helper commits for it, as the handlers always did.
        """
        if self.session is not None:
            session = self.session

            def _in_lock() -> None:
                fn(session)
                session.flush()  # noqa: unawaited-async — sync Session, runs in a worker thread

            await run_in_threadpool(_in_lock)
            return

        def _own_session() -> None:
            with self._scope() as session:
                fn(session)
                session.commit()  # noqa: unawaited-async — sync Session, runs in a worker thread

        await run_in_threadpool(_own_session)


class _Opened(NamedTuple):
    """What ``_open_locked_session`` found: a lock-holding session (Postgres), or, for any
    other database, the sqlite file to lock beside (None when there is no file)."""

    scope: Any = None
    session: Session | None = None
    sqlite_path: str | None = None


def _sqlite_file(session: Session) -> str | None:
    database = session.get_bind().engine.url.database
    return database if database and database != ":memory:" else None


def _open_locked_session(scope_factory: SessionScope, job_id: str, timeout_seconds: int) -> _Opened:
    """Open a session and take the advisory lock; on any other database, say where its file is."""
    scope = scope_factory()
    session = scope.__enter__()
    try:
        if session.get_bind().dialect.name != "postgresql":
            sqlite_path = _sqlite_file(session)
            scope.__exit__(None, None, None)
            return _Opened(sqlite_path=sqlite_path)
        conn = session.connection()
        # SET LOCAL lasts for this transaction only, so the pooled connection comes
        # back with the server default.
        conn.execute(text(f"SET LOCAL lock_timeout = {int(timeout_seconds) * 1000}"))
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": LOCK_KEY_PREFIX + job_id})
        return _Opened(scope=scope, session=session)
    except BaseException as exc:
        scope.__exit__(type(exc), exc, exc.__traceback__)
        raise


def _close(scope: Any, session: Session, *, commit: bool) -> None:
    try:
        if commit:
            session.commit()
        else:
            session.rollback()
    finally:
        scope.__exit__(None, None, None)


def lock_file_name(job_id: str) -> str:
    """The job's lock file name: stable across processes, one file per job.

    ``sha256`` not ``hash()`` (randomised per process) and not a modulo
    stripe (two jobs on one stripe queue against each other, #834). The
    hash also keeps any character a job_id may carry out of the filename.
    """
    return f"job-{hashlib.sha256(job_id.encode()).hexdigest()[:32]}.lock"


def _lock_file_path(sqlite_path: str, job_id: str) -> Path:
    return Path(sqlite_path).parent / LOCK_DIR_NAME / lock_file_name(job_id)


async def _acquire_file_lock(sqlite_path: str, job_id: str, timeout: float) -> int:
    """Take the job's stripe lock; the fd is the lock. EscrowBusy once ``timeout`` runs out."""
    path = _lock_file_path(sqlite_path, job_id)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError as exc:
        logger.error("Escrow lock file %s unavailable for job_id=%s: %s", path, job_id, exc)
        raise
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    logger.warning(
                        "escrow mutation busy: job_id=%s lock_file=%s waited %.1fs",
                        job_id,
                        path.name,
                        timeout,
                    )
                    raise EscrowBusy(job_id) from None
            await asyncio.sleep(_FLOCK_POLL_SECONDS)
    except BaseException:
        os.close(fd)  # noqa: unawaited-async — os.close is a synchronous syscall
        raise


def _release_file_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


#: Timeout for the synchronous row lock below. The async mutation path waits
#: up to LOCK_TIMEOUT_ENV seconds because its caller is a settlement route;
#: the sweeper/backfill writers only skip a pass or a heal when busy, so a
#: short budget keeps a read path from queueing behind a slow settlement.
ROW_LOCK_TIMEOUT_ENV = "ESCROW_ROW_LOCK_TIMEOUT_SECONDS"
DEFAULT_ROW_LOCK_TIMEOUT_SECONDS = 5


def _row_lock_timeout_seconds() -> float:
    raw = os.environ.get(ROW_LOCK_TIMEOUT_ENV, "")
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_ROW_LOCK_TIMEOUT_SECONDS)
    return value if value > 0 else float(DEFAULT_ROW_LOCK_TIMEOUT_SECONDS)


@contextmanager
def escrow_row_lock(session: Session, job_id: str, timeout: float | None = None) -> Iterator[bool]:
    """Synchronous per-job lock for non-route writers (#831).

    The settlement-mark sweeper and ``backfill_settlement_legs`` commit
    outside ``escrow_mutation`` — they run in worker threads, so the async
    path does not fit. They take the same stripe-file flock the routes poll
    (a second flock fd excludes even inside one process), which serialises
    a sweeper/backfill write against any route's release/refund of the same
    job in this worker or any other.

    Yields True with the lock held — the caller MUST ``session.refresh``
    the row inside: a route that committed before this lock was taken is
    only visible on fresh attributes. Yields False on timeout or an
    unavailable lock file, in which case the caller skips the write
    (fail closed — the stale-write defect exists precisely because these
    paths wrote unlocked). A fileless (in-memory) database has nothing to
    lock beside and yields True ungated.
    """
    sqlite_path = _sqlite_file(session)
    if sqlite_path is None:
        yield True
        return
    path = _lock_file_path(sqlite_path, job_id)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError as exc:
        logger.error("Escrow row lock file %s unavailable for job_id=%s: %s", path, job_id, exc)
        yield False
        return
    try:
        deadline = time.monotonic() + (timeout if timeout is not None else _row_lock_timeout_seconds())
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(_FLOCK_POLL_SECONDS)
        yield True
    finally:
        os.close(fd)  # closing releases the flock either way


@asynccontextmanager
async def _process_lock(job_id: str, sqlite_path: str | None, timeout: float) -> AsyncIterator[None]:
    """The non-Postgres lock: this worker's asyncio lock, then the file lock for other workers."""
    deadline = time.monotonic() + timeout
    lock = _process_locks.get(job_id)
    if lock is None:
        lock = _process_locks.setdefault(job_id, asyncio.Lock())
    try:
        await asyncio.wait_for(lock.acquire(), timeout)
    except TimeoutError as exc:
        raise EscrowBusy(job_id) from exc
    fd: int | None = None
    try:
        if sqlite_path is not None:
            fd = await _acquire_file_lock(sqlite_path, job_id, max(0.0, deadline - time.monotonic()))
        yield
    finally:
        if fd is not None:
            _release_file_lock(fd)
        lock.release()  # noqa: unawaited-async — asyncio.Lock.release() is synchronous


@asynccontextmanager
async def escrow_mutation(job_id: str, scope: SessionScope | None = None) -> AsyncIterator[EscrowMutation]:
    """Hold the escrow's release/refund lock for the duration of the block.

    ``scope`` opens the chain-database session (the routes pass their own
    ``session_scope``); the default is ``database.session_scope``. Raises
    ``EscrowBusy`` if another worker keeps the lock past the timeout. A handler that
    raises rolls the transaction back (and so releases the lock); one that returns
    commits whatever it wrote through ``EscrowMutation.write``.
    """
    scope_factory = scope or _default_scope
    timeout = lock_timeout_seconds()
    try:
        opened = await run_in_threadpool(_open_locked_session, scope_factory, job_id, timeout)
    except DBAPIError as exc:
        if _is_lock_timeout(exc):
            raise EscrowBusy(job_id) from exc
        raise

    if opened.session is None:
        async with _process_lock(job_id, opened.sqlite_path, timeout):
            yield EscrowMutation(job_id, None, scope_factory)
        return

    held_scope, session = opened.scope, opened.session
    try:
        yield EscrowMutation(job_id, session, scope_factory)
    except BaseException:
        await run_in_threadpool(_close, held_scope, session, commit=False)
        raise
    try:
        await run_in_threadpool(_close, held_scope, session, commit=True)
    except Exception as exc:  # noqa: BLE001 - settlement already happened; see below
        # By the time the block returns, the settlement transaction is submitted and
        # cannot be taken back, so a commit that fails here must not turn the caller's
        # success into an error (a retry would only re-find the settled release). The
        # row catches up through the settlement sweeper's backfill from the chain, the
        # same recovery a failed row write always had.
        logger.error("Escrow mutation commit failed for job_id=%s after settlement: %s", job_id, exc)
