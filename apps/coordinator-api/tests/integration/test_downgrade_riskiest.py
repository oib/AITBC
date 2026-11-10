"""Spot-check pins for the riskiest coordinator-api downgrades (#1527).

``test_migrations.py::test_full_downgrade_roundtrip_sweep`` already walks every
revision one step down and back up (~9 min, marked slow). These three tests
pin the *behaviour* of the revisions the #1527 audit flagged, each on a
throwaway SQLite DB — they document downgrades that run but are lossy or
destructive by design, so a future "fix" that silently changes the loss
profile fails loudly here.

Downgrade catalog (SQLite, verified 2026-11):

- ``021f508dbce7`` (reconcile schema): upgrade() DROP TABLEs six legacy
  tables (settlements, staking_pool, regional_council, regional_proposal,
  staking_position + their indexes). downgrade() re-creates them **empty** —
  the downgrade runs clean but every row the upgrade dropped is gone for
  good. Destructive-by-design; tracked under #1526 (ALEMBIC-DROP-1) /
  #1527.
- ``f53990f9d6cc`` (energy floor columns): downgrade() drops six
  baseline-owned indexes (``ix_{job,gpu_bookings,gpu_registry}_{model,resource}_id``)
  so SQLite will allow the column drops, and never recreates them — the
  parent revision's schema is left permanently missing those indexes.
  Lossy drift; tracked in #1527 finding 3 and the sweep's ``_KNOWN_DRIFT``.
- ``1c58c844d95e`` (client_ref + client FKs): upgrade() copies
  ``client_id`` → ``client_ref`` and rewrites ``client_id`` to synthetic
  ``users.id`` UUIDs (inserting placeholder users rows). downgrade() drops
  the FK, the ``client_ref`` index and the ``client_ref`` column but never
  restores ``client_id`` from ``client_ref`` — the original caller
  reference survives nowhere. Lossy; #1527 finding 1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .test_migrations import _run_alembic, _version_num

_DROPPED_BY_021F = (
    "settlements",
    "staking_pool",
    "regional_council",
    "regional_proposal",
    "staking_position",
)

_F53990_BASELINE_INDEXES = (
    "ix_job_model_id",
    "ix_job_resource_id",
    "ix_gpu_bookings_model_id",
    "ix_gpu_bookings_resource_id",
    "ix_gpu_registry_model_id",
    "ix_gpu_registry_resource_id",
)


def _table_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def _index_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()


def _insert_minimal_job(db_path: Path, *, client_id: str = "user-abc") -> None:
    """Insert the smallest valid ``job`` row at the pre-1c58 schema.

    Column set is read from PRAGMA so the pin survives unrelated column
    additions; every NOT NULL column gets a type-appropriate dummy except
    ``client_id``, which carries the caller reference under test.
    """
    con = sqlite3.connect(db_path)
    try:
        cols = con.execute("PRAGMA table_info(job)").fetchall()
        names: list[str] = []
        values: list[object] = []
        for _cid, name, ctype, _notnull, _dflt, _pk in cols:
            if name in ("client_ref",):
                continue  # leave NULL — the upgrade backfills it from client_id
            names.append(name)
            if name == "id":
                values.append("j1")
            elif name == "client_id":
                values.append(client_id)
            elif "INT" in (ctype or "").upper():
                values.append(1)
            elif "BOOL" in (ctype or "").upper():
                values.append(0)
            elif "JSON" in (ctype or "").upper() or "NUMERIC" in (ctype or "").upper():
                values.append("{}" if "JSON" in (ctype or "").upper() else 1)
            elif "DATETIME" in (ctype or "").upper() or "DATE" in (ctype or "").upper():
                values.append("2026-01-01 00:00:00")
            else:
                values.append("x")
        con.execute(
            f"INSERT INTO job ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
            values,
        )
        con.commit()
    finally:
        con.close()


def _job_client_ids(db_path: Path) -> list[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return [r[0] for r in con.execute("SELECT client_id FROM job")]
    finally:
        con.close()


def test_downgrade_021f508dbce7_recreates_dropped_tables_empty(tmp_path: Path) -> None:
    """021f508dbce7's downgrade runs and rebuilds the six dropped tables —
    empty. The upgrade's DROP TABLE is unrecoverable by design (#1526)."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "021f508dbce7")
    # Its own upgrade dropped the legacy tables.
    assert not (_table_names(db_path) & set(_DROPPED_BY_021F))

    _run_alembic(tmp_path, "downgrade", "-1")
    assert _version_num(db_path) == "001_context_prefixes"
    present = _table_names(db_path) & set(_DROPPED_BY_021F)
    assert present == set(_DROPPED_BY_021F), f"downgrade did not recreate: {sorted(set(_DROPPED_BY_021F) - present)}"

    # Re-upgrade drops them again — the round-trip is stable but lossy.
    _run_alembic(tmp_path, "upgrade", "021f508dbce7")
    assert not (_table_names(db_path) & set(_DROPPED_BY_021F))


def test_downgrade_f53990f9d6cc_succeeds_but_loses_baseline_indexes(tmp_path: Path) -> None:
    """f53990f9d6cc's downgrade drops six baseline-owned indexes to unblock
    DROP COLUMN and never recreates them (#1527 finding 3)."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "f53990f9d6cc")
    before = _index_names(db_path)
    present_before = set(_F53990_BASELINE_INDEXES) & before
    assert present_before, "baseline indexes missing already at f53990f9d6cc — test premise broken"

    _run_alembic(tmp_path, "downgrade", "-1")
    assert _version_num(db_path) == "1c58c844d95e"

    after = _index_names(db_path)
    lost = set(_F53990_BASELINE_INDEXES) - after
    # Pin the loss exactly: every baseline index the downgrade touched must
    # be gone afterwards — nothing recreates them on this path.
    assert lost == set(_F53990_BASELINE_INDEXES) & before, f"unexpected index loss profile: lost={sorted(lost)}"


def test_downgrade_1c58c844d95e_loses_original_client_id(tmp_path: Path) -> None:
    """1c58c844d95e round-trip is lossy (#1527 finding 1): upgrade rewrites
    ``client_id`` to a synthetic users.id UUID and stashes the original in
    ``client_ref``; downgrade drops ``client_ref`` without restoring
    ``client_id`` — the caller reference is unrecoverable."""
    db_path = tmp_path / "test_migrations.db"
    _run_alembic(tmp_path, "upgrade", "5d8339a13a12")
    _insert_minimal_job(db_path, client_id="user-abc")

    # Runs 1c58c844d95e's upgrade (then f53990f9d6cc's).
    _run_alembic(tmp_path, "upgrade", "f53990f9d6cc")
    rewritten = _job_client_ids(db_path)
    assert rewritten and rewritten[0] != "user-abc", "upgrade did not rewrite client_id — premise broken"

    # f53990f9d6cc downgrade, then 1c58c844d95e downgrade.
    _run_alembic(tmp_path, "downgrade", "-1")
    _run_alembic(tmp_path, "downgrade", "-1")
    assert _version_num(db_path) == "5d8339a13a12"

    after = _job_client_ids(db_path)
    assert after == rewritten, f"expected the synthetic client_id to survive the downgrade (lossy, #1527), got {after}"
    assert "user-abc" not in after, "original client_id unexpectedly survived — update the #1527 pin"
