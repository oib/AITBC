"""PG-TARGET-1 stream 2: pool-hub downgrade correctness on SQLite.

Two pinned defects:

- ``c3b2d6e7f8a9`` listed three indexes ``b2a1c4d5e6f7`` had already
  created (``ix_sla_metrics_miner_id``, ``ix_sla_violations_miner_id``,
  ``ix_sla_violations_created_at``). Its ``if_not_exists`` upgrade made
  them no-ops, but downgrade() dropped them — so b2's own downgrade then
  failed dropping them a second time. Index drops are now exactly the
  indexes this revision creates.
- ``d4c3e7f8a9b0`` used bare ``op.alter_column(nullable=...)``, which is
  a ``SET NOT NULL`` SQLite cannot execute; batch mode rebuilds instead.

Runs on a temporary SQLite file — no live database is touched.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

POOL_HUB = Path(__file__).resolve().parents[1]
REPO_ROOT = POOL_HUB.parent.parent


def _run_alembic(tmp_path: Path, *args: str, db_name: str = "poolhub_migrations.db") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / db_name}"
    env.pop("SQLITE_URL", None)
    env.pop("POOLHUB_POSTGRES_DSN", None)
    env["PYTHONPATH"] = f"{POOL_HUB / 'src'}:{REPO_ROOT}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=POOL_HUB,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def _index_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()


def test_index_revision_downgrade_leaves_b2_indexes_intact(tmp_path: Path) -> None:
    """Downgrading c3b2d6e7f8a9 must not touch b2a1c4d5e6f7's indexes."""
    _run_alembic(tmp_path, "upgrade", "c3b2d6e7f8a9")
    _run_alembic(tmp_path, "downgrade", "-1")
    db_path = tmp_path / "poolhub_migrations.db"
    earlier_indexes = {
        # owned by b2a1c4d5e6f7
        "ix_sla_metrics_miner_id",
        "ix_sla_metrics_timestamp",
        "ix_sla_metrics_metric_type",
        "ix_sla_violations_miner_id",
        "ix_sla_violations_created_at",
        "ix_sla_violations_severity",
        "ix_capacity_snapshots_timestamp",
        # owned by a58c1f3b3e87
        "ix_feedback_miner_id",
        "ix_feedback_job_id",
        "ix_match_results_request_id",
    }
    missing = earlier_indexes - _index_names(db_path)
    assert not missing, f"earlier-revision indexes dropped by c3's downgrade: {sorted(missing)}"
    gone = {
        "ix_match_results_miner_id",
        "ix_match_results_created_at",
        "ix_feedback_created_at",
    } & _index_names(db_path)
    assert not gone, f"c3 indexes that should have been dropped: {sorted(gone)}"


def test_full_downgrade_base_sweep(tmp_path: Path) -> None:
    """head -> base must run clean, including d4c3e7f8a9b0's column rebuild."""
    db_path = tmp_path / "poolhub_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "base")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        con.close()
    assert version == []
    _run_alembic(tmp_path, "upgrade", "head")
