#!/usr/bin/env python3
"""Read-only per-table state digests for a local chain.db (V-3 first step).

V-3 proposes committing a root over the *apply-written* side tables into the
block header (aux_state_root). Before anyone writes that code, this probe
answers the gating question: do those tables actually hold identical contents
on every host today? A table that diverges across the fleet would hard-fork
at the first committed block — committing it is only safe for tables whose
digest matches on every node at the same head height.

READ-ONLY BY CONSTRUCTION: the only connection this program opens is SQLite
``mode=ro`` plus ``PRAGMA query_only=ON``; there is no write flag, no second
connection, no ATTACH. ``immutable=1`` is deliberately absent: a live
chain.db holds its newest pages in the WAL and immutable mode would skip
them, so the probe would digest a stale snapshot. Output is table name,
row count and a short digest — never row data, never an address.

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
import re
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

# --- V-3 activation rules (--canonical) --------------------------------------
#
# Operator decision 2026-10-12: the committed set is all 13 apply-written
# tables. The 10 whose raw digests already agree fleet-wide digest under
# the same rules unchanged; the 3 dual-writer tables require the
# canonicalization rules below (verified fleet-wide at height 44672 — all
# 13 give one digest per table on all five hosts).
RESTRICTED_TABLES: tuple[str, ...] = (
    "account",
    "bond",
    "chain_parameter",
    "chain_parameter_history",
    "edge_node_registration",
    "ipfs_subscription",
    "liquidity_distribution",
    "liquidity_pool",
    "liquidity_stake",
    "receipt",
)

# The 3 dual-writer tables (apply + RPC paths write them): their raw forms
# diverge only in locally-stamped columns/encodings, so their committed
# digests are computed under the canonicalization rules below.
CANONICALIZED_TABLES: tuple[str, ...] = (
    "gpu_allocation",
    "gpu_registration",
    "stake",
)


def committed_tables_for_version(block_version: int) -> tuple[str, ...]:
    """The committed set for a block version — mirror of
    state/side_root_shadow.committed_tables_for_version. v15
    (EDGE-REG-CONSENSUS-1) drops edge_node_registration, which is
    service-local (no apply writer or reader); the v14 set stays frozen for
    replay of already-sealed eras."""
    restricted = (
        RESTRICTED_TABLES if block_version < 15 else tuple(t for t in RESTRICTED_TABLES if t != "edge_node_registration")
    )
    return (*restricted, *CANONICALIZED_TABLES)


# Canonical rule 1: every column whose name ends in ``_at`` is a locally
# stamped timestamp (registered_at, allocated_at, completed_at, created_at,
# updated_at) — excluded, matching the operator's "*_at exclusions" decision.
def _is_local_stamp(col: str) -> bool:
    return col in VOLATILE_COLUMNS or col.endswith("_at")


# Canonical rule 1b (operator 2026-10-08, "normalize + exclude"): named
# columns holding node-local handles — generated by the RPC writer, never
# derivable from sealed history — are excluded per table. Live fact:
# gpu_allocation.allocation_id differs on every host.
CANONICAL_EXCLUDED_COLUMNS: dict[str, frozenset[str]] = {
    "gpu_allocation": frozenset({"allocation_id"}),
}


# Canonical rule 2: 0x-prefixed identifiers are EVM-style addresses; case is
# an encoding artifact (hub stores stake.address checksummed, followers
# lowercased). Lowercased before hashing. Timestamp text is normalized on
# all-zero fractional seconds — '…:00.000000' vs '…:00' is the same instant
# written by different SQLite writers (live fact: stake.locked_until on
# node0 vs node2/hub).
_STAMP_FRACTION_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.0{1,9}$")


def _canonical_cell_value(value: Any) -> Any:
    if isinstance(value, str):
        if value[:2].lower() == "0x":
            return value.lower()
        return _STAMP_FRACTION_RE.sub(r"\1", value)
    return value


# History/journal tables are deliberately not probed: block, transaction,
# receipt-adjacent journals (block_state_delta), mempool artefacts are either
# already bound by the block hash or per-block journals, not side state.
# sqlite_sequence likewise.

DIGEST_LEN = 16


def connect_ro(db_path: str) -> sqlite3.Connection:
    """The ONLY connection this program creates: mode=ro + query_only.

    Plain ``mode=ro`` (not ``immutable=1``) so the probe honors the WAL of a
    live database and reads the rows the node just committed."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
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


