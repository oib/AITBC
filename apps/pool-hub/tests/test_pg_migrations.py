"""pool-hub migrations against a disposable PostgreSQL cluster (PG-TARGET-1 stream 3).

Runs ``alembic upgrade head``, a real insert, a real read, and ``downgrade
base`` on a throwaway cluster — never on a deployed database. The DSN is a
local unix socket and is re-checked by ``assert_local_pg_url``.
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
    cfg.set_main_option("script_location", str(_APP_ROOT / "migrations"))
    return cfg


def test_pool_hub_migrations_on_throwaway_cluster(postgres_cluster, monkeypatch) -> None:
    psycopg2 = pytest.importorskip("psycopg2")
    postgres_cluster.create_database("poolhub_pg_test")
    async_dsn = postgres_cluster.dsn("poolhub_pg_test", driver="postgresql+asyncpg")
    sync_dsn = postgres_cluster.dsn("poolhub_pg_test", driver="postgresql")
    assert_local_pg_url(async_dsn)
    assert_local_pg_url(sync_dsn)
    monkeypatch.setenv("DATABASE_URL", async_dsn)
    monkeypatch.delenv("SQLITE_URL", raising=False)
    monkeypatch.delenv("POOLHUB_POSTGRES_DSN", raising=False)

    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(sync_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO miners (miner_id, api_key_hash, addr, proto, gpu_vram_gb,
                                    cpu_cores, ram_gb, max_parallel, base_price, chain_id)
                VALUES ('pg-probe-miner', 'probehash', 'socket://local', 'http',
                        24.0, 8, 64.0, 2, 1.5, 'pg-probe')
                """
            )
            cur.execute("SELECT miner_id, base_price FROM miners WHERE miner_id = 'pg-probe-miner'")
            row = cur.fetchone()
            assert row is not None and row[0] == "pg-probe-miner"
    finally:
        conn.close()

    command.downgrade(cfg, "base")

    conn = psycopg2.connect(sync_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.miners')")
            assert cur.fetchone() == (None,)
    finally:
        conn.close()
