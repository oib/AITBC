"""Durable operation ledger for replay-safe financial mutations.

Financial write paths must survive client retries, gateway re-sends, and
process crashes without double-applying. This module records one row per
``Idempotency-Key`` in a small SQLite table and gives handlers a
begin/complete/fail protocol:

- ``begin`` returns ``EXECUTE`` for a fresh key, ``REPLAY`` (with the stored
  response) when a completed operation is retried with the same request body,
  ``CONFLICT`` when a key is reused with a *different* body, ``IN_PROGRESS``
  while a live attempt holds the lease, and ``UNCERTAIN`` when a previous
  attempt's outcome is unknown and re-execution would be unsafe.
- ``complete`` stores the response alongside the row; ``fail`` marks the
  attempt retryable (``failed``) or terminal (``uncertain``).

Crash recovery is lease-based: a ``pending`` row whose lease expired means
the worker died mid-operation. Whether a retry may re-drive it depends on
the ``allow_adopt`` flag recorded at ``begin`` time — ``True`` only when
re-execution is provably safe (transactional rollback or a domain-level
dedup backstop). Non-adoptable rows flip to ``uncertain`` and require
manual resolution via the reconciler/ops tooling instead of risking a
double-apply.

All methods accept an optional ``conn`` so a service whose domain data lives
in the same SQLite file can record the operation and its side effects in a
single transaction — then there is no window at all between "did the write"
and "did we record it".
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .aitbc_logging import get_logger

logger = get_logger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operations (
    service TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    allow_adopt INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL CHECK (state IN ('pending', 'completed', 'failed', 'uncertain')),
    result_json TEXT,
    response_status INTEGER,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    lease_expires_at REAL NOT NULL,
    PRIMARY KEY (service, idempotency_key)
)
"""

DEFAULT_LEASE_SECONDS = 300.0
DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60.0


class BeginStatus(Enum):
    """What ``begin`` decided for this Idempotency-Key."""

    EXECUTE = "execute"
    REPLAY = "replay"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class Operation:
    """A recorded operation row."""

    idempotency_key: str
    operation_type: str
    request_hash: str
    state: str
    attempt: int
    result: Any
    response_status: int | None
    error: str | None
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class BeginResult:
    """Outcome of ``OperationLedger.begin``.

    ``attempt`` is the lease holder's attempt number; pass it back to
    ``complete``/``fail`` so a preempted attempt cannot overwrite a newer
    one. ``result``/``response_status`` are populated for ``REPLAY``.
    """

    status: BeginStatus
    attempt: int = 0
    result: Any = None
    response_status: int | None = None


