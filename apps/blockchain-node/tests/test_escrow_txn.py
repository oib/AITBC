"""#780 step c: one escrow's release/refund is serialised by ``escrow_mutation``.

The sqlite path (in-process lock) and the Postgres path (transaction-scoped
advisory lock) are both driven here. The Postgres statements are checked against a
recording session, and the actual two-connection exclusion runs against a real
server when one is reachable (``requires_postgres``, skipped otherwise, same
convention as ``test_mempool_column_types``).
"""

import asyncio
import gc
import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from aitbc_chain.contracts import escrow_txn
from aitbc_chain.contracts.escrow_txn import EscrowBusy, escrow_mutation
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlmodel import Session, SQLModel


@pytest.fixture
def sqlite_scope():
    """A session factory over one in-memory sqlite database with a probe table."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE probe (job_id TEXT PRIMARY KEY, n INTEGER)"))

    @contextmanager
    def _scope():
        with Session(engine) as session:
            yield session

    return _scope, engine


# ---- sqlite / non-Postgres: in-process lock ----------------------------------------


@pytest.mark.asyncio
async def test_same_job_is_exclusive_in_process(sqlite_scope):
    scope, _ = sqlite_scope
    order: list[str] = []
    holding = asyncio.Event()
    let_go = asyncio.Event()

    async def first():
        async with escrow_mutation("job-1", scope):
            order.append("first-in")
            holding.set()
            await let_go.wait()
            order.append("first-out")

    async def second():
        await holding.wait()
        async with escrow_mutation("job-1", scope):
            order.append("second-in")

    t1 = asyncio.create_task(first())
    t2 = asyncio.create_task(second())
    await holding.wait()
    await asyncio.sleep(0.05)
    assert order == ["first-in"], "second caller must wait while the first holds the lock"
    let_go.set()
    await asyncio.gather(t1, t2)
    assert order == ["first-in", "first-out", "second-in"]


@pytest.mark.asyncio
async def test_different_jobs_do_not_block_each_other(sqlite_scope):
    scope, _ = sqlite_scope
    async with escrow_mutation("job-a", scope):
        # Would hang (and time out) if the lock were shared across jobs.
        async with asyncio.timeout(1):
            async with escrow_mutation("job-b", scope):
                pass


@pytest.mark.asyncio
async def test_lock_wait_past_the_timeout_raises_busy(sqlite_scope, monkeypatch):
    scope, _ = sqlite_scope
    monkeypatch.setattr(escrow_txn, "lock_timeout_seconds", lambda: 0.05)
    async with escrow_mutation("job-1", scope):
        with pytest.raises(EscrowBusy):
            async with escrow_mutation("job-1", scope):
                pytest.fail("the busy caller must never run its body")
    # The holder's exit released it: the next caller gets in.
    async with escrow_mutation("job-1", scope):
        pass


@pytest.mark.asyncio
async def test_handler_exception_releases_the_lock(sqlite_scope):
    scope, _ = sqlite_scope
    with pytest.raises(RuntimeError, match="boom"):
        async with escrow_mutation("job-1", scope):
            raise RuntimeError("boom")
    async with asyncio.timeout(1):
        async with escrow_mutation("job-1", scope):
            pass


@pytest.mark.asyncio
async def test_lock_map_does_not_retain_finished_jobs(sqlite_scope):
    scope, _ = sqlite_scope
    for n in range(20):
        async with escrow_mutation(f"job-{n}", scope):
            pass
    gc.collect()
    assert len(escrow_txn._process_locks) == 0


@pytest.mark.asyncio
async def test_write_runs_in_its_own_committed_session_without_postgres(sqlite_scope):
    scope, engine = sqlite_scope

    def _insert(session):
        session.execute(text("INSERT INTO probe (job_id, n) VALUES ('job-1', 7)"))

    async with escrow_mutation("job-1", scope) as txn:
        assert txn.session is None
        await txn.write(_insert)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT n FROM probe WHERE job_id = 'job-1'")).scalar_one() == 7


def test_lock_timeout_seconds_env(monkeypatch):
    monkeypatch.delenv(escrow_txn.LOCK_TIMEOUT_ENV, raising=False)
    assert escrow_txn.lock_timeout_seconds() == escrow_txn.DEFAULT_LOCK_TIMEOUT_SECONDS
    monkeypatch.setenv(escrow_txn.LOCK_TIMEOUT_ENV, "5")
    assert escrow_txn.lock_timeout_seconds() == 5
    for junk in ("", "abc", "0", "-3"):
        monkeypatch.setenv(escrow_txn.LOCK_TIMEOUT_ENV, junk)
        assert escrow_txn.lock_timeout_seconds() == escrow_txn.DEFAULT_LOCK_TIMEOUT_SECONDS


# ---- Postgres: statements on a recording session -----------------------------------


class _FakePgSession:
    """Looks like a Postgres Session to escrow_mutation and records what happens to it."""

    def __init__(self, execute_error: Exception | None = None, commit_error: Exception | None = None):
        self.events: list = []
        self._execute_error = execute_error
        self._commit_error = commit_error
        self.conn = MagicMock()
        self.conn.execute.side_effect = self._execute

    def _execute(self, stmt, params=None):
        self.events.append(("execute", str(stmt), params))
        if self._execute_error is not None:
            raise self._execute_error

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def connection(self):
        return self.conn

    def flush(self):
        self.events.append(("flush",))

    def commit(self):
        self.events.append(("commit",))
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self):
        self.events.append(("rollback",))


def _fake_scope(session):
    exits: list = []

    class _Scope:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            exits.append(exc)

    return (lambda: _Scope()), exits


def _lock_error(pgcode: str) -> DBAPIError:
    orig = SimpleNamespace(pgcode=pgcode)
    return OperationalError("SELECT pg_advisory_xact_lock", {}, orig)


@pytest.mark.asyncio
async def test_postgres_takes_a_transaction_scoped_advisory_lock_on_the_job_key():
    session = _FakePgSession()
    scope, exits = _fake_scope(session)

    async with escrow_mutation("job-9", scope):
        pass

    stmts = [e for e in session.events if e[0] == "execute"]
    assert "SET LOCAL lock_timeout" in stmts[0][1]
    assert "pg_advisory_xact_lock(hashtext(:key))" in stmts[1][1]
    assert stmts[1][2] == {"key": "escrow_release:job-9"}
    assert ("commit",) in session.events and ("rollback",) not in session.events
    assert len(exits) == 1


@pytest.mark.asyncio
async def test_postgres_write_goes_through_the_lock_holding_session():
    session = _FakePgSession()
    scope, _ = _fake_scope(session)
    seen = []

    async with escrow_mutation("job-9", scope) as txn:
        assert txn.session is session
        await txn.write(lambda s: seen.append(s))
        # Written and flushed, but not committed until the lock is let go.
        assert ("commit",) not in session.events

    assert seen == [session]
    assert session.events.index(("flush",)) < session.events.index(("commit",))


@pytest.mark.asyncio
async def test_postgres_handler_exception_rolls_back_and_reraises():
    session = _FakePgSession()
    scope, exits = _fake_scope(session)

    with pytest.raises(ValueError, match="nope"):
        async with escrow_mutation("job-9", scope):
            raise ValueError("nope")

    assert ("rollback",) in session.events
    assert ("commit",) not in session.events
    assert len(exits) == 1


@pytest.mark.asyncio
async def test_postgres_lock_timeout_maps_to_busy_and_closes_the_session():
    session = _FakePgSession(execute_error=_lock_error("55P03"))
    scope, exits = _fake_scope(session)

    with pytest.raises(EscrowBusy):
        async with escrow_mutation("job-9", scope):
            pytest.fail("body must not run without the lock")

    assert len(exits) == 1


@pytest.mark.asyncio
async def test_postgres_other_database_errors_are_not_called_busy():
    session = _FakePgSession(execute_error=_lock_error("08006"))
    scope, exits = _fake_scope(session)

    with pytest.raises(DBAPIError):
        async with escrow_mutation("job-9", scope):
            pytest.fail("body must not run without the lock")

    assert len(exits) == 1


@pytest.mark.asyncio
async def test_postgres_commit_failure_after_the_body_is_logged_not_raised(caplog):
    """Settlement already went out; a failing commit must not turn it into an error."""
    session = _FakePgSession(commit_error=RuntimeError("connection lost"))
    scope, exits = _fake_scope(session)

    async with escrow_mutation("job-9", scope):
        pass

    assert len(exits) == 1
    assert any("commit failed" in r.getMessage() for r in caplog.records)


# ---- Postgres: real two-connection exclusion ---------------------------------------


def _pg_url() -> str:
    return os.environ.get("MEMPOOL_DB_URL") or os.environ.get("DATABASE_URL") or "postgresql://localhost:5432/aitbc"


@pytest.fixture
def pg_scope():
    engine = create_engine(_pg_url())

    @contextmanager
    def _scope():
        with Session(engine) as session:
            yield session

    yield _scope
    engine.dispose()


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_real_postgres_second_caller_waits_then_sees_the_first_commit(pg_scope, monkeypatch):
    monkeypatch.setenv(escrow_txn.LOCK_TIMEOUT_ENV, "1")
    job = f"job-lock-test-{os.getpid()}"
    started = asyncio.Event()
    let_go = asyncio.Event()

    async def holder():
        async with escrow_mutation(job, pg_scope):
            started.set()
            await let_go.wait()

    task = asyncio.create_task(holder())
    await started.wait()
    # Another connection asking for the same job's lock gives up after the timeout...
    with pytest.raises(EscrowBusy):
        async with escrow_mutation(job, pg_scope):
            pytest.fail("must not enter while the first connection holds the lock")
    # ...a different job is unaffected...
    async with escrow_mutation(job + "-other", pg_scope):
        pass
    # ...and the lock is free again as soon as the holder commits.
    let_go.set()
    await task
    async with escrow_mutation(job, pg_scope):
        pass
