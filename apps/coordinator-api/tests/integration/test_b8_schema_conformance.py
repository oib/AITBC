"""
B-8: Schema-conformance test for the coordinator-api migration graph.

The 001_initial migration uses SQLModel.metadata.create_all() dynamically —
a fresh deploy gets today's models, not a historical schema. Subsequent
migrations then add columns that may already exist (handled by checkfirst
and idempotence guards).

This test asserts that a fresh `alembic upgrade head` produces a schema that
matches the declared models. If it doesn't, there's drift between the
migration graph and the models — which means either a migration is missing
or a model column was added without a migration.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

_COORDINATOR_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = _COORDINATOR_ROOT.parent.parent


def _run_alembic(tmp_path: Path, *args: str) -> Path:
    """Run alembic and return the DB path that was used."""
    db_path = tmp_path / "test_conformance.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    env.setdefault("AUDIT_LOG_DIR", str(tmp_path / "audit"))
    env.setdefault("TEST_MODE", "true")

    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(
        cmd,
        cwd=_COORDINATOR_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return db_path


def _get_model_columns() -> dict[str, set[str]]:
    """Return {table_name: {column_names}} from the declared SQLModel metadata."""
    # Keep this in lock-step with the 001_initial migration's model imports so the
    # test compares the migration output against the schema the migration actually
    # intends to create, not against whichever models happened to be loaded by the
    # test collection order.
    import coordinator_api.main  # noqa: F401
    import coordinator_api.models.multitenant  # noqa: F401
    from sqlmodel import SQLModel

    tables: dict[str, set[str]] = {}
    for table_name, table in SQLModel.metadata.tables.items():
        tables[table_name] = {col.name for col in table.columns}
    return tables


def test_fresh_upgrade_head_matches_declared_models(tmp_path: Path):
    """A fresh `alembic upgrade head` should produce a schema matching the models.

    This catches:
    - Model columns added without a migration (schema would be missing them)
    - Migration columns that no longer exist in models (schema would have extras)
    - The 001_initial dynamic create_all drifting from the migration graph
    """
    db_path = _run_alembic(tmp_path, "upgrade", "head")

    # Inspect the resulting schema
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    db_tables: dict[str, set[str]] = {}
    for table_name in inspector.get_table_names():
        if table_name == "alembic_version":
            continue
        db_tables[table_name] = {col["name"] for col in inspector.get_columns(table_name)}
    engine.dispose()

    # Get the declared model columns
    model_tables = _get_model_columns()

    # Compare
    db_table_names = set(db_tables.keys())
    model_table_names = set(model_tables.keys())

    missing_tables = model_table_names - db_table_names
    extra_tables = db_table_names - model_table_names

    assert not missing_tables, f"Tables in models but missing from DB after upgrade: {missing_tables}"
    assert not extra_tables, f"Tables in DB after upgrade but not in models: {extra_tables}"

    for table_name in model_table_names & db_table_names:
        model_cols = model_tables[table_name]
        db_cols = db_tables[table_name]
        missing_cols = model_cols - db_cols
        extra_cols = db_cols - model_cols
        assert not missing_cols, f"Table '{table_name}': columns in models but missing from DB: {missing_cols}"
        assert not extra_cols, f"Table '{table_name}': columns in DB but not in models: {extra_cols}"


def test_alembic_head_is_not_initial_migration(tmp_path: Path):
    """The alembic version table should not be stuck at initial_migration."""
    db_path = _run_alembic(tmp_path, "upgrade", "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()
    engine.dispose()

    assert version is not None, "alembic_version table is empty after upgrade head"
    assert version != "initial_migration", "upgrade head stopped at initial_migration — subsequent migrations didn't run"
