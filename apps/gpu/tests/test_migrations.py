"""PG-TARGET-1 stream 2: gpu alembic graph is portable and self-sufficient.

Two pinned defects:

- ``4d6e9c8a1b52`` probed column existence with ``PRAGMA table_info`` —
  SQLite-only syntax that aborts the whole upgrade on PostgreSQL. The
  check now goes through ``sa.inspect``.
- Neither revision created anything: both were alteration-only, so an
  empty database upgraded to head held only ``alembic_version``. A
  baseline revision (``0001a2b3c4d5``) now ``create_all``s every
  ``gpu_metadata`` table.

Everything runs on a temporary SQLite file — no live database and no
PostgreSQL service is touched. PostgreSQL coverage is a compile check:
the baseline table renders valid DDL under the postgresql dialect.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

GPU_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = GPU_ROOT.parent.parent


def _run_alembic(tmp_path: Path, *args: str, db_name: str = "gpu_migrations.db") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / db_name}"
    env["PYTHONPATH"] = f"{GPU_ROOT / 'src'}:{REPO_ROOT}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=GPU_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def _model_tables() -> set[str]:
    sys.path.insert(0, str(GPU_ROOT / "src"))
    try:
        from gpu_service.domain import gpu_market  # noqa: F401  (registers tables)
        from gpu_service.domain.base import gpu_metadata

        return set(gpu_metadata.tables)
    finally:
        sys.path.remove(str(GPU_ROOT / "src"))


def test_no_sqlite_pragma_in_revision_sources() -> None:
    versions = GPU_ROOT / "alembic" / "versions"
    offenders = []
    for path in versions.glob("*.py"):
        for line in path.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue  # comments may narrate the old pragma; they don't run
            if "PRAGMA" in line:
                offenders.append(path.name)
                break
    assert not offenders, f"SQLite-only PRAGMA in migrations: {offenders}"


def test_upgrade_head_on_empty_db_creates_every_model_table(tmp_path: Path) -> None:
    db_path = tmp_path / "gpu_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {r[1] for r in con.execute("SELECT * FROM pragma_table_info('gpu_registry')")}
    finally:
        con.close()
    missing = _model_tables() - tables
    assert not missing, f"model tables missing after upgrade head: {sorted(missing)}"
    assert "chain_id" in cols


def test_downgrade_base_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "gpu_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "base")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert tables <= {"alembic_version"}, f"tables survived downgrade base: {sorted(tables)}"
    _run_alembic(tmp_path, "upgrade", "head")


def test_baseline_table_renders_postgresql_ddl() -> None:
    """The baseline's create is real PostgreSQL DDL, not SQLite-flavoured."""
    sys.path.insert(0, str(GPU_ROOT / "src"))
    try:
        from gpu_service.domain import gpu_market  # noqa: F401
        from gpu_service.domain.base import gpu_metadata

        table = gpu_metadata.tables["gpu_registry"]
        ddl = str(sa.schema.CreateTable(table).compile(dialect=postgresql.dialect()))
    finally:
        sys.path.remove(str(GPU_ROOT / "src"))
    assert "CREATE TABLE gpu_registry" in ddl
    assert "NUMERIC(20, 8)" in ddl or "NUMERIC(20,8)" in ddl
