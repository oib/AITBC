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

_COORDINATOR_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    db_path = tmp_path / "test_migrations.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(_COORDINATOR_ROOT / "src")
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


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Online upgrade to head and downgrade to base should be symmetric."""
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "base")


def test_alembic_offline_sql(tmp_path: Path) -> None:
    """Offline SQL generation should complete and emit core schema statements."""
    result = _run_alembic(tmp_path, "upgrade", "head", "--sql")
    stdout = result.stdout
    assert "CREATE TABLE" in stdout, "Offline SQL should contain CREATE TABLE statements"
    assert "UPDATE alembic_version" in stdout, "Offline SQL should update alembic_version"
    assert "CREATE INDEX IF NOT EXISTS" in stdout, "Offline SQL should contain idempotent index creation"


def test_alembic_single_head() -> None:
    """The migration graph should have exactly one head."""
    result = _run_alembic(Path("/tmp"), "heads")
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected exactly one head, got: {heads}"
