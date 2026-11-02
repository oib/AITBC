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

Not on Postgres (sqlite, single process by construction): the lock is an
in-process ``asyncio.Lock`` per job. The sketch for this step used ``BEGIN
IMMEDIATE`` there; that takes sqlite's one database-wide writer lock and would hold
it across the settlement submit -- an HTTP round trip to the same node -- stalling the
block producer and every other writer, so it is deliberately not used.
"""

from __future__ import annotations

import asyncio
import os
import weakref
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractContextManager, asynccontextmanager
from typing import Any

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


def _open_locked_session(scope_factory: SessionScope, job_id: str, timeout_seconds: int) -> tuple[Any, Session] | None:
    """Open a session and take the advisory lock; None when the database is not Postgres."""
    scope = scope_factory()
    session = scope.__enter__()
    try:
        if session.get_bind().dialect.name != "postgresql":
            scope.__exit__(None, None, None)
            return None
        conn = session.connection()
        # SET LOCAL lasts for this transaction only, so the pooled connection comes
        # back with the server default.
        conn.execute(text(f"SET LOCAL lock_timeout = {int(timeout_seconds) * 1000}"))
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": LOCK_KEY_PREFIX + job_id})
        return scope, session
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

    if opened is None:
        lock = _process_locks.get(job_id)
        if lock is None:
            lock = _process_locks.setdefault(job_id, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), timeout)
        except TimeoutError as exc:
            raise EscrowBusy(job_id) from exc
        try:
            yield EscrowMutation(job_id, None, scope_factory)
        finally:
            lock.release()  # noqa: unawaited-async — asyncio.Lock.release() is synchronous
        return

    held_scope, session = opened
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
