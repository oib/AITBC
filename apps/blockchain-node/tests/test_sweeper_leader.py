"""#832: one sweeper leader per host under --workers N.

The mempool and settlement-mark sweepers start inside the app lifespan, so every
uvicorn worker would run its own pair. ``try_acquire_sweeper_leadership`` gates
them on a process-lifetime ``flock`` beside chain.db: one worker leads, the rest
skip. These tests contest the lock the way two workers do — two opens of the
same file flock-exclude each other even inside one process.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from aitbc_chain.rpc.sweeper_leader import (
    LOCK_FILE_NAME,
    UNLOCKED,
    release_sweeper_leadership,
    try_acquire_sweeper_leadership,
)
from aitbc_chain.contracts.escrow_txn import LOCK_DIR_NAME


@pytest.fixture()
def db_dir(tmp_path: Path) -> Path:
    (tmp_path / "chain.db").touch()
    return tmp_path


def test_second_contender_is_excluded(db_dir: Path):
    first = try_acquire_sweeper_leadership(str(db_dir / "chain.db"))
    assert first is not None and first >= 0
    assert try_acquire_sweeper_leadership(str(db_dir / "chain.db")) is None
    release_sweeper_leadership(first)


def test_leadership_is_reacquired_after_release(db_dir: Path):
    first = try_acquire_sweeper_leadership(str(db_dir / "chain.db"))
    assert first is not None and first >= 0
    release_sweeper_leadership(first)
    second = try_acquire_sweeper_leadership(str(db_dir / "chain.db"))
    assert second is not None and second >= 0
    release_sweeper_leadership(second)


def test_lock_lands_beside_chain_db_in_escrow_locks(db_dir: Path):
    fd = try_acquire_sweeper_leadership(str(db_dir / "chain.db"))
    assert fd is not None and fd >= 0
    assert (db_dir / LOCK_DIR_NAME / LOCK_FILE_NAME).is_file()
    release_sweeper_leadership(fd)


def test_holder_death_frees_the_lock(db_dir: Path):
    """A crashed leader drops the flock; the next process acquires — the
    uvicorn-respawn path."""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import sys
                from aitbc_chain.rpc.sweeper_leader import try_acquire_sweeper_leadership
                fd = try_acquire_sweeper_leadership(sys.argv[1])
                assert fd is not None and fd >= 0
                # exit without releasing: the kernel must drop the flock
                """
            ),
            str(db_dir / "chain.db"),
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
        check=True,
    )
    assert child.returncode == 0
    fd = try_acquire_sweeper_leadership(str(db_dir / "chain.db"))
    assert fd is not None and fd >= 0
    release_sweeper_leadership(fd)


def test_memory_db_leads_ungated():
    assert try_acquire_sweeper_leadership(":memory:") == UNLOCKED


def test_unopenable_lock_fails_open(db_dir: Path):
    """An unusable lock path leads anyway (fail-open: a dead sweeper is worse
    than a double one). A db path inside a regular file raises NotADirectoryError
    on the mkdir — works regardless of euid."""
    not_a_dir = db_dir / "regular-file"
    not_a_dir.touch()
    assert try_acquire_sweeper_leadership(str(not_a_dir / "chain.db")) == UNLOCKED