def request_hash(payload: Any) -> str:
    """Canonical hash of the request body an Idempotency-Key is bound to.

    Replays must present the same payload; a key reused with a different
    body is a CONFLICT, not a second execution.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OperationLedger:
    """SQLite-backed per-service operation ledger.

    ``db_path`` may point at a dedicated ``operations.db`` file or at the
    service's own database so ledger writes can join the domain transaction
    via the ``conn`` argument.
    """

    def __init__(
        self,
        db_path: str | Path,
        service: str,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        timeout: float = 30.0,
    ) -> None:
        self._path = str(db_path)
        self._service = service
        self._lease_seconds = lease_seconds
        self._timeout = timeout
        self._schema_ready = False
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._ensure_schema()
        except sqlite3.OperationalError:
            # A caller may already hold this file's write lock (shared-file
            # mode): schema creation is deferred — ``begin``/``complete`` run
            # the idempotent CREATE inside the caller's transaction instead.
            pass

    @property
    def db_path(self) -> str:
        """Filesystem path of the ledger database (readiness checks read this)."""
        return self._path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=self._timeout)

    def _ensure_schema(self) -> None:
        with self._own_conn() as conn:
            self._ensure_schema_on(conn)
        self._schema_ready = True

    @staticmethod
    def _ensure_schema_on(conn: sqlite3.Connection) -> None:
        # conn.execute (not executescript) issues the CREATE without
        # committing first, so it is safe inside a caller's transaction.
        conn.execute(SCHEMA_SQL)

    def _own_conn(self) -> sqlite3.Connection:
        conn = self._connect()
        if not self._schema_ready:
            self._ensure_schema_on(conn)
            self._schema_ready = True
        return conn

    # ------------------------------------------------------------------
    # begin / complete / fail
    # ------------------------------------------------------------------

    def begin(
        self,
        key: str,
        operation_type: str,
        req_hash: str,
        *,
        allow_adopt: bool = True,
        lease_seconds: float | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> BeginResult:
        """Claim or dedupe an operation by Idempotency-Key.

        With ``conn`` the check runs inside the caller's transaction (the
        caller must already hold a write lock, e.g. BEGIN IMMEDIATE) so the
        ledger row commits atomically with the domain write. Without it the
        ledger opens its own BEGIN IMMEDIATE transaction.
        """
        now = time.time()
        lease = now + (lease_seconds if lease_seconds is not None else self._lease_seconds)
        if conn is None:
            own = True
            conn = self._own_conn()
            conn.execute("BEGIN IMMEDIATE")
        else:
            own = False
            self._ensure_schema_on(conn)
            self._schema_ready = True
        try:
            row = conn.execute(
                """
                SELECT state, request_hash, allow_adopt, attempt, lease_expires_at, result_json, response_status
                FROM operations WHERE service = ? AND idempotency_key = ?
                """,
                (self._service, key),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO operations
                        (service, idempotency_key, operation_type, request_hash, allow_adopt,
                         state, attempt, created_at, updated_at, lease_expires_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?)
                    """,
                    (self._service, key, operation_type, req_hash, int(allow_adopt), now, now, lease),
                )
                self._commit_own(own, conn)
                return BeginResult(BeginStatus.EXECUTE, attempt=1)

            result = self._begin_existing(row, key, req_hash, now, lease, conn)
            self._commit_own(own, conn)
            return result
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    @staticmethod
    def _commit_own(own: bool, conn: sqlite3.Connection) -> None:
        if own:
            conn.commit()

    def _begin_existing(
        self,
        row: tuple,
        key: str,
        req_hash: str,
        now: float,
        lease: float,
        conn: sqlite3.Connection,
    ) -> BeginResult:
        """Decide the outcome for an existing operation row.

        Writes stay inside the caller's transaction — ``begin`` commits after
        this returns, so every outcome here is just a verdict plus the row
        mutations it needs.
        """
        state, stored_hash, stored_adopt, attempt, lease_expires, result_json, resp_status = row
        if stored_hash != req_hash and state in ("completed", "failed"):
            return BeginResult(BeginStatus.CONFLICT)

        if state == "completed":
            result = json.loads(result_json) if result_json is not None else None
            return BeginResult(BeginStatus.REPLAY, attempt=attempt, result=result, response_status=resp_status)

        if state == "uncertain":
            return BeginResult(BeginStatus.UNCERTAIN)

        if state == "pending":
            return self._begin_pending(key, attempt, stored_adopt, lease_expires, now, lease, conn)

        # state == 'failed' — a retryable failure; re-drive under a new lease.
        new_attempt = attempt + 1
        conn.execute(
            "UPDATE operations SET state='pending', attempt=?, updated_at=?, lease_expires_at=? "
            "WHERE service=? AND idempotency_key=? AND state='failed'",
            (new_attempt, now, lease, self._service, key),
        )
        return BeginResult(BeginStatus.EXECUTE, attempt=new_attempt)

    def _begin_pending(
        self,
        key: str,
        attempt: int,
        stored_adopt: int,
        lease_expires: float,
        now: float,
        lease: float,
        conn: sqlite3.Connection,
    ) -> BeginResult:
        if now < lease_expires:
            return BeginResult(BeginStatus.IN_PROGRESS)
        if not stored_adopt:
            conn.execute(
                "UPDATE operations SET state='uncertain', error=?, updated_at=? "
                "WHERE service=? AND idempotency_key=? AND state='pending'",
                ("lease expired; outcome unknown — not safe to auto-retry", now, self._service, key),
            )
            return BeginResult(BeginStatus.UNCERTAIN)
        # Adopt the expired lease: the previous attempt died before
        # completing, and the caller declared re-execution safe.
        new_attempt = attempt + 1
        conn.execute(
            "UPDATE operations SET attempt=?, updated_at=?, lease_expires_at=? "
            "WHERE service=? AND idempotency_key=? AND state='pending'",
            (new_attempt, now, lease, self._service, key),
        )
        logger.info("Adopted expired operation lease: key=%s attempt=%d", key, new_attempt)
        return BeginResult(BeginStatus.EXECUTE, attempt=new_attempt)

    def complete(
        self,
        key: str,
        attempt: int,
        result: Any,
        *,
        response_status: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Record the operation's response for future replays.

        Returns False if the row is no longer this attempt's pending lease
        (preempted by adoption or reconciliation) — the caller's transaction
        should then be treated as superseded.
        """
        now = time.time()
        payload = json.dumps(result, default=str) if result is not None else None
        if conn is None:
            own = True
            conn = self._own_conn()
        else:
            own = False
            self._ensure_schema_on(conn)
        try:
            cur = conn.execute(
                """
                UPDATE operations SET state='completed', result_json=?, response_status=?, updated_at=?
                WHERE service=? AND idempotency_key=? AND state='pending' AND attempt=?
                """,
                (payload, response_status, now, self._service, key, attempt),
            )
            landed = cur.rowcount == 1
            if own:
                conn.commit()
            if not landed:
                logger.warning("complete() did not land: key=%s attempt=%d no longer holds the lease", key, attempt)
            return landed
        finally:
            if own:
                conn.close()

    def fail(
        self,
        key: str,
        attempt: int,
        error: str,
        *,
        terminal: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Mark the attempt failed.

        ``terminal=True`` records ``uncertain`` — for operations whose side
        effects cannot be proven not to have happened (e.g. a broadcast that
        may have landed). Uncertain rows never auto-retry; an operator
        resolves them via ``resolve``.
        """
        now = time.time()
        state = "uncertain" if terminal else "failed"
        if conn is None:
            own = True
            conn = self._own_conn()
        else:
            own = False
            self._ensure_schema_on(conn)
        try:
            cur = conn.execute(
                """
                UPDATE operations SET state=?, error=?, updated_at=?
                WHERE service=? AND idempotency_key=? AND state='pending' AND attempt=?
                """,
                (state, error[:2000], now, self._service, key, attempt),
            )
            landed = cur.rowcount == 1
            if own:
                conn.commit()
            if not landed:
                logger.warning("fail() did not land: key=%s attempt=%d no longer holds the lease", key, attempt)
            return landed
        finally:
            if own:
                conn.close()

    # ------------------------------------------------------------------
    # inspection / reconciliation
    # ------------------------------------------------------------------

    def get(self, key: str) -> Operation | None:
        with self._own_conn() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, operation_type, request_hash, state, attempt,
                       result_json, response_status, error, created_at, updated_at
                FROM operations WHERE service=? AND idempotency_key=?
                """,
                (self._service, key),
            ).fetchone()
        return self._to_operation(row) if row else None

    def list_uncertain(self, limit: int = 500) -> list[Operation]:
        with self._own_conn() as conn:
            rows = conn.execute(
                """
                SELECT idempotency_key, operation_type, request_hash, state, attempt,
                       result_json, response_status, error, created_at, updated_at
                FROM operations WHERE service=? AND state='uncertain' ORDER BY updated_at LIMIT ?
                """,
                (self._service, limit),
            ).fetchall()
        return [self._to_operation(r) for r in rows]

    def resolve(self, key: str) -> bool:
        """Clear an ``uncertain`` operation back to ``failed`` (retryable).

        Operators call this after establishing via domain state (order book,
        chain history, wallet ledger) that the attempt's side effect did not
        land — or that the client should simply retry.
        """
        with self._own_conn() as conn:
            cur = conn.execute(
                "UPDATE operations SET state='failed', error=?, updated_at=? "
                "WHERE service=? AND idempotency_key=? AND state='uncertain'",
                ("resolved manually", time.time(), self._service, key),
            )
            return cur.rowcount == 1

    def reconcile(self, limit: int = 1000) -> dict[str, int]:
        """Expire stale ``pending`` rows.

        Adoptable rows become ``failed`` (safe to retry); non-adoptable rows
        become ``uncertain`` (operator attention). Returns per-transition
        counts for monitoring.
        """
        now = time.time()
        with self._own_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            adoptable = conn.execute(
                "UPDATE operations SET state='failed', error=?, updated_at=? "
                "WHERE service=? AND state='pending' AND lease_expires_at<? AND allow_adopt=1",
                ("lease expired; attempt abandoned", now, self._service, now),
            ).rowcount
            non_adoptable = conn.execute(
                "UPDATE operations SET state='uncertain', error=?, updated_at=? "
                "WHERE service=? AND state='pending' AND lease_expires_at<? AND allow_adopt=0",
                ("lease expired; outcome unknown — not safe to auto-retry", now, self._service, now),
            ).rowcount
            conn.commit()
        report = {"expired_to_failed": adoptable, "expired_to_uncertain": non_adoptable}
        if adoptable or non_adoptable:
            logger.info("Operation reconcile: %s", report)
        return report

    def purge(self, retention_seconds: float = DEFAULT_RETENTION_SECONDS) -> int:
        """Delete terminal rows older than the retention window.

        ``uncertain`` rows are never purged — they need an operator decision.
        """
        cutoff = time.time() - retention_seconds
        with self._own_conn() as conn:
            cur = conn.execute(
                "DELETE FROM operations WHERE service=? AND state IN ('completed','failed') AND updated_at<?",
                (self._service, cutoff),
            )
            conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------
    # async wrappers — the ledger ops are single-row SQLite writes; running
    # them on a thread keeps async handlers unblocked without an aiosqlite dep.
    # ------------------------------------------------------------------

    async def begin_async(self, *args: Any, **kwargs: Any) -> BeginResult:
        return await asyncio.to_thread(self.begin, *args, **kwargs)

    async def complete_async(self, *args: Any, **kwargs: Any) -> bool:
        return await asyncio.to_thread(self.complete, *args, **kwargs)

    async def fail_async(self, *args: Any, **kwargs: Any) -> bool:
        return await asyncio.to_thread(self.fail, *args, **kwargs)

    async def reconcile_async(self, *args: Any, **kwargs: Any) -> dict[str, int]:
        return await asyncio.to_thread(self.reconcile, *args, **kwargs)

    @staticmethod
    def _to_operation(row: tuple) -> Operation:
        key, op_type, req_hash, state, attempt, result_json, resp_status, error, created, updated = row
        return Operation(
            idempotency_key=key,
            operation_type=op_type,
            request_hash=req_hash,
            state=state,
            attempt=attempt,
            result=json.loads(result_json) if result_json is not None else None,
            response_status=resp_status,
            error=error,
            created_at=created,
            updated_at=updated,
        )
