#!/usr/bin/env python3
"""Compare each host's bridge_validators active set against the consensus set.

Read-only. The active set is the latest-epoch is_active rows — the same rows
``load_validator_set(epoch=None)`` returns. A signature only counts toward
``bridge_multisig_threshold`` when its signer is both a bridge-set member and
a consensus attester (attestations are the only ``validator_signatures`` a
proof can carry). Prints addresses and counts only; exits 1 when any host
cannot meet the given threshold.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_SELECT = """
SELECT address, is_active FROM bridge_validators
WHERE epoch = (SELECT MAX(epoch) FROM bridge_validators)
"""


def _rows_from_db(path: Path) -> list[tuple[str, int]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [(str(a), int(f)) for a, f in con.execute(_SELECT)]
    finally:
        con.close()


def _rows_from_json(path: Path) -> list[tuple[str, int]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    # JSON dumps may carry every epoch — filter to the max like the SQL does.
    if not rows:
        return []
    max_epoch = max(int(r.get("epoch", 0)) for r in rows)
    return [(str(r["address"]), int(r["is_active"])) for r in rows if int(r.get("epoch", 0)) == max_epoch]


def load_rows(path: Path) -> list[tuple[str, int]]:
    if path.suffix == ".json":
        return _rows_from_json(path)
    return _rows_from_db(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+", metavar="NAME:PATH", help="per-host chain.db or JSON row dump")
    ap.add_argument("--validators", required=True, help="comma-separated consensus attester addresses")
    ap.add_argument("--threshold", type=int, required=True, help="bridge_multisig_threshold (M of N)")
    args = ap.parse_args(argv)

    consensus = {a.strip().lower() for a in args.validators.split(",") if a.strip()}
    rc = 0
    for spec in args.inputs:
        name, _, raw = spec.partition(":")
        try:
            rows = load_rows(Path(raw))
        except Exception as exc:
            print(f"{name}: ERROR {exc.__class__.__name__}")
            rc = 1
            continue
        active = {a.lower() for a, flag in rows if flag}
        possible = active & consensus
        verdict = (
            f"CAN MEET THRESHOLD {args.threshold}"
            if len(possible) >= args.threshold
            else f"CANNOT: only {len(possible)} of {len(active)} possible signers are attesters"
        )
        act = ",".join(sorted(active)) or "(none)"
        print(f"{name}: bridge_active={len(active)} [{act}] intersection={len(possible)} {verdict}")
        if len(possible) < args.threshold:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
