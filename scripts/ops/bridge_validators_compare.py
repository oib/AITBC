#!/usr/bin/env python3
"""Compare the bridge_validators ACTIVE set across node chain.db files.

Read-only. Accepts one or more ``name:path`` arguments where ``path`` is a
sqlite chain.db (``.db``/anything else) or a JSON dump of rows. Prints only
addresses and counts — never public_key material or other columns. Exits 0
when every input's *active* address set is identical, 1 on DIFFER or error.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_SELECT = "SELECT address, is_active FROM bridge_validators"


def _rows_from_db(path: Path) -> list[tuple[str, int]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [(str(addr), int(flag)) for addr, flag in con.execute(_SELECT)]
    finally:
        con.close()


def _rows_from_json(path: Path) -> list[tuple[str, int]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [(str(r["address"]), int(r["is_active"])) for r in rows]


def load_rows(path: Path) -> list[tuple[str, int]]:
    if path.suffix == ".json":
        return _rows_from_json(path)
    return _rows_from_db(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+", metavar="NAME:PATH", help="per-host chain.db or JSON row dump")
    args = ap.parse_args(argv)

    sets: dict[str, frozenset[str]] = {}
    counts: dict[str, int] = {}
    for spec in args.inputs:
        name, _, raw = spec.partition(":")
        path = Path(raw)
        try:
            rows = load_rows(path)
        except Exception as exc:  # noqa: BLE001 - load failure reports ERROR, never tracebacks
            print(f"{name}: ERROR {exc.__class__.__name__}")
            return 1
        counts[name] = len(rows)
        sets[name] = frozenset(a.lower() for a, flag in rows if flag)
        act = ",".join(sorted(sets[name])) or "(none)"
        print(f"{name}: rows={counts[name]} active={len(sets[name])} [{act}]")

    verdict = len(set(sets.values())) <= 1
    print("ACTIVE SET:", "MATCH" if verdict else "DIFFER")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
