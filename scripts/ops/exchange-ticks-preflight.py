#!/usr/bin/env python3
"""Read-only preflight for the exchange tick-column migration.

Simulates ``_migrate_add_tick_columns`` against an exchange database without
writing anything: reports row counts, values that are not exactly representable
at 8 decimal places (which would abort startup), and the tick ranges that would
result.

Usage:
    python scripts/ops/exchange-ticks-preflight.py [DB_PATH]

DB_PATH defaults to the exchange's configured location
(EXCHANGE_DATABASE_URL, else the DATA_DIR default). Point it at a *copy* of a
live database — the script opens read-only regardless.

Exit code: 0 if every value is representable, 1 otherwise.
"""

import os
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.exchange.simple_exchange.db import (  # noqa: E402
    TICK_DECIMAL_PLACES,
    _TICK_COLUMNS,
    get_db_path,
    to_ticks,
)


def preflight(db_path: str) -> int:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    failures: list[str] = []
    try:
        for table, columns in _TICK_COLUMNS.items():
            existing = {row[1]: row[2].upper() for row in conn.execute(f"PRAGMA table_info({table})")}
            if not existing:
                print(f"{table}: table absent — nothing to migrate")
                continue

            src_cols = list(columns)
            # CAST AS TEXT mirrors what the REAL->TEXT migration produces for
            # pre-B2 databases, so this previews values as the migration sees
            # them regardless of the column's current affinity.
            select_list = ", ".join(f"CAST({c} AS TEXT)" for c in src_cols)
            # table/columns come from the hardcoded _TICK_COLUMNS map
            rows = conn.execute(f"SELECT id, {select_list} FROM {table}").fetchall()  # nosec B608

            bad = 0
            tick_min = tick_max = None
            for row in rows:
                row_id = row[0]
                for i, src in enumerate(src_cols):
                    raw = row[1 + i]
                    try:
                        ticks = to_ticks(Decimal(str(raw)))
                    except (InvalidOperation, ValueError):
                        bad += 1
                        failures.append(f"{table}#{row_id}.{src} = {raw!r}")
                        continue
                    tick_min = ticks if tick_min is None else min(tick_min, ticks)
                    tick_max = ticks if tick_max is None else max(tick_max, ticks)

            tick_cols_present = [t for t in columns.values() if t in existing]
            print(
                f"{table}: {len(rows)} row(s), {bad} unrepresentable, "
                f"tick columns present: {tick_cols_present or 'none'}, "
                f"tick range: {tick_min}..{tick_max}"
                if rows
                else f"{table}: empty"
            )
    finally:
        conn.close()

    if failures:
        print(f"\n{len(failures)} value(s) exceed {TICK_DECIMAL_PLACES} decimal places or are invalid:")
        for line in failures[:50]:
            print(f"  {line}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")
        print("\ninit_db() would refuse to start the service on this database.")
        return 1
    print("\nAll values representable at 8 decimal places. Migration would succeed.")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else get_db_path()
    if not os.path.exists(path):
        print(f"database not found: {path}", file=sys.stderr)
        sys.exit(2)
    sys.exit(preflight(path))
