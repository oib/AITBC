"""Cross-worker sweeper leadership election (#832).

``aitbc-blockchain-rpc`` runs ``--workers N`` (N=2 fleet-wide since #827),
and both the mempool staleness sweeper and the settlement-mark sweeper are
started inside the app lifespan — so without an election every worker runs
its own copy of each. The settlement-mark sweeper writes escrow rows, the
mempool sweeper only double-counts eviction metrics, and the fee-sweep pass
(when armed) would submit twice per tick, so the double-run is worth
removing even though none of it moves funds.

One worker per host leads: a non-blocking ``fcntl.flock`` on
``sweeper-leader.lock`` inside the ``escrow-locks/`` dir beside chain.db —
the same directory and mechanism ``escrow_txn`` uses for mutation stripes.
The fd is held for the process lifetime; the kernel drops the lock if the
holding worker dies, and uvicorn's respawn guarantees a fresh worker runs
its lifespan and re-acquires, so no retry loop in the survivor is needed.

One lock gates BOTH sweepers: the election stays atomic — there is no
split-brain where worker A sweeps the mempool and worker B sweeps
settlement marks.

Failure policy (operator-flagged deviation from #827's fail-closed): if the
lock file cannot be opened or the flock syscall errors (not contended —
contention is the normal BlockingIOError path), the caller LEADS anyway and
logs an error. A silently dead sweeper loses the demote function entirely;
a double sweep is the low-severity status quo this module exists to fix.
An unpathable (in-memory) database has nothing to lock beside — the caller
leads, keeping tests and dev mode unchanged.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from ..contracts.escrow_txn import LOCK_DIR_NAME
from ..database import get_engine
from ..logger import get_logger

_logger = get_logger(__name__)

LOCK_FILE_NAME = "sweeper-leader.lock"

#: Returned when leadership is ungated (no file to lock beside, or the lock
#: path failed open). Distinct from a real fd so callers can skip os.close.
UNLOCKED = -1


def _sqlite_path() -> str | None:
    """The chain.db file the sweepers sweep, or None for an in-memory db."""
    try:
        database = get_engine().url.database
    except Exception:  # noqa: BLE001 - engine resolution failure must not decide leadership
        return None
    return database if database and database != ":memory:" else None


def try_acquire_sweeper_leadership(sqlite_path: str | None = None) -> int | None:
    """Take the per-host sweeper leader lock.

    Returns an fd (or the ``UNLOCKED`` sentinel when there was nothing real
    to lock) when this process leads — the caller keeps it referenced for
    the process lifetime and may ``release_sweeper_leadership`` it at
    shutdown. Returns ``None`` when another worker already leads.
    """
    if sqlite_path is None:
        sqlite_path = _sqlite_path()
    if sqlite_path is None or sqlite_path == ":memory:":
        return UNLOCKED
    path = Path(sqlite_path).parent / LOCK_DIR_NAME / LOCK_FILE_NAME
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    except OSError as exc:
        _logger.error("Sweeper leader lock file %s unavailable (%s) — leading ungated", path, exc)
        return UNLOCKED
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None  # another worker holds the lock
    except OSError as exc:
        os.close(fd)
        _logger.error("Sweeper leader flock on %s failed (%s) — leading ungated", path, exc)
        return UNLOCKED
    return fd


def release_sweeper_leadership(fd: int | None) -> None:
    """Drop leadership (app shutdown). None/UNLOCKED need no close."""
    if fd is not None and fd >= 0:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
