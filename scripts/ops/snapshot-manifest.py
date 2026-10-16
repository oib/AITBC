#!/usr/bin/env python3
"""Snapshot manifest generator (V-5, recommended "attested snapshot" option).

Prints a canonical JSON manifest describing a chain database: chain id, head
height and hash, the state root **recomputed with the node's own
``compute_state_root_full``** (state_root_utils.py — the same function the
proposer uses) compared against the head block's recorded root, row counts
for every table, and the A8 per-table digests (``side-root-probe.py``) for the
enumerated apply-written candidates plus node-local controls.

The manifest is a pure function of the database file: two runs over identical
bytes produce identical manifests (no timestamps, no host fields), so a
manifest produced anywhere can be compared or signed byte-for-byte.

Signing
-------
This tool **never signs** — it reads no key, wallet, keystore or password and
the manifest's ``signature`` field is emitted empty by construction. Signing
is a separate, deliberate operator step: pipe the JSON to whichever signing
tool the operator trusts, over exactly the bytes printed here. Keeping the
manifest free of volatile fields means the signature attests the content,
not the moment it was generated.

READ-ONLY BY CONSTRUCTION: the only connections opened are SQLite
``mode=ro`` plus ``PRAGMA query_only=ON`` (the SQLModel session
used for the state-root recompute is bound to the same read-only engine;
``immutable=1`` is deliberately absent so a live database's WAL is honored).
There is no write flag, no ATTACH, no temp copy.

Usage:

    PYTHONPATH=/opt/aitbc/apps/blockchain-node/src \\
      venv/bin/python scripts/ops/snapshot-manifest.py --db /path/to/chain.db
    ... --chain-id <id>   required only when the DB holds several chains
    ... --no-state-root   skip the recompute (e.g. aitbc_chain unavailable)

Exit status: 0 = manifest printed; 2 = usage error / unreadable database /
ambiguous chain. ``state_root.match`` is data, not an exit code.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
import urllib.parse
from typing import Any

MANIFEST_FORMAT = "aitbc-snapshot-manifest/v1"


def connect_ro(db_path: str) -> sqlite3.Connection:
    """The ONLY raw connection this program creates: mode=ro + query_only."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _load_side_root_probe():
    """Sibling script loaded by path — keeps this file runnable standalone."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("side_root_probe", os.path.join(here, "side-root-probe.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chain_ids(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT chain_id FROM block ORDER BY chain_id")]


def _head(conn: sqlite3.Connection, chain_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT height, hash, state_root FROM block WHERE chain_id = ? ORDER BY height DESC LIMIT 1",
        (chain_id,),
    ).fetchone()
    if row is None:
        return {"height": None, "hash": None, "state_root": None}
    return {"height": row[0], "hash": row[1], "state_root": row[2]}


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        # table names from sqlite_master
        counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]  # nosec
    return counts


def _recompute_state_root(db_path: str, chain_id: str) -> str | None:
    """Recompute the state root with the node's own compute_state_root_full,
    on a SQLModel session bound to a mode=ro engine (WAL-aware)."""
    try:
        from sqlalchemy import event
        from sqlmodel import Session, create_engine

        from aitbc_chain.state.state_root_utils import compute_state_root_full
    except ImportError:
        return None
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path))
    engine = create_engine(f"sqlite:///{uri}?uri=true&mode=ro")

    @event.listens_for(engine, "connect")
    def _query_only(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA query_only=ON")

    with Session(engine) as session:
        return compute_state_root_full(session, chain_id)


def build_manifest(conn: sqlite3.Connection, db_path: str, chain_id: str, *, with_state_root: bool = True) -> dict[str, Any]:
    head = _head(conn, chain_id)
    recomputed = _recompute_state_root(db_path, chain_id) if with_state_root else None
    recorded = head["state_root"]

    probe = _load_side_root_probe()
    digests: dict[str, Any] = {"candidates": {}, "controls": {}}
    for table in probe.CANDIDATE_TABLES:
        digests["candidates"][table] = probe.table_digest(conn, table)
    for table in probe.CONTROL_TABLES:
        digests["controls"][table] = probe.table_digest(conn, table)

    return {
        "format": MANIFEST_FORMAT,
        "source": {"db_file": os.path.basename(db_path)},
        "chain_id": chain_id,
        "head": {"height": head["height"], "hash": head["hash"]},
        "state_root": {
            "recorded": recorded,
            "recomputed": recomputed,
            "match": (recomputed is not None and recomputed == recorded),
            "skipped": recomputed is None,
        },
        "row_counts": _row_counts(conn),
        "table_digests": digests,
        "digest_convention": "sha256 over canonically-ordered type-tagged rows; created_at/updated_at excluded (side-root-probe.py)",
        "signature": "",
        "signature_note": "Unsigned by construction — this tool reads no key, wallet, keystore or password. Signing is a separate operator step over exactly these bytes.",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Emit a canonical snapshot manifest for a chain.db, read-only (V-5).")
    ap.add_argument("--db", required=True, help="path to chain.db")
    ap.add_argument("--chain-id", default=None, help="required when the DB holds several chains")
    ap.add_argument("--no-state-root", action="store_true", help="skip the root recompute")
    args = ap.parse_args(argv)

    try:
        conn = connect_ro(args.db)
    except sqlite3.Error as e:
        print(f"cannot open {args.db} read-only: {e}", file=sys.stderr)
        return 2

    chain_ids = _chain_ids(conn)
    chain_id = args.chain_id
    if chain_id is None:
        if len(chain_ids) != 1:
            print(
                f"database holds {len(chain_ids)} chains {chain_ids}; pass --chain-id",
                file=sys.stderr,
            )
            conn.close()
            return 2
        chain_id = chain_ids[0]
    elif chain_id not in chain_ids:
        print(f"chain '{chain_id}' not present ({chain_ids})", file=sys.stderr)
        conn.close()
        return 2

    manifest = build_manifest(conn, args.db, chain_id, with_state_root=not args.no_state_root)
    conn.close()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
