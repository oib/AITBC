"""trading migrations against a disposable PostgreSQL cluster (PG-TARGET-1 stream 3).

Same proof as the pool-hub variant: ``alembic upgrade head``, a real insert,
a real read, then ``downgrade base`` — all on a throwaway local-socket
cluster. The suite's default run is unchanged (SQLite); this test exists only
behind ``requires_postgres``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from aitbc.testing.pg_cluster import assert_local_pg_url

pytest_plugins = ["aitbc.testing.pytest_pg"]

pytestmark = pytest.mark.requires_postgres

_APP_ROOT = Path(__file__).resolve().parent.parent


def _alembic_cfg() -> Config:
    cfg = Config(str(_APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_APP_ROOT / "alembic"))
    return cfg


def test_trading_migrations_on_throwaway_cluster(postgres_cluster, monkeypatch) -> None:
    psycopg2 = pytest.importorskip("psycopg2")
    postgres_cluster.create_database("trading_pg_test")
    sa_dsn = postgres_cluster.dsn("trading_pg_test", driver="postgresql+psycopg2")
    sync_dsn = postgres_cluster.dsn("trading_pg_test", driver="postgresql")
    assert_local_pg_url(sa_dsn)
    assert_local_pg_url(sync_dsn)
    # trading's shared resolver honours DB_TYPE+DB_* first — clear them so
    # DATABASE_URL is the single source, pointing at the throwaway socket.
    for var in ("DB_TYPE", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", sa_dsn)

    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(sync_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO island_registry (chain_id, endpoint, status, registered_at, last_sync)
                VALUES ('pg-probe-chain', 'http://127.0.0.1:8202', 'active', now(), now())
                """
            )
            cur.execute("SELECT endpoint FROM island_registry WHERE chain_id = 'pg-probe-chain'")
            row = cur.fetchone()
            assert row is not None and row[0] == "http://127.0.0.1:8202"
    finally:
        conn.close()

    command.downgrade(cfg, "base")

    conn = psycopg2.connect(sync_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.island_registry')")
            assert cur.fetchone() == (None,)
    finally:
        conn.close()
