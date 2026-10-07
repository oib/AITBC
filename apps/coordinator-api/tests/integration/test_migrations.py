"""Regression tests for the coordinator-api Alembic migration graph.

These tests exercise the migration graph end-to-end on a temporary SQLite
database: online upgrade to head, downgrade to base, and offline SQL
emission. They are intentionally standalone (shelling out to ``alembic``) so
they validate the exact command-line path operations teams use.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from .test_b8_schema_conformance import _semantic_schema

_COORDINATOR_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = _COORDINATOR_ROOT.parent.parent


def _run_alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    db_path = tmp_path / "test_migrations.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    # The repo root is needed so `import aitbc` resolves; `coordinator_api.src` is
    # needed for the alembic env itself.
    env["PYTHONPATH"] = f"{_COORDINATOR_ROOT / 'src'}:{REPO_ROOT}"
    # Ensure app settings can boot inside the subprocess without a real audit dir
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
    return result


def test_alembic_offline_sql(tmp_path: Path) -> None:
    """Offline SQL generation should complete and emit core schema statements."""
    result = _run_alembic(tmp_path, "upgrade", "head", "--sql")
    stdout = result.stdout
    assert "CREATE TABLE" in stdout, "Offline SQL should contain CREATE TABLE statements"
    assert "UPDATE alembic_version" in stdout, "Offline SQL should update alembic_version"
    assert "CREATE INDEX IF NOT EXISTS" in stdout, "Offline SQL should contain idempotent index creation"


def test_alembic_single_head() -> None:
    """The migration graph should have exactly one head."""
    result = _run_alembic(Path("/tmp"), "heads")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected exactly one head, got: {heads}"


def _version_num(db_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    return version


def test_upgrade_head_twice_is_noop(tmp_path: Path) -> None:
    """B-8 follow-on (a/b): a second `upgrade head` on a stamped DB is a no-op."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    before = _semantic_schema(db_path)
    version = _version_num(db_path)

    second = _run_alembic(tmp_path, "upgrade", "head")

    assert "Running upgrade" not in second.stdout, f"second upgrade ran migrations:\n{second.stdout[-2000:]}"
    assert _semantic_schema(db_path) == before, "schema changed on re-upgrade"
    assert _version_num(db_path) == version


def test_downgrade_latest_then_upgrade_roundtrips(tmp_path: Path) -> None:
    """B-8 follow-on (c): downgrade -1 then upgrade head restores the schema."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "head")
    before = _semantic_schema(db_path)
    head_version = _version_num(db_path)

    _run_alembic(tmp_path, "downgrade", "-1")
    assert _version_num(db_path) != head_version

    _run_alembic(tmp_path, "upgrade", "head")

    assert _version_num(db_path) == head_version
    after = _semantic_schema(db_path)
    assert after == before, "schema differs after downgrade+upgrade round-trip"
