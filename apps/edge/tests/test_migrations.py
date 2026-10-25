"""PG-TARGET-1 stream 2: edge alembic graph builds an empty database.

The only shipped revision was alteration-only, so ``alembic upgrade
head`` on a fresh database produced just ``alembic_version`` and left
``init_db``/``create_all`` to build the real schema untracked. Baseline
revision ``0001b2c3d4e5`` now ``create_all``s every table registered on
``SQLModel.metadata``.

Runs on a temporary SQLite file — no live database, no PostgreSQL
service. The edge env resolves its URL from ``aitbc_edge.config``
settings whose ``url`` field maps to the bare ``URL`` env var (see the
config comment on why ``DATABASE_URL`` alone does nothing here);
``DATABASE_ADAPTER``+``DATABASE_URL`` are set too as the documented pair.
PostgreSQL coverage is a compile check under the postgresql dialect.
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

EDGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDGE_ROOT.parent.parent


def _env(tmp_path: Path, db_name: str) -> dict[str, str]:
    env = os.environ.copy()
    url = f"sqlite:///{tmp_path / db_name}"
    env["URL"] = url
    env["DATABASE_URL"] = url
    env["DATABASE_ADAPTER"] = "sqlite"
    env["PYTHONPATH"] = f"{EDGE_ROOT / 'src'}:{REPO_ROOT}"
    # pydantic-settings reads the bare name; a leaked DEBUG=release is not a bool.
    env.pop("DEBUG", None)
    return env


def _run_alembic(tmp_path: Path, *args: str, db_name: str = "edge_migrations.db") -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=EDGE_ROOT,
        env=_env(tmp_path, db_name),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def _model_tables() -> set[str]:
    sys.path.insert(0, str(EDGE_ROOT / "src"))
    try:
        from aitbc_edge.schemas import database, gpu, island, metrics, serve  # noqa: F401
        from sqlmodel import SQLModel

        return set(SQLModel.metadata.tables)
    finally:
        sys.path.remove(str(EDGE_ROOT / "src"))


def test_upgrade_head_on_empty_db_creates_every_model_table(tmp_path: Path) -> None:
    db_path = tmp_path / "edge_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    missing = _model_tables() - tables
    assert not missing, f"model tables missing after upgrade head: {sorted(missing)}"


def test_downgrade_base_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "edge_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "base")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert tables <= {"alembic_version"}, f"tables survived downgrade base: {sorted(tables)}"
    _run_alembic(tmp_path, "upgrade", "head")


def test_baseline_tables_render_postgresql_ddl() -> None:
    sys.path.insert(0, str(EDGE_ROOT / "src"))
    try:
        from aitbc_edge.schemas import database, gpu, island, metrics, serve  # noqa: F401
        from sqlmodel import SQLModel

        for name, table in SQLModel.metadata.tables.items():
            ddl = str(sa.schema.CreateTable(table).compile(dialect=postgresql.dialect()))
            assert f"CREATE TABLE {name}" in ddl
    finally:
        sys.path.remove(str(EDGE_ROOT / "src"))
