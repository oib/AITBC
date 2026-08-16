"""Stamp against DATABASE_URL must persist after the process exits.

pool-hub's async env.py used to configure Alembic without begin_transaction, so
stamp/upgrade ran and rolled back when the connection closed. alembic.ini still
points at user:pass@localhost; that URL must never be the target.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

POOL_HUB = Path(__file__).resolve().parents[1]
ALEMBIC = Path("/opt/aitbc/venv/bin/alembic")
HEAD = "e5d4f8a9b0c1"


@pytest.mark.skipif(not ALEMBIC.is_file(), reason="venv alembic not installed")
def test_stamp_survives_process_exit(tmp_path: Path) -> None:
    db = tmp_path / "poolhub.db"
    url = f"sqlite+aiosqlite:///{db}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env.pop("SQLITE_URL", None)
    env.pop("POOLHUB_POSTGRES_DSN", None)

    stamp = subprocess.run(
        [str(ALEMBIC), "stamp", HEAD],
        cwd=POOL_HUB,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stamp.returncode == 0, stamp.stderr
    assert "user:pass@localhost" not in stamp.stderr
    assert str(db) in stamp.stderr

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    versions = [row[0] for row in con.execute("select version_num from alembic_version")]
    con.close()
    assert versions == [HEAD]
