"""Widen mempool.fee to BIGINT and mempool.received_at to DOUBLE PRECISION.

Revision ID: a7c3d9e2f184
Revises: f7a3c5e9b1d2
Create Date: 2026-11-03 00:00:00.000000

Refs #797 (operator ruling 4A): alembic migration on both backends — sqlite
rebuild + Postgres ALTER, preserving every existing row.

The 32-bit pair capped fees at ~59.65 AIT (int4 overflow raised a driver
error inside mempool.add) and rounded received_at to a 128 s granularity,
which feeds the eviction tie-break. Fresh tables get the wide types from
DatabaseMempool._init_table; this revision converges tables that already
exist.

The mempool table is not always in the chain database: deployments that set
MEMPOOL_DB_URL keep it in a dedicated (usually Postgres) database. The
revision therefore widens the table in the primary bind when present and
then repeats against settings.mempool_db_url when configured. Both paths
are idempotent and existence-guarded.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "a7c3d9e2f184"
down_revision: str | None = "f7a3c5e9b1d2"
branch_labels: str | None = None
depends_on: str | None = None


def _column_types(conn: sa.engine.Connection, table: str) -> dict[str, str]:
    inspector = sa.inspect(conn)
    if table not in inspector.get_table_names():
        return {}
    if conn.dialect.name == "sqlite":
        # Inspector normalizes DOUBLE PRECISION to REAL; the declared text
        # is the only way to tell an old table from a rebuilt one.
        return {row[1]: (row[2] or "").lower() for row in conn.execute(text(f"PRAGMA table_info({table})")).all()}
    return {c["name"]: str(c["type"]).lower() for c in inspector.get_columns(table)}


def _rebuild_sqlite(conn: sa.engine.Connection, types: dict[str, str]) -> None:
    """Recreate mempool with wide declared types, copying every row.

    sqlite declared types are advisory — values were never constrained — so
    the rebuild is catalog hygiene; all columns ride over verbatim. The
    column set is derived from the live table so this works on tables that
    predate or postdate the slot/signed columns.
    """
    overrides = {"fee": "BIGINT", "received_at": "DOUBLE PRECISION"}
    cols = ", ".join(f"{name} {overrides.get(name, types[name])}" for name in types)
    names = ", ".join(types)
    conn.execute(text(f"CREATE TABLE mempool_new ({cols}, PRIMARY KEY (chain_id, tx_hash))"))
    conn.execute(text(f"INSERT INTO mempool_new SELECT {names} FROM mempool"))  # nosec B608 — identifiers from PRAGMA/inspector, never user input
    conn.execute(text("DROP TABLE mempool"))
    conn.execute(text("ALTER TABLE mempool_new RENAME TO mempool"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mempool_sender_nonce ON mempool(chain_id, sender, nonce)"))


def _widen(conn: sa.engine.Connection) -> None:
    types = _column_types(conn, "mempool")
    if not types:
        return
    if conn.dialect.name == "postgresql":
        if types.get("fee") == "integer":
            conn.execute(text("ALTER TABLE mempool ALTER COLUMN fee TYPE BIGINT"))
        if types.get("received_at") == "real":
            conn.execute(text("ALTER TABLE mempool ALTER COLUMN received_at TYPE DOUBLE PRECISION"))
    elif conn.dialect.name == "sqlite":
        if types.get("fee") != "bigint" or types.get("received_at") != "double precision":
            _rebuild_sqlite(conn, types)


def _mempool_extra_bind() -> sa.engine.Engine | None:
    """Engine for a dedicated MEMPOOL_DB_URL database, if one is configured."""
    try:
        from aitbc_chain.config import settings
    except Exception:
        return None
    url = getattr(settings, "mempool_db_url", "") or ""
    if not url:
        return None
    return sa.create_engine(url)


def upgrade() -> None:
    bind = op.get_bind()
    _widen(bind)
    engine = _mempool_extra_bind()
    if engine is None:
        return
    try:
        with engine.connect() as conn:
            with conn.begin():
                _widen(conn)
    finally:
        engine.dispose()


def downgrade() -> None:
    bind = op.get_bind()
    types = _column_types(bind, "mempool")
    if not types:
        return
    if bind.dialect.name == "postgresql":
        conn = bind
        if types.get("fee") == "bigint":
            conn.execute(text("ALTER TABLE mempool ALTER COLUMN fee TYPE INTEGER"))
        if types.get("received_at") == "double precision":
            conn.execute(text("ALTER TABLE mempool ALTER COLUMN received_at TYPE REAL"))
    elif bind.dialect.name == "sqlite":
        overrides = {"fee": "INTEGER", "received_at": "REAL"}
        cols = ", ".join(f"{name} {overrides.get(name, types[name])}" for name in types)
        names = ", ".join(types)
        conn = bind
        conn.execute(text(f"CREATE TABLE mempool_old ({cols}, PRIMARY KEY (chain_id, tx_hash))"))
        conn.execute(text(f"INSERT INTO mempool_old SELECT {names} FROM mempool"))  # nosec B608 — identifiers from PRAGMA/inspector, never user input
        conn.execute(text("DROP TABLE mempool"))
        conn.execute(text("ALTER TABLE mempool_old RENAME TO mempool"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mempool_fee ON mempool(fee DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mempool_sender_nonce ON mempool(chain_id, sender, nonce)"))
