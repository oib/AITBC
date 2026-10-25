#!/usr/bin/env python3
"""Copy coordinator-api rows from SQLite into a PostgreSQL database.

PG-TARGET-1 stream 4 rewrite. The previous version dropped target tables
``CASCADE`` and hand-wrote a schema that diverged from the models (a ``user``
table that never existed, indexes on ``marketoffer``/``marketbid`` while the
real tables are ``marketplaceoffer``/``marketplacebid``, positional
``SELECT *`` copies into fixed INSERT lists). This script instead:

* builds the target schema with ``alembic upgrade head`` — the same
  migrations the service runs — never hand-written DDL;
* never issues ``DROP`` or ``CASCADE``; a target that already holds rows is
  refused unless ``--allow-nonempty`` is passed;
* copies table by table in foreign-key dependency order with *named*
  columns resolved per-table from the reflected target schema;
* treats ``--allow-nonempty`` as insert-missing-only: a row whose primary
  key already exists is skipped and counted, never updated, never deleted;
* is a **dry run by default** — it prints the plan and per-table counts and
  writes nothing; ``--execute`` performs the schema upgrade and the copy;
* verifies per-table row counts and a checksum over primary keys after the
  copy and exits non-zero on any mismatch.

The target database URL is only ever printed in
:func:`aitbc.database.target.redacted_url` form.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

_SCRIPT_DIR = Path(__file__).resolve().parent
_APP_ROOT = _SCRIPT_DIR.parent  # apps/coordinator-api
_REPO_ROOT = _APP_ROOT.parent.parent
for _p in (str(_REPO_ROOT), str(_APP_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from aitbc.constants import DATA_DIR  # noqa: E402
from aitbc.database.target import redacted_url, to_sync_url  # noqa: E402

# Tables that must never be copied: alembic's own bookkeeping (the target is
# stamped by ``upgrade head``) and SQLite internals.
_SKIP_TABLES = {"alembic_version"}
_SKIP_PREFIXES = ("sqlite_",)

DEFAULT_SOURCE = DATA_DIR / "data" / "coordinator.db"


class MigrationError(RuntimeError):
    """Fatal precondition or verification failure."""


# ---------------------------------------------------------------------------
# Source helpers


def _open_source(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise MigrationError(f"SQLite source database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _source_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [r[0] for r in rows if r[0] not in _SKIP_TABLES and not any(r[0].startswith(p) for p in _SKIP_PREFIXES)]


def _source_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def _source_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])  # nosec B608 — table names come from schema reflection, never user input


# ---------------------------------------------------------------------------
# Schema creation: alembic upgrade head, exactly as the service runs it


def _build_target_schema(target_url: str) -> None:
    """Run ``alembic upgrade head`` against the target database.

    Invoked in a subprocess so the coordinator's ``alembic/env.py`` resolves
    the URL itself (``DATABASE_URL`` override path) — identical to the
    documented operator command.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = target_url
    env.pop("SQLITE_URL", None)
    env["PYTHONPATH"] = f"{_APP_ROOT / 'src'}:{_REPO_ROOT}"
    env.setdefault("TEST_MODE", "true")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_APP_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        raise MigrationError(
            f"alembic upgrade head failed against the target database:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Value normalisation SQLite -> SQLAlchemy bind values


def _normalise(value, column: sa.Column):
    """Convert a raw sqlite3 value into something the target type accepts.

    Money columns stay exact: integers pass through untouched and any other
    number becomes ``Decimal(str(v))`` — never a float round trip.
    """
    if value is None:
        return None
    coltype = column.type
    if isinstance(coltype, sa.JSON) and isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    if isinstance(coltype, sa.Numeric) and not isinstance(coltype, sa.Boolean):
        return value if isinstance(value, int) else Decimal(str(value))
    if isinstance(coltype, sa.Boolean) and isinstance(value, int):
        return bool(value)
    if isinstance(coltype, sa.DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(coltype, sa.Date) and not isinstance(coltype, sa.DateTime) and isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(coltype, sa.Time) and isinstance(value, str):
        return time.fromisoformat(value)
    if isinstance(coltype, sa.LargeBinary) and isinstance(value, (str, bytearray, memoryview)):
        return bytes(value, "utf-8") if isinstance(value, str) else bytes(value)
    return value


# ---------------------------------------------------------------------------
# Verification helpers


def _canon_value(value) -> str:
    """Canonical string form for one primary-key element.

    SQLite hands back ints/floats/ISO strings while psycopg2 returns
    ``Decimal``/``datetime`` — the same logical key must compare equal on
    both sides, so each element is reduced to a canonical string.
    """
    if value is None:
        return "∅"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        return str(Decimal(str(value)))
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return value.hex  # undashed form matches SQLite's CHAR(32)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def _canon_pk(row) -> tuple:
    return tuple(_canon_value(v) for v in row)


def _pk_checksum(pks: set[tuple]) -> str:
    """Deterministic checksum over a set of canonical primary-key tuples."""
    digest = hashlib.sha256()
    for pk in sorted(pks):
        digest.update(repr(pk).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _pk_columns(table: sa.Table) -> list[str]:
    return [c.name for c in table.primary_key.columns]


def _fetch_target_pks(conn: sa.Connection, table: sa.Table) -> set[tuple]:
    """Primary keys present in the target, in canonical form."""
    cols = [table.c[name] for name in _pk_columns(table)]
    return {_canon_pk(row) for row in conn.execute(sa.select(*cols))}


# ---------------------------------------------------------------------------
# Copy plan and execution


def _plan_tables(source_conn: sqlite3.Connection, target_meta: sa.MetaData) -> list[tuple[str, sa.Table, list[str], int]]:
    """Resolve ``(source_name, target_table, shared_columns, source_count)``.

    Dependency order comes from ``MetaData.sorted_tables`` over the reflected
    target schema, filtered to tables that also exist in the SQLite source.
    Only named columns present on both sides are copied.
    """
    source_tables = set(_source_tables(source_conn))
    target_tables = {t.name: t for t in target_meta.sorted_tables}
    for name in sorted(source_tables - set(target_tables)):
        print(f"  ! source table {name!r} has no target table — skipped")
    # Iterate the reflected schema in foreign-key dependency order — parents
    # (users, tenants) are copied before their children (job, usage_records).
    plan: list[tuple[str, sa.Table, list[str], int]] = []
    for table in target_meta.sorted_tables:
        name = table.name
        if name not in source_tables:
            continue
        src_cols = set(_source_columns(source_conn, name))
        columns = [c.name for c in table.columns if c.name in src_cols]
        missing = [c.name for c in table.columns if c.name not in src_cols]
        if missing:
            print(f"  ! {name}: target columns absent from source (left at defaults): {missing}")
        if not _pk_columns(table):
            raise MigrationError(f"target table {name!r} has no primary key — refusing to copy")
        plan.append((name, table, columns, _source_count(source_conn, name)))
    return plan


def _copy_table(
    source_conn: sqlite3.Connection,
    target_conn: sa.Connection,
    table: sa.Table,
    columns: list[str],
    existing_pks: set[tuple],
    batch_size: int,
) -> tuple[int, int]:
    """Insert source rows missing from the target. Returns (inserted, skipped)."""
    pk_names = _pk_columns(table)
    pk_idx = [columns.index(c) for c in pk_names]
    col_objs = [table.c[c] for c in columns]
    inserted = 0
    skipped = 0
    batch: list[dict] = []
    cursor = source_conn.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in columns)} FROM "{table.name}"')  # nosec B608 — reflected column/table names only
    for row in cursor:
        pk = _canon_pk(row[i] for i in pk_idx)
        if pk in existing_pks:
            skipped += 1
            continue
        existing_pks.add(pk)  # guard against duplicate PKs inside the source
        batch.append({c.name: _normalise(v, c) for c, v in zip(col_objs, row, strict=False)})
        if len(batch) >= batch_size:
            target_conn.execute(table.insert(), batch)
            inserted += len(batch)
            batch = []
    if batch:
        target_conn.execute(table.insert(), batch)
        inserted += len(batch)
    return inserted, skipped


# ---------------------------------------------------------------------------
# CLI


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy the coordinator SQLite database into a PostgreSQL target. "
        "Dry-run by default; --execute performs the migration.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"SQLite database file (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="PostgreSQL SQLAlchemy URL for the target database "
        "(or set TARGET_DATABASE_URL / DATABASE_URL). Never printed unredacted.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run 'alembic upgrade head' and copy rows. Without this flag the script only prints what it would do.",
    )
    parser.add_argument(
        "--allow-nonempty",
        action="store_true",
        help="Permit a target that already contains rows. Insert-missing-only: "
        "existing primary keys are skipped and counted — never updated or deleted.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows per INSERT batch (default: 1000).",
    )
    return parser.parse_args(argv)


def _resolve_target(args: argparse.Namespace) -> str:
    url = args.target_url or os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise MigrationError("no target database URL: pass --target-url or set TARGET_DATABASE_URL")
    url = to_sync_url(url)
    if not url.startswith(("postgresql", "postgres")):
        raise MigrationError(f"target is not a PostgreSQL URL: {redacted_url(url)} — this script only migrates to PostgreSQL")
    return url


def _refuse_nonempty_target(engine, args) -> None:
    """Raise before the schema build when the target already holds rows.

    Pre-existing data must not be touched; migration seeds added during
    'upgrade head' are not pre-existing (they exist identically in the
    source and count as skips). ``--allow-nonempty`` disables the refusal.
    """
    inspector = sa.inspect(engine)
    preexisting: dict[str, int] = {}
    for tname in inspector.get_table_names():
        if tname in _SKIP_TABLES or any(tname.startswith(p) for p in _SKIP_PREFIXES):
            continue
        with engine.connect() as conn:
            count = int(conn.execute(sa.text(f'SELECT COUNT(*) FROM "{tname}"')).scalar_one())  # nosec B608 — reflected table names only
        if count:
            preexisting[tname] = count
    if preexisting and not args.allow_nonempty:
        raise MigrationError(
            "target database already holds rows — refusing to copy "
            "(re-run with --allow-nonempty for insert-missing-only): "
            + ", ".join(f"{n}={c}" for n, c in sorted(preexisting.items()))
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.batch_size < 1:
        raise MigrationError("--batch-size must be >= 1")
    target_url = _resolve_target(args)
    mode = "EXECUTE" if args.execute else "DRY-RUN"

    print("=" * 60)
    print("AITBC Coordinator SQLite -> PostgreSQL migration")
    print(f"mode        : {mode}")
    print(f"source      : {args.source}")
    print(f"target      : {redacted_url(target_url)}")
    print(f"nonempty    : {'insert-missing-only allowed' if args.allow_nonempty else 'refused'}")
    print("=" * 60)

    source_conn = _open_source(args.source)

    if not args.execute:
        # Dry run: touch nothing on the target. Report the plan only.
        print("\nDRY-RUN — no writes will be made.\n")
        print("plan:")
        print("  1. build the target schema via 'alembic upgrade head'")
        print(
            "  2. refuse to continue if the target already holds rows"
            + (" (waived: insert-missing-only)" if args.allow_nonempty else "")
        )
        print("  3. copy rows per table in dependency order, named columns only")
        print("  4. verify per-table row counts and a checksum over primary keys\n")
        for name in sorted(_source_tables(source_conn)):
            print(f"  {name:<55} {_source_count(source_conn, name):>10} source rows")
        print("\nRe-run with --execute to perform the migration.")
        return 0

    # -- execute ------------------------------------------------------------
    engine = sa.create_engine(target_url)
    try:
        _refuse_nonempty_target(engine, args)

        print("\nBuilding target schema via 'alembic upgrade head' ...")
        _build_target_schema(target_url)

        meta = sa.MetaData()
        meta.reflect(bind=engine)
        plan = _plan_tables(source_conn, meta)

        with engine.begin() as target_conn:
            # Baseline = every PK present right after the schema build
            # (pre-existing rows + migration seeds). Verification then requires
            # source ⊆ target ⊆ source ∪ baseline — no row may be lost and no
            # foreign row may appear.
            baseline_pks = {name: _fetch_target_pks(target_conn, t) for name, t, _, _ in plan}

            total_inserted = 0
            total_skipped = 0
            for name, table, columns, src_count in plan:
                inserted, skipped = _copy_table(
                    source_conn, target_conn, table, columns, set(baseline_pks[name]), args.batch_size
                )
                total_inserted += inserted
                total_skipped += skipped
                print(f"  {name:<55} src={src_count:<8} inserted={inserted:<8} skipped={skipped}")

            # Verification inside the same transaction: row counts and a
            # checksum over primary keys. Any mismatch raises before commit.
            print("\nverifying ...")
            failures: list[str] = []
            for name, table, _columns, _src_count in plan:
                tgt_pks = _fetch_target_pks(target_conn, table)
                src_pks = {
                    _canon_pk(r)
                    for r in source_conn.execute(
                        f'SELECT {", ".join(chr(34) + c + chr(34) for c in _pk_columns(table))} FROM "{name}"'
                    )  # nosec B608 — reflected names only
                }
                expected = src_pks | baseline_pks[name]
                if src_pks - tgt_pks:
                    failures.append(f"{name}: {len(src_pks - tgt_pks)} source primary keys missing from target")
                if tgt_pks != expected:
                    failures.append(
                        f"{name}: target row count {len(tgt_pks)} != expected {len(expected)} "
                        f"(source {len(src_pks)} + pre-existing {len(baseline_pks[name])})"
                    )
                elif _pk_checksum(tgt_pks) != _pk_checksum(expected):
                    failures.append(f"{name}: primary-key checksum mismatch")
            if failures:
                raise MigrationError("post-copy verification failed:\n  " + "\n  ".join(failures))

            print(f"\nOK — {total_inserted} rows inserted, {total_skipped} existing rows skipped.")
            print("All per-table counts and primary-key checksums verified.")
    finally:
        engine.dispose()
        source_conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
