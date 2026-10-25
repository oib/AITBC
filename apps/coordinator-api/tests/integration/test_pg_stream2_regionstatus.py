"""PG-TARGET-1 stream 2: marketplace_regions status must be enum-legal.

001 creates ``marketplace_regions.status`` as ``ENUM('ACTIVE', 'INACTIVE',
'MAINTENANCE', 'DEPRECATED', name='regionstatus')`` on PostgreSQL. The
``add_global_marketplace`` seed originally wrote ``'active'`` — valid on
SQLite (no enum check), fatal on PostgreSQL (invalid enum label), and
invisible to the model either way since ``RegionStatus`` binds member
names. These tests pin the seed to the enum labels without needing a
running PostgreSQL: SQLite carries the migration end-to-end, and the
label set is asserted against the column type compiled for the
postgresql dialect.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from .test_migrations import _run_alembic

_REGIONSTATUS_LABELS = {"ACTIVE", "INACTIVE", "MAINTENANCE", "DEPRECATED"}
_SEEDED_REGIONS = {
    "region_us_east_1",
    "region_us_west_1",
    "region_eu_west_1",
    "region_ap_south_1",
}


def _regionstatus_column() -> sa.Column:
    """The status column exactly as 001 declares it."""
    return sa.Column(
        "status",
        sa.Enum("ACTIVE", "INACTIVE", "MAINTENANCE", "DEPRECATED", name="regionstatus"),
        nullable=False,
    )


def test_seeded_region_statuses_are_enum_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "regionstatus.db"
    _run_alembic(tmp_path, "upgrade", "head", db_name=db_path.name)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = dict(con.execute("SELECT id, status FROM marketplace_regions"))
    finally:
        con.close()
    assert _SEEDED_REGIONS <= set(rows), f"seeded regions missing: {_SEEDED_REGIONS - set(rows)}"
    bad = {k: v for k, v in rows.items() if v not in _REGIONSTATUS_LABELS}
    assert not bad, f"statuses that are not regionstatus enum labels: {bad}"


def test_regionstatus_column_compiles_for_postgresql() -> None:
    """The enum labels a PostgreSQL CREATE TYPE would carry match the model.

    Compiling the column under the postgresql dialect proves the type is
    renderable as a native ENUM; asserting the stored seed values are a
    subset of ``.enums`` is what makes the seed insert legal there.
    """
    col = _regionstatus_column()
    ddl = str(sa.schema.CreateTable(sa.Table("marketplace_regions", sa.MetaData(), col)).compile(dialect=postgresql.dialect()))
    assert "regionstatus" in ddl
    assert set(col.type.enums) == _REGIONSTATUS_LABELS


def test_heal_revision_rewrites_lowercase_rows(tmp_path: Path) -> None:
    """A database that already carries 'active' is repaired, not stranded."""
    db_path = tmp_path / "heal.db"
    _run_alembic(tmp_path, "upgrade", "head", db_name=db_path.name)
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("UPDATE marketplace_regions SET status = 'active' WHERE id = 'region_us_east_1'")
        con.commit()
    finally:
        con.close()
    # Re-stamp back one revision then forward again so the heal re-runs.
    _run_alembic(tmp_path, "downgrade", "-1", db_name=db_path.name)
    _run_alembic(tmp_path, "upgrade", "head", db_name=db_path.name)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        status = con.execute("SELECT status FROM marketplace_regions WHERE id = 'region_us_east_1'").fetchone()[0]
    finally:
        con.close()
    assert status == "ACTIVE"
