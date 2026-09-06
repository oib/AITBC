"""P0-3 — Fresh-database migration tests for both migration chains.

Both the coordinator-api and blockchain-node migration chains must migrate
cleanly from an empty SQLite database. This was broken because:

* The coordinator baseline (``001_initial_migration``) calls
  ``SQLModel.metadata.create_all``, which creates the *current* schema on a
  fresh database. Later migrations that ``ALTER TABLE ... ADD COLUMN`` then
  fail with ``duplicate column name``.
* The blockchain baseline (``e31f486f1484``) does not create the ``escrow``
  table at all — it was historically created by ``create_all`` at app
  startup. Migrations that ``ALTER TABLE escrow`` fail with
  ``no such table: escrow``.
* The blockchain backfill migration ``9f8e7d6c5b4a`` references
  ``transaction.type`` and ``transaction.value``, which are not created by
  any migration — they come from ``create_all`` at app startup.

These tests guard against regression by running each chain to ``head``
against a temporary empty SQLite file and asserting success.

Run with: ``pytest tests/unit/test_fresh_db_migrations.py -v``
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_DIR = REPO_ROOT / "apps" / "coordinator-api"
BLOCKCHAIN_DIR = REPO_ROOT / "apps" / "blockchain-node"


def _run_alembic_upgrade(app_dir: Path, alembic_ini: str, db_path: Path, extra_env: dict[str, str] | None = None) -> None:
    """Run ``alembic upgrade head`` against a fresh SQLite database.

    Raises ``AssertionError`` if the migration fails.
    """
    from alembic.config import Config
    from alembic import command

    db_url = f"sqlite:///{db_path}"
    env = {
        "DATABASE_URL": db_url,
        "ENVIRONMENT": "development",
    }
    if extra_env:
        env.update(extra_env)

    old_environ = os.environ.copy()
    os.environ.update(env)
    try:
        cfg = Config(str(app_dir / alembic_ini))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


@pytest.fixture
def fresh_db():
    """Yield a path to a temporary SQLite file that does not yet exist."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    # Remove the file so the database starts truly empty.
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


def test_coordinator_fresh_db_migration(fresh_db):
    """Coordinator-api migrations must succeed from an empty database."""
    _run_alembic_upgrade(COORDINATOR_DIR, "alembic.ini", fresh_db)
    assert fresh_db.exists(), "Database file should exist after migration"
    # Verify the alembic_version table was created and has a head revision.
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        cursor = conn.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()
        assert version is not None, "alembic_version table should have a row"
        assert version[0], "alembic_version should be non-empty"
    finally:
        conn.close()


def test_blockchain_fresh_db_migration(fresh_db):
    """Blockchain-node migrations must succeed from an empty database."""
    _run_alembic_upgrade(
        BLOCKCHAIN_DIR,
        "alembic.ini",
        fresh_db,
        extra_env={"CHAIN_ID": "ait-hub.aitbc.bubuit.net"},
    )
    assert fresh_db.exists(), "Database file should exist after migration"
    import sqlite3

    conn = sqlite3.connect(str(fresh_db))
    try:
        cursor = conn.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()
        assert version is not None, "alembic_version table should have a row"
        assert version[0], "alembic_version should be non-empty"
        # Verify the escrow table was created (by c9a4f1e2b73d).
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='escrow'"
        )
        assert cursor.fetchone() is not None, "escrow table should exist"
    finally:
        conn.close()


def test_coordinator_fresh_db_migration_idempotent(fresh_db):
    """Running coordinator migrations twice should not fail.

    The exit gate for P0 says "migrate cleanly from an empty database in CI,
    twice in a row." The second run should be a no-op (alembic stamps the
    version and skips already-applied revisions).
    """
    _run_alembic_upgrade(COORDINATOR_DIR, "alembic.ini", fresh_db)
    # Second run should succeed (no-op).
    _run_alembic_upgrade(COORDINATOR_DIR, "alembic.ini", fresh_db)


def test_blockchain_fresh_db_migration_idempotent(fresh_db):
    """Running blockchain migrations twice should not fail."""
    _run_alembic_upgrade(
        BLOCKCHAIN_DIR,
        "alembic.ini",
        fresh_db,
        extra_env={"CHAIN_ID": "ait-hub.aitbc.bubuit.net"},
    )
    # Second run should succeed (no-op).
    _run_alembic_upgrade(
        BLOCKCHAIN_DIR,
        "alembic.ini",
        fresh_db,
        extra_env={"CHAIN_ID": "ait-hub.aitbc.bubuit.net"},
    )
