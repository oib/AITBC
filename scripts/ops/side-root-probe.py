#!/usr/bin/env python3
"""Read-only per-table state digests for a local chain.db (V-3 first step).

V-3 proposes committing a root over the *apply-written* side tables into the
block header (aux_state_root). Before anyone writes that code, this probe
answers the gating question: do those tables actually hold identical contents
on every host today? A table that diverges across the fleet would hard-fork
at the first committed block — committing it is only safe for tables whose
digest matches on every node at the same head height.

READ-ONLY BY CONSTRUCTION: the only connection this program opens is SQLite
``mode=ro&immutable=1`` plus ``PRAGMA query_only=ON``; there is no write flag,
no second connection, no ATTACH. Output is table name, row count and a short
digest — never row data, never an address.

Digest construction (deterministic across hosts):

- columns come from ``PRAGMA table_info``; locally-stamped volatile columns
  (``created_at``, ``updated_at`` — replay-chain.py's _VOLATILE_COLUMNS) are
  excluded from the digest and listed as ``-col`` markers instead;
- each kept cell is canonicalised by type (None/int/float/str/bytes) and rows
  are joined and sorted in Python, so digest equality depends only on logical
  content — never on rowid, storage order, or SQLite internals;
- digest = sha256(table_name + column list + sorted canonical rows), printed
  as the first 16 hex chars.

The ``account`` table is included as a canary: it is already committed via
``state_root``, so a fleet account mismatch would mean something deeper is
broken. Control tables are node-local by design (RPC/service bookkeeping or
the mempool) and are *expected* to differ — they prove the probe detects real
divergence.

Usage:

    venv/bin/python scripts/ops/side-root-probe.py --db /path/to/chain.db
    venv/bin/python scripts/ops/side-root-probe.py --db chain.db --json

Exit status: 0 = ran (digests are data, not a verdict), 2 = usage error /
unreadable database. Cross-host comparison is done by the operator from the
printed table — the probe never reaches another host's file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.parse
from typing import Any

# Apply-written state tables — written by StateTransition.apply_transaction
# and its state/* helpers, hence deterministic from sealed history on every
# node. Candidates for a committed side-table root (V-3). ``account`` is the
# canary: already committed via state_root, it must always agree.
CANDIDATE_TABLES: tuple[str, ...] = (
    "account",
    "bond",
    "chain_parameter",
    "chain_parameter_history",
    "edge_node_registration",
    "gpu_allocation",
    "gpu_registration",
    "ipfs_subscription",
    "liquidity_distribution",
    "liquidity_pool",
    "liquidity_stake",
    "receipt",
    "stake",
)

# Node-local tables — RPC/service bookkeeping, never written by consensus
# apply. Included as controls: divergence here is expected and proves the
# probe detects it (escrow rows materialise only where the RPC touched the
# job; mempool is transient by definition).
CONTROL_TABLES: tuple[str, ...] = (
    "bridge_block_header",
    "consensus_state",
    "cross_chain_transfer",
    "escrow",
    "governance_proposal",
    "governance_vote",
    "mempool",
)

# Columns stamped locally at write time (replay-chain.py::_VOLATILE_COLUMNS —
# the same convention): a value written from the local clock legitimately
# differs across hosts without the state being different. Excluded from the
# digest, reported by name so nothing hides silently.
VOLATILE_COLUMNS = frozenset({"created_at", "updated_at"})

# History/journal tables are deliberately not probed: block, transaction,
# receipt-adjacent journals (block_state_delta), mempool artefacts are either
# already bound by the block hash or per-block journals, not side state.
# sqlite_sequence likewise.

DIGEST_LEN = 16


def connect_ro(db_path: str) -> sqlite3.Connection:
    """The ONLY connection this program creates: mode=ro&immutable=1 + query_only."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _canonical_cell(value: Any) -> str:
    """One cell → a canonical string. Type-tagged so 1 != '1' != b'\\x01'."""
    if value is None:
        return "n:"
    if isinstance(value, bool):
        return "i:" + str(int(value))
    if isinstance(value, int):
        return "i:" + str(value)
    if isinstance(value, float):
        return "f:" + repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "b:" + bytes(value).hex()
    return "s:" + str(value)


