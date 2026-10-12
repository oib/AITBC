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
            spent = conn.execute(
                "SELECT COALESCE(SUM(amount_units),0) FROM spends WHERE ts > ?",
                (now - WINDOW_SECONDS,),
            ).fetchone()[0]
            if int(spent) + amount_units > max_per_day:
                conn.execute("ROLLBACK")
                return None
            cur = conn.execute(
                "INSERT INTO spends(ts,amount_units,memo,to_addr) VALUES (?,?,?,?)",
                (now, amount_units, memo, to_addr),
            )
            conn.execute("COMMIT")
            return int(cur.lastrowid or 0)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    def record_tx_hash(self, row_id: int, tx_hash: str) -> None:
        self._connect().execute("UPDATE spends SET tx_hash=? WHERE id=?", (tx_hash, row_id))

    def release(self, row_id: int) -> None:
        """Remove an admitted-but-never-sent row so a failed send does not burn headroom."""
        self._connect().execute("DELETE FROM spends WHERE id=?", (row_id,))
