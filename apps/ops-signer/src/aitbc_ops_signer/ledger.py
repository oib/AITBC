"""Rolling 24h spend counter in sqlite.

The day cap is the only stateful policy bound and it must be atomic:
two concurrent requests must not both read headroom and both pass.
BEGIN IMMEDIATE takes the write lock before the sum is read, so the
check-and-admit is a single critical section on the db file.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

WINDOW_SECONDS = 86_400
# Rows are kept well past the cap window so the (memo, to, amount) dedupe
# can still recognize a retry of an ambiguous send, and so an operator can
# reconcile a hashless row. Without pruning the table — and the per-request
# SUM scan — grows forever (#2827).
RETENTION_SECONDS = 7 * WINDOW_SECONDS


class DailyLedger:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS spends ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts REAL NOT NULL, "
                "amount_units INTEGER NOT NULL, "
                "memo TEXT NOT NULL, "
                "to_addr TEXT NOT NULL, "
                "tx_hash TEXT)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            # isolation_level=None -> autocommit: every statement commits unless
            # inside an explicit BEGIN, so record_tx_hash/release cannot leave an
            # open write transaction holding the lock (that deadlocked admit).
            conn = sqlite3.connect(self._path, timeout=10, isolation_level=None)
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        return conn

    @staticmethod
    def _begin_immediate(conn: sqlite3.Connection) -> None:
        """BEGIN IMMEDIATE can return SQLITE_BUSY at once on a deferred-to-
        immediate upgrade (the busy timeout does not cover that case), so
        retry the lock acquisition briefly."""
        for _ in range(200):  # ~10 s worst case
            try:
                conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as e:
                if "locked" not in str(e):
                    raise
                time.sleep(0.05)
        raise TimeoutError("ledger lock unavailable")

    def spent_last_24h(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        row = (
            self._connect()
            .execute(
                "SELECT COALESCE(SUM(amount_units),0) FROM spends WHERE ts > ?",
                (now - WINDOW_SECONDS,),
            )
            .fetchone()
        )
        return int(row[0])

    @staticmethod
    def _admit_core(
        conn: sqlite3.Connection,
        amount_units: int,
        *,
        memo: str,
        to_addr: str,
        max_per_day: int,
        now: float,
        dedupe: bool,
    ) -> tuple[str, int | None, str | None]:
        """Prune, optionally dedupe, cap-check and insert — inside the
        caller's open IMMEDIATE transaction. Returns
        ``(kind, row_id, tx_hash)``: ``admitted`` / ``replay`` /
        ``in_flight`` / ``over_cap``."""
        conn.execute("DELETE FROM spends WHERE ts < ?", (now - RETENTION_SECONDS,))
        if dedupe:
            # An identical (memo, to, amount) request inside the window is
            # a retry of the same payment, not a new one: replay the
            # recorded hash, or refuse while the earlier send's outcome is
            # still unknown — a blind resubmit is how ambiguous sends
            # double-pay (#2827).
            row = conn.execute(
                "SELECT id, tx_hash FROM spends WHERE memo = ? AND to_addr = ? AND amount_units = ? AND ts > ?"
                " ORDER BY id DESC LIMIT 1",
                (memo, to_addr, amount_units, now - WINDOW_SECONDS),
            ).fetchone()
            if row is not None:
                return ("replay" if row[1] else "in_flight", int(row[0]), row[1])
        spent = conn.execute(
            "SELECT COALESCE(SUM(amount_units),0) FROM spends WHERE ts > ?",
            (now - WINDOW_SECONDS,),
        ).fetchone()[0]
        if int(spent) + amount_units > max_per_day:
            return ("over_cap", None, None)
        cur = conn.execute(
            "INSERT INTO spends(ts,amount_units,memo,to_addr) VALUES (?,?,?,?)",
            (now, amount_units, memo, to_addr),
        )
        return ("admitted", int(cur.lastrowid or 0), None)

    def admit(self, amount_units: int, *, memo: str, to_addr: str, max_per_day: int) -> int | None:
        """Record a spend iff the rolling-day total stays within the cap.

        Returns the new row id, or None when the cap would be exceeded.
        BEGIN IMMEDIATE serializes concurrent callers: the second sees the
        first's already-committed sum.
        """
        conn = self._connect()
        now = time.time()
        try:
            self._begin_immediate(conn)
            kind, row_id, _ = self._admit_core(
                conn, amount_units, memo=memo, to_addr=to_addr, max_per_day=max_per_day, now=now, dedupe=False
            )
            if kind == "over_cap":
                conn.execute("ROLLBACK")
                return None
            conn.execute("COMMIT")
            return row_id
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    def admit_or_find(
        self, amount_units: int, *, memo: str, to_addr: str, max_per_day: int
    ) -> tuple[str, int | None, str | None]:
        """Atomic admit-or-dedupe for the sign path (#2827).

        Returns ``(kind, row_id, tx_hash)`` — ``admitted`` (new spend row,
        proceed to sign), ``replay`` (identical payment already sent;
        ``tx_hash`` is its recorded hash), ``in_flight`` (identical
        payment admitted but its send outcome is still unknown — do NOT
        resubmit), or ``over_cap``.
        """
        conn = self._connect()
        now = time.time()
        try:
            self._begin_immediate(conn)
            kind, row_id, tx_hash = self._admit_core(
                conn, amount_units, memo=memo, to_addr=to_addr, max_per_day=max_per_day, now=now, dedupe=True
            )
            conn.execute("COMMIT")
            return kind, row_id, tx_hash
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    def record_tx_hash(self, row_id: int, tx_hash: str) -> None:
        self._connect().execute("UPDATE spends SET tx_hash=? WHERE id=?", (tx_hash, row_id))

    def release(self, row_id: int) -> None:
        """Remove an admitted-but-never-sent row so a failed send does not burn headroom."""
        self._connect().execute("DELETE FROM spends WHERE id=?", (row_id,))