def table_digest(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """Row count + digest over canonically ordered rows for one table.

    Returns a dict so the JSON and text outputs share one shape:
    ``{"rows": n, "digest": "…", "skipped": [volatile col names]}`` or
    ``{"status": "absent"}`` when the table does not exist in this database.
    """
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    if not cols:
        return {"status": "absent"}
    keep = [c for c in cols if c not in VOLATILE_COLUMNS]
    skipped = [c for c in cols if c in VOLATILE_COLUMNS]
    quoted = ", ".join(f'"{c}"' for c in keep)
    rows = conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()  # nosec B608 - quoted identifiers from PRAGMA table_info
    canonical = sorted("\x1f".join(_canonical_cell(v) for v in row) for row in rows)
    h = hashlib.sha256()
    h.update(table.encode())
    h.update(b"\x00")
    h.update(",".join(keep).encode())
    h.update(b"\x00")
    for row in canonical:
        h.update(row.encode())
        h.update(b"\x1e")
    return {"rows": len(rows), "digest": h.hexdigest()[:DIGEST_LEN], "skipped_cols": skipped}


def head_height(conn: sqlite3.Connection) -> dict[str, int | None]:
    """Max sealed block height per chain_id — digests only compare at equal
    heights, so the probe records the height it observed."""
    out: dict[str, int | None] = {}
    try:
        for (cid,) in conn.execute("SELECT DISTINCT chain_id FROM block ORDER BY chain_id"):
            h = conn.execute("SELECT MAX(height) FROM block WHERE chain_id = ?", (cid,)).fetchone()[0]
            out[cid] = h
    except sqlite3.Error:
        out["<unknown>"] = None
    return out


def collect(conn: sqlite3.Connection) -> dict[str, Any]:
    result: dict[str, Any] = {"head": head_height(conn), "candidates": {}, "controls": {}}
    for table in CANDIDATE_TABLES:
        result["candidates"][table] = table_digest(conn, table)
    for table in CONTROL_TABLES:
        result["controls"][table] = table_digest(conn, table)
    # Fleet fingerprint over candidates only: one line a human can eyeball
    # across five runs without diffing tables.
    h = hashlib.sha256()
    for table in sorted(result["candidates"]):
        entry = result["candidates"][table]
        h.update(table.encode())
        h.update(b"=")
        h.update((entry["digest"] if "digest" in entry else entry["status"]).encode())
        h.update(b";")
    result["candidate_fingerprint"] = h.hexdigest()[:DIGEST_LEN]
    return result


def _print_group(title: str, entries: dict[str, Any]) -> None:
    print(f"{title}:")
    for table, entry in entries.items():
        if entry.get("status") == "absent":
            print(f"  {table:28s}  ABSENT")
            continue
        skipped = "".join(f" -{c}" for c in entry["skipped_cols"]) if entry["skipped_cols"] else ""
        print(f"  {table:28s}  rows={entry['rows']:<7d} digest={entry['digest']}{skipped}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-table state digests over a chain.db, read-only (V-3 fleet probe).")
    ap.add_argument("--db", required=True, help="path to chain.db")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    try:
        conn = connect_ro(args.db)
    except sqlite3.Error as e:
        print(f"cannot open {args.db} read-only: {e}", file=sys.stderr)
        return 2

    result = collect(conn)
    conn.close()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("connection: sqlite file:?mode=ro&immutable=1 + PRAGMA query_only=ON (read-only by construction)")
    heads = ", ".join(f"{cid}@{h}" for cid, h in result["head"].items())
    print(f"head: {heads}")
    _print_group("candidate tables (apply-written; V-3 committable iff digests agree fleet-wide)", result["candidates"])
    _print_group("control tables (node-local; expected to differ)", result["controls"])
    print(f"candidate fingerprint: {result['candidate_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
