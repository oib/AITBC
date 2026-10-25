"""PG-TARGET-1 stream 4: migrate_to_postgresql.py on a disposable cluster.

End-to-end against the stream-3 throwaway PostgreSQL fixture: a real
coordinator SQLite database (``alembic upgrade head`` on a temp file, then
populated rows covering JSON, enum, boolean, datetime and NUMERIC money
columns) is transferred to a fresh PG database whose schema the script
itself builds via ``alembic upgrade head``. Never touches a live database —
every DSN comes from ``LocalPostgresCluster`` and is re-checked by
``assert_local_pg_url``.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

from aitbc.testing.pg_cluster import assert_local_pg_url

pytest_plugins = ["aitbc.testing.pytest_pg"]

pytestmark = pytest.mark.requires_postgres

_APP_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _APP_ROOT.parent.parent
_SCRIPT = _APP_ROOT / "scripts" / "migrate_to_postgresql.py"


def _env(**extra: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_APP_ROOT / 'src'}:{_REPO_ROOT}"
    env.setdefault("AUDIT_LOG_DIR", "/var/tmp/aitbc-mig-test-audit")
    env.setdefault("TEST_MODE", "true")
    env.update(extra)
    return env


def _sqlite_upgrade_head(db_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_APP_ROOT,
        env=_env(DATABASE_URL=f"sqlite:///{db_path}"),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr


def _run_migrator(db_path: Path, dsn: str, *flags: str) -> subprocess.CompletedProcess[str]:
    assert_local_pg_url(dsn)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--source", str(db_path), "--target-url", dsn, *flags],
        cwd=_APP_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )


def _populate(db_path: Path) -> None:
    """Insert rows covering JSON, enum, boolean, datetime and money columns."""
    conn = sqlite3.connect(db_path)
    try:
        # Parent rows first: job.client_id -> users.id,
        # usage_records.tenant_id -> tenants.id (enforced on PostgreSQL).
        conn.execute(
            """INSERT INTO users (id, email, username, status, created_at, updated_at)
               VALUES ('client-1', 'c1@example.invalid', 'client1', 'active',
                       '2026-10-25 10:00:00', '2026-10-25 10:00:00')"""
        )
        conn.execute(
            """INSERT INTO tenants (id, name, slug, status, plan, contact_email, created_at, updated_at)
               VALUES ('11111111111111111111111111111111', 'Tenant One', 'tenant-one', 'active', 'pro', 't1@example.invalid',
                       '2026-10-25 10:00:00', '2026-10-25 10:00:00')"""
        )
        conn.execute(
            """INSERT INTO miner (id, region, capabilities, concurrency, status, inflight,
                                  extra_metadata, last_heartbeat, jobs_completed, jobs_failed,
                                  total_job_duration_ms, average_job_duration_ms)
               VALUES ('miner-1', 'eu-west-1', '{"gpu": true, "vram_gb": 24}', 2, 'active', 0,
                       '{"notes": "pg probe"}', '2026-10-25 12:00:00', 7, 1, 123456, 17.5)"""
        )
        conn.execute(
            """INSERT INTO job (id, client_id, state, payload, constraints, ttl_seconds,
                               requested_at, expires_at, requires_cross_chain_settlement,
                               protected, payment_amount, payment_token)
               VALUES ('job-1', 'client-1', 'completed', '{"model": "probe"}', '{}', 3600,
                       '2026-10-25 11:00:00', '2026-10-25 13:00:00', 0, 0,
                       123456789, 'AIT')"""
        )
        conn.execute(
            """INSERT INTO jobreceipt (id, job_id, receipt_id, payload, created_at)
               VALUES ('receipt-1', 'job-1', 'rcpt-1', '{"ok": true}', '2026-10-25 12:30:00')"""
        )
        conn.execute(
            """INSERT INTO usage_records (id, tenant_id, resource_type, resource_id, quantity,
                                         unit, unit_price, total_cost, currency, recorded_at)
               VALUES ('22222222222222222222222222222222', '11111111111111111111111111111111', 'gpu-hours', 'job-1', 2, 'hour', 50000000, 100000000,
                       'AIT', '2026-10-25 12:45:00')"""
        )
        conn.commit()
    finally:
        conn.close()


def _count(dsn: str, table: str) -> int:
    engine = sa.create_engine(dsn)
    try:
        with engine.connect() as conn:
            return int(conn.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
    finally:
        engine.dispose()


def test_dry_run_is_default_and_writes_nothing(tmp_path, pg_url) -> None:
    db_path = tmp_path / "coord_source.db"
    _sqlite_upgrade_head(db_path)
    _populate(db_path)
    dsn = pg_url("coord_mig_dry")

    result = _run_migrator(db_path, dsn)
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert "miner" in result.stdout

    # No schema was built and no rows were written: the DB is still empty.
    engine = sa.create_engine(dsn)
    try:
        assert sa.inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_execute_copies_and_verifies(tmp_path, pg_url) -> None:
    db_path = tmp_path / "coord_source.db"
    _sqlite_upgrade_head(db_path)
    _populate(db_path)
    dsn = pg_url("coord_mig_exec")

    result = _run_migrator(db_path, dsn, "--execute")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "checksums verified" in result.stdout

    # The schema came from alembic: the target is stamped at head and holds
    # every table — including enum-typed marketplace_regions seeded by the
    # migration itself on both sides.
    assert _count(dsn, "miner") == 1
    assert _count(dsn, "job") == 1
    assert _count(dsn, "jobreceipt") == 1
    assert _count(dsn, "usage_records") == 1
    assert _count(dsn, "marketplace_regions") == 4  # enum-label rows copied verbatim


def test_nonempty_target_refused_then_insert_missing_only(tmp_path, pg_url) -> None:
    db_path = tmp_path / "coord_source.db"
    _sqlite_upgrade_head(db_path)
    _populate(db_path)
    dsn = pg_url("coord_mig_retry")

    first = _run_migrator(db_path, dsn, "--execute")
    assert first.returncode == 0, first.stderr

    # Second run without --allow-nonempty must refuse before touching rows.
    second = _run_migrator(db_path, dsn, "--execute")
    assert second.returncode != 0
    assert "already holds rows" in second.stderr

    # With --allow-nonempty every source row is skipped, never overwritten.
    third = _run_migrator(db_path, dsn, "--execute", "--allow-nonempty")
    assert third.returncode == 0, f"{third.stdout}\n{third.stderr}"
    assert _count(dsn, "miner") == 1
    assert _count(dsn, "job") == 1
    assert _count(dsn, "usage_records") == 1


def test_allow_nonempty_keeps_preexisting_rows(tmp_path, pg_url) -> None:
    """A target row whose PK is absent from the source survives untouched."""
    db_path = tmp_path / "coord_source.db"
    _sqlite_upgrade_head(db_path)
    _populate(db_path)
    dsn = pg_url("coord_mig_pre")

    first = _run_migrator(db_path, dsn, "--execute")
    assert first.returncode == 0, first.stderr

    # Add a row to the source and a *different* row to the target; the copy
    # must add only the new source row and leave the target-only row alone.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO miner (id, region, capabilities, concurrency, status, inflight,
                                  extra_metadata, last_heartbeat, jobs_completed, jobs_failed,
                                  total_job_duration_ms, average_job_duration_ms)
               VALUES ('miner-2', 'us-east-1', '{}', 1, 'active', 0, '{}',
                       '2026-10-25 13:00:00', 0, 0, 0, 0.0)"""
        )
        conn.commit()
    finally:
        conn.close()
    engine = sa.create_engine(dsn)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """INSERT INTO miner (id, region, capabilities, concurrency, status, inflight,
                                         extra_metadata, last_heartbeat, jobs_completed, jobs_failed,
                                         total_job_duration_ms, average_job_duration_ms)
                       VALUES ('miner-target-only', 'ap-south-1', '{}'::json, 1, 'active', 0, '{}'::json,
                               '2026-10-25 13:00:00', 0, 0, 0, 0.0)"""
                )
            )
    finally:
        engine.dispose()

    result = _run_migrator(db_path, dsn, "--execute", "--allow-nonempty")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert _count(dsn, "miner") == 3