def table_digest(conn: sqlite3.Connection, table: str, *, canonical: bool = False) -> dict[str, Any]:
    """Row count + digest over canonically ordered rows for one table.

    With ``canonical=True`` the V-3 activation rules apply: every ``*_at``
    column is excluded (not just created_at/updated_at) and 0x-prefixed
    identifiers are lowercased. Returns a dict so the JSON and text outputs
    share one shape: ``{"rows": n, "digest": "…", "skipped": [col names]}``
    or ``{"status": "absent"}`` when the table does not exist.
    """
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    if not cols:
        return {"status": "absent"}
    excluded = CANONICAL_EXCLUDED_COLUMNS.get(table, frozenset()) if canonical else frozenset()
    drop = (lambda c: _is_local_stamp(c) or c in excluded) if canonical else lambda c: c in VOLATILE_COLUMNS
    keep = [c for c in cols if not drop(c)]
    skipped = [c for c in cols if drop(c)]
    quoted = ", ".join(f'"{c}"' for c in keep)
    # quoted identifiers from PRAGMA table_info
    rows = conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()  # nosec
    if canonical:
        rows = [tuple(_canonical_cell_value(v) for v in row) for row in rows]
    canonical_rows = sorted("\x1f".join(_canonical_cell(v) for v in row) for row in rows)
    h = hashlib.sha256()
    h.update(table.encode())
    h.update(b"\x00")
    h.update(",".join(keep).encode())
    h.update(b"\x00")
    for row in canonical_rows:
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


def collect(conn: sqlite3.Connection, *, canonical: bool = False, block_version: int = 14) -> dict[str, Any]:
    result: dict[str, Any] = {"head": head_height(conn), "candidates": {}, "controls": {}}
    for table in CANDIDATE_TABLES:
        result["candidates"][table] = table_digest(conn, table, canonical=canonical)
    if canonical:
        # V-3 committed set, versioned (v14 = 13 tables frozen for replay;
        # v15 = 12 without edge_node_registration). ``requires_rules`` names
        # the members whose committed digest is only defined under the
        # canonicalization rules.
        committed = committed_tables_for_version(block_version)
        result["committed_set"] = {t: result["candidates"].pop(t) for t in committed if t in result["candidates"]}
        result["requires_rules"] = list(CANONICALIZED_TABLES)
    for table in CONTROL_TABLES:
        result["controls"][table] = table_digest(conn, table)
    # Fleet fingerprint over the proposed committed set only: one line a
    # human can eyeball across five runs without diffing tables.
    h = hashlib.sha256()
    source = result.get("committed_set", result["candidates"])
    for table in sorted(source):
        entry = source[table]
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
    ap.add_argument(
        "--canonical",
        action="store_true",
        help="apply the V-3 activation rules: committed set = the era's apply-written tables, "
        "digested with *_at columns excluded, node-local handle columns excluded, "
        "0x identifiers lowercased, and timestamp text normalized",
    )
    ap.add_argument(
        "--block-version",
        type=int,
        default=14,
        help="block version the committed set is computed for (default 14 = the frozen "
        "13-table set; >=15 drops edge_node_registration — see EDGE-REG-CONSENSUS-1)",
    )
    args = ap.parse_args(argv)

    try:
        conn = connect_ro(args.db)
    except sqlite3.Error as e:
        print(f"cannot open {args.db} read-only: {e}", file=sys.stderr)
        return 2

    result = collect(conn, canonical=args.canonical, block_version=args.block_version)
    conn.close()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("connection: sqlite file:?mode=ro + PRAGMA query_only=ON (read-only, WAL-aware)")
    heads = ", ".join(f"{cid}@{h}" for cid, h in result["head"].items())
    print(f"head: {heads}")
    if args.canonical:
        _print_group(
            f"committed set ({len(result['committed_set'])} tables — block_version {args.block_version})",
            result["committed_set"],
        )
    else:
        _print_group("candidate tables (apply-written; V-3 committable iff digests agree fleet-wide)", result["candidates"])
    _print_group("control tables (node-local; expected to differ)", result["controls"])
    print(f"candidate fingerprint: {result['candidate_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
