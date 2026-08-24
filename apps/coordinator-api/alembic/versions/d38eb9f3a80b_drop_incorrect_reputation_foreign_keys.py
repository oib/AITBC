"""Drop incorrect reputation foreign keys.

The reputation_* and community_feedback tables store agent_id values that
are miner / workflow identifiers (e.g. 'aitbc-miner-1'), while the declared
ForeignKeys point to agent_reputation.id ('rep_*') or ai_agent_workflows.id.
Those constraints were never enforced by SQLite in production, but they make
`PRAGMA foreign_key_check` fail and mislead readers about the actual schema.

The migration reads the existing CREATE TABLE SQL from sqlite_master, removes
the FOREIGN KEY clauses, recreates the table without them, and copies the data.

Revision ID: d38eb9f3a80b
Revises: a3e7c15b8d94
Create Date: 2026-08-23 00:00:00.000000
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "d38eb9f3a80b"
down_revision: str | None = "a3e7c15b8d94"
branch_labels: str | None = None
depends_on: str | None = None

TABLES = [
    "agent_reputation",
    "reputation_events",
    "community_feedback",
    "trust_score_calculations",
    "agent_economic_profiles",
]

# Match an inline FOREIGN KEY table-constraint clause, including trailing comma
# and whitespace.  This also covers multi-column FK declarations if any exist.
_FK_RE = re.compile(
    r"\s*,?\s*FOREIGN\s*KEY\s*\([^)]+\)\s*REFERENCES\s+[^\s(]+\s*\([^)]*\)",
    re.IGNORECASE | re.DOTALL,
)


def _recreate_without_fks(table_name: str, connection: sa.Connection) -> None:
    """Recreate a table without its ForeignKey constraints, preserving data and indexes."""
    # Fetch the original CREATE TABLE statement and index definitions.
    create_row = connection.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).fetchone()
    if create_row is None or create_row[0] is None:
        raise RuntimeError(f"Could not find CREATE TABLE SQL for {table_name}")
    create_sql = create_row[0]

    index_rows = connection.execute(
        sa.text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=:name"),
        {"name": table_name},
    ).fetchall()
    index_sqls = [row[1] for row in index_rows if row[1] is not None]

    # Remove FOREIGN KEY(...) REFERENCES ... clauses.  Because the SQLite
    # schema stored in sqlite_master places FK constraints as separate lines,
    # a line-oriented strip is sufficient and safer than full regex parsing.
    cleaned_lines = []
    for line in create_sql.splitlines():
        stripped = line.strip()
        if _FK_RE.fullmatch(stripped):
            continue
        if re.match(r"^FOREIGN\s+KEY\s*\(", stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    cleaned_sql = "\n".join(cleaned_lines)
    # If the removed FK was the last constraint, the previous item now has a
    # trailing comma before the closing ')' which is a syntax error in SQLite.
    cleaned_sql = re.sub(r",\s*\)", "\n)", cleaned_sql, count=1)

    # Rename existing table so the new table can use the original name.
    connection.execute(sa.text(f'ALTER TABLE "{table_name}" RENAME TO "{table_name}_old"'))

    # Drop the old indexes.  SQLite keeps index names when the table is renamed,
    # and they will be recreated on the new table with the same names.
    for name, _ in index_rows:
        connection.execute(sa.text(f'DROP INDEX IF EXISTS "{name}"'))

    # Create the cleaned table and copy the data.
    connection.execute(sa.text(cleaned_sql))
    connection.execute(sa.text(f'INSERT INTO "{table_name}" SELECT * FROM "{table_name}_old"'))

    # Recreate the indexes.
    for sql in index_sqls:
        connection.execute(sa.text(sql))

    # Drop the old table.
    connection.execute(sa.text(f'DROP TABLE "{table_name}_old"'))


def upgrade() -> None:
    if context.is_offline_mode():
        # Offline SQL generation has no live database to introspect, and the
        # current SQLModel definitions already create these tables without the
        # incorrect foreign keys, so there is nothing to emit here.
        return
    bind = op.get_bind()
    for table in TABLES:
        _recreate_without_fks(table, bind)


def downgrade() -> None:
    """Downgrade is not supported for this schema cleanup."""
    raise NotImplementedError("Downgrade not supported: it would re-create the incorrect FKs.")
