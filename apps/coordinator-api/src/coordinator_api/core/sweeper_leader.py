"""One sweeper runner per host (COORD-SWEEPERS-PER-WORKER-1, #769).

uvicorn runs the coordinator with ``--workers N`` and every worker runs the
app lifespan, so without a guard each worker starts all of the periodic
sweepers, and with the fixed stagger each twin pair fires in the same second
(double release/refund calls, a bond-slash nonce counter per process). The
worker that takes this host-wide lock starts the sweepers; the others stand
by and retry, so a dead leader's sweepers come back in another worker.

The lock is a plain ``fcntl.flock`` on a file that is opened once and kept
open for the life of the process. The kernel drops it when the process exits
or is killed, so a dead leader frees it with no cleanup, nothing ever
releases it, and the file is never unlinked (with a plain flock, an unlink
while another worker holds a descriptor to the old inode could let a second
leader lock a new file).

Fail-open: when the lock file cannot be opened or locked for any reason other
than another holder (no ``/var/lib/aitbc`` on a dev machine, a filesystem
without flock), the process sweeps unguarded with one warning, which is the
pre-lock behaviour. A lock held by another worker is never fail-open.
"""

from __future__ import annotations

import fcntl
import os

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

DEFAULT_LOCK_PATH = "/var/lib/aitbc/coordinator-sweepers.lock"
DEFAULT_STANDBY_RETRY_SECONDS = 30.0

ROLE_PENDING = "pending"  # not decided yet (before startup, or in tests)
ROLE_LEADER = "leader"  # holds the lock and runs the sweepers
ROLE_STANDBY = "standby"  # another worker holds the lock
ROLE_UNGUARDED = "unguarded"  # lock unusable: runs the sweepers without it
ROLE_DISABLED = "disabled"  # COORDINATOR_SWEEPER_LEADER_ENABLED=false


def leader_enabled() -> bool:
    """COORDINATOR_SWEEPER_LEADER_ENABLED, default on; false restores every-worker sweepers."""
    raw = os.environ.get("COORDINATOR_SWEEPER_LEADER_ENABLED", "true")
    return raw.strip().lower() not in ("0", "false", "no", "off")


def lock_path() -> str:
    return os.environ.get("COORDINATOR_SWEEPER_LEADER_LOCK_PATH") or DEFAULT_LOCK_PATH


def standby_retry_seconds() -> float:
    """How often a standby worker retries the lock (COORDINATOR_SWEEPER_STANDBY_RETRY_SECONDS)."""
    try:
        value = float(os.environ.get("COORDINATOR_SWEEPER_STANDBY_RETRY_SECONDS", DEFAULT_STANDBY_RETRY_SECONDS))
    except ValueError:
        return DEFAULT_STANDBY_RETRY_SECONDS
    return max(0.1, value)


class SweeperLeaderLock:
    """Decides whether this process runs the sweepers."""

    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self.role = ROLE_PENDING
        self._fd: int | None = None

    @property
    def runs_sweepers(self) -> bool:
        return self.role in (ROLE_LEADER, ROLE_UNGUARDED, ROLE_DISABLED)

    def try_lead(self) -> bool:
        """Take the lock without blocking. True means this process runs the sweepers."""
        if self.runs_sweepers:
            return True
        if not self.enabled:
            self.role = ROLE_DISABLED
            return True
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            return self._unguarded(exc)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            self.role = ROLE_STANDBY
            return False
        except OSError as exc:
            os.close(fd)
            return self._unguarded(exc)
        self._fd = fd
        self.role = ROLE_LEADER
        try:
            os.ftruncate(fd, 0)
            os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)
        except OSError:
            pass  # the pid is only a hint for standby logs and the admin report
        return True

    def _unguarded(self, exc: OSError) -> bool:
        logger.warning("Sweeper leader lock %s unusable (%s); this worker runs the sweepers unguarded", self.path, exc)
        self.role = ROLE_UNGUARDED
        return True

    def leader_pid(self) -> int | None:
        """The pid the current leader wrote into the lock file, if readable."""
        try:
            with open(self.path, encoding="ascii") as fh:
                return int(fh.read().strip() or 0) or None
        except (OSError, ValueError):
            return None

    def abandon(self) -> None:
        """Drop the lock as process exit would. Production never calls this; tests do."""
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.role = ROLE_PENDING


_leader_lock: SweeperLeaderLock | None = None


def get_leader_lock() -> SweeperLeaderLock:
    """The process-wide leader lock, configured from the environment on first use."""
    global _leader_lock
    if _leader_lock is None:
        _leader_lock = SweeperLeaderLock(lock_path(), enabled=leader_enabled())
    return _leader_lock
