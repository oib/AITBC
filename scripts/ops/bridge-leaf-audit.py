#!/usr/bin/env python3
"""Read-only audit of bridge_state_root leaf provenance (V-4 measurement).

Today ``block.bridge_state_root`` is built from the *service-local*
``cross_chain_transfer`` table: for every sealed BRIDGE_LOCK transaction the
proposer looks up the local row and writes the leaf
``lock:<transfer_id>:<amount>:<target_chain>`` — or the degenerate
``lock:<tx_hash>:0:unknown`` when the row is missing
(``consensus/poa.py::_compute_bridge_state_root``). A node without the local
row derives a different root for the same sealed block.

V-4 proposes deriving the leaf entirely from the sealed transaction — the
``payload``, with the ``envelope`` fallback for the GAP-47 block-scoped rows
whose payload was stored empty. Before that change is designed further this
audit answers: *would a transaction-derived root already equal every sealed
header's bridge_state_root, and where do today's service-local leaves read
0:unknown?*

READ-ONLY BY CONSTRUCTION: the only connection opened is SQLite ``mode=ro``
plus ``PRAGMA query_only=ON``. ``immutable=1`` is deliberately absent so a
live database's WAL contents are honored instead of skipped. Output is
counts, verdicts and truncated hash references — never row contents,
recipients or addresses.

Usage (on a node, so ``aitbc_chain`` resolves):

    PYTHONPATH=/opt/aitbc/apps/blockchain-node/src \\
      venv/bin/python scripts/ops/bridge-leaf-audit.py --db /path/to/chain.db
    ... --json     machine-readable output
    ... --no-trie  leaf audit only (skip the MerklePatriciaTrie root rebuild;
                   for hosts/environments without the package importable)

Exit status: 0 = ran; 2 = usage error / unreadable database.
Verdicts are data, not exit codes.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
from typing import Any

UNKNOWN_LEAF_TEMPLATE = "lock:{tx_hash}:0:unknown"


def connect_ro(db_path: str) -> sqlite3.Connection:
    """The ONLY connection this program creates: mode=ro + query_only.

    Plain ``mode=ro`` (not ``immutable=1``) so the audit honors the WAL of a
    live database and sees rows the node just committed."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _as_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return val if isinstance(val, dict) else {}
    return {}


def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = source.get(key)
        if val is not None and val != "":
            return val
    return None


def current_leaf(tx_hash: str, record: tuple | None) -> tuple[str, str]:
    """Today's service-local leaf. record = (transfer_id, amount, target_chain)
    or None → the degenerate 0:unknown leaf."""
    if record is None:
        return UNKNOWN_LEAF_TEMPLATE.format(tx_hash=tx_hash), "missing-row"
    tid, amount, target = record
    return f"lock:{tid}:{amount}:{target}", "row"


def derived_leaf(tx_hash: str, payload: dict[str, Any], envelope: dict[str, Any]) -> tuple[str | None, str]:
    """V-4 leaf derived from the sealed transaction only.

    Preferred source is ``payload``; when it is empty (GAP-47 block-scoped
    rows) the signed ``envelope`` carries the same body. Returns
    ``(leaf, source)`` where source is payload / envelope / missing.
    """
    tid = _pick(payload, "transfer_id")
    amount = _pick(payload, "amount")
    target = _pick(payload, "target_chain")
    source = "payload"
    if tid is None or amount is None or target is None:
        tid = tid or _pick(envelope, "transfer_id")
        amount = amount or _pick(envelope, "amount")
        target = target or _pick(envelope, "target_chain")
        source = "envelope"
    if tid is None or amount is None or target is None:
        return None, "unreadable"
    return f"lock:{tid}:{amount}:{target}", source


def lock_class(der_src: str, height: int, boundary: int | None) -> str:
    """V-4 grandfathering classification for one sealed lock.

    ``boundary`` is the proposed activation height: at or above it every
    sealed BRIDGE_LOCK must carry derivable data (payload, or the GAP-47
    envelope fallback). Below it, an underivable lock is ``grandfathered`` —
    the sealed header root stands as-is and is never recomputed, because the
    legacy rows cannot be reconstructed deterministically. Above it an
    underivable lock is a ``missing_data`` defect: the seal path that wrote
    it dropped both payload fields and the envelope, which the activation
    guard must make impossible. With ``boundary=None`` the classification is
    descriptive only (``derivable``/``underivable``).
    """
    if boundary is None:
        return "underivable" if der_src == "unreadable" else "derivable"
    if der_src != "unreadable":
        return "derivable"
    return "grandfathered" if height < boundary else "missing_data"


GRANDFATHER_BOUNDARY = 30000


def _load_trie():
    try:
        from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie
    except ImportError:
        return None
    return MerklePatriciaTrie


def short_hash(tx_hash: str) -> str:
    """Truncated reference — no full 64-hex string is ever printed."""
    return f"{tx_hash[:10]}…{tx_hash[-4:]}" if len(tx_hash) > 16 else tx_hash


def audit(conn: sqlite3.Connection, *, use_trie: bool = True, boundary: int | None = None) -> dict[str, Any]:
    locks = conn.execute(
        """
        SELECT chain_id, tx_hash, block_height, payload, envelope
        FROM "transaction"
        WHERE type = 'BRIDGE_LOCK' AND block_height IS NOT NULL
        ORDER BY chain_id, block_height, tx_hash
        """
    ).fetchall()

    # Local transfer rows, keyed exactly the way consensus looks them up:
    # source_chain == tx.chain_id AND transfer_id == tx.tx_hash.
    transfer_rows = conn.execute("SELECT source_chain, transfer_id, amount, target_chain FROM cross_chain_transfer").fetchall()
    transfers = {(r[0], r[1]): (r[1], r[2], r[3]) for r in transfer_rows}

    block_roots = {
        (r[0], r[1]): r[2]
        for r in conn.execute("SELECT chain_id, height, bridge_state_root FROM block WHERE bridge_state_root IS NOT NULL")
    }

    result: dict[str, Any] = {
        "locks_sealed": len(locks),
        "current_leaf": {"row": 0, "missing-row": 0},
        "derived_leaf": {"payload": 0, "envelope": 0, "unreadable": 0},
        "leaves": {"agree": 0, "differ": 0, "differ_only_missing_row": 0, "underivable": 0},
        "lock_classes": {"derivable": 0, "grandfathered": 0, "missing_data": 0},
        "blocks": [],
        "root_verdicts": {
            "derived_matches_header": 0,
            "derived_mismatch": 0,
            "current_matches_header": 0,
            "current_mismatch": 0,
            "header_absent": 0,
        },
        "breaking_locks": [],
    }

    per_block: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for chain_id, tx_hash, height, payload_raw, envelope_raw in locks:
        payload = _as_json(payload_raw)
        envelope = _as_json(envelope_raw)
        cur, cur_src = current_leaf(tx_hash, transfers.get((chain_id, tx_hash)))
        der, der_src = derived_leaf(tx_hash, payload, envelope)
        cls = lock_class(der_src, height, boundary)
        result["current_leaf"][cur_src] += 1
        result["derived_leaf"][der_src] += 1
        if cls in result["lock_classes"]:
            result["lock_classes"][cls] += 1
        if der is None:
            result["leaves"]["underivable"] += 1
        elif der == cur:
            result["leaves"]["agree"] += 1
        else:
            result["leaves"]["differ"] += 1
            if cur_src == "missing-row":
                result["leaves"]["differ_only_missing_row"] += 1
        per_block.setdefault((chain_id, height), []).append(
            {"tx_hash": tx_hash, "cur": cur, "cur_src": cur_src, "der": der, "der_src": der_src, "class": cls}
        )

    trie_cls = _load_trie() if use_trie else None
    for (chain_id, height), txs in sorted(per_block.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        stored = block_roots.get((chain_id, height))
        entry: dict[str, Any] = {
            "chain_id": chain_id,
            "height": height,
            "locks": len(txs),
            "stored_root": "present" if stored else "absent",
        }
        if trie_cls is not None:
            _rebuild_block_roots(entry, txs, stored, trie_cls, result)
        result["blocks"].append(entry)

    result["trie_rebuilt"] = trie_cls is not None
    return result


def _rebuild_block_roots(
    entry: dict[str, Any],
    txs: list[dict[str, Any]],
    stored: Any,
    trie_cls: Any,
    result: dict[str, Any],
) -> None:
    """Rebuild both roots for one block, compare against the stored header
    value. Fills ``entry`` and updates ``result`` verdicts/breaking_locks."""
    cur_trie, der_trie = trie_cls(), trie_cls()
    for tx in txs:
        cur_trie.put(tx["tx_hash"].encode(), tx["cur"].encode())
        if tx["der"] is not None:
            der_trie.put(tx["tx_hash"].encode(), tx["der"].encode())
    cur_root = "0x" + cur_trie.get_root().hex()
    # A derived root is only defined when every leaf was derivable;
    # an underivable lock leaves the root undefined rather than
    # silently dropping the leaf.
    der_ok = all(tx["der"] is not None for tx in txs)
    der_root = "0x" + der_trie.get_root().hex() if der_ok else None
    entry["derived_root"] = der_root
    entry["current_root"] = cur_root
    if stored is None:
        result["root_verdicts"]["header_absent"] += 1
        return
    entry["stored_match"] = {
        "derived": (der_root == stored) if der_ok else None,
        "current": cur_root == stored,
    }
    if der_ok and der_root == stored:
        result["root_verdicts"]["derived_matches_header"] += 1
    else:
        result["root_verdicts"]["derived_mismatch"] += 1
        for tx in txs:
            if tx["der"] is None or tx["der"] != tx["cur"]:
                result["breaking_locks"].append(
                    {
                        "chain_id": entry["chain_id"],
                        "height": entry["height"],
                        "tx": short_hash(tx["tx_hash"]),
                        "derived_source": tx["der_src"],
                        "current_leaf_missing_row": tx["cur_src"] == "missing-row",
                    }
                )
    if cur_root == stored:
        result["root_verdicts"]["current_matches_header"] += 1
    else:
        result["root_verdicts"]["current_mismatch"] += 1


def head_height(conn: sqlite3.Connection) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    try:
        for (cid,) in conn.execute("SELECT DISTINCT chain_id FROM block ORDER BY chain_id"):
            h = conn.execute("SELECT MAX(height) FROM block WHERE chain_id = ?", (cid,)).fetchone()[0]
            out[cid] = h
    except sqlite3.Error:
        out["<unknown>"] = None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit bridge_state_root leaves vs sealed-tx derivation, read-only (V-4).")
    ap.add_argument("--db", required=True, help="path to chain.db")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--no-trie", action="store_true", help="leaf audit only; skip MerklePatriciaTrie root rebuild")
    ap.add_argument(
        "--boundary",
        type=int,
        default=GRANDFATHER_BOUNDARY,
        metavar="HEIGHT",
        help="activation height chosen by the operator (default %(default)s): classify each "
        "underivable lock as grandfathered (below) or missing_data defect (at/above) — the "
        "V-4 boundary rule; pass 0 to classify everything as missing_data",
    )
    args = ap.parse_args(argv)

    try:
        conn = connect_ro(args.db)
    except sqlite3.Error as e:
        print(f"cannot open {args.db} read-only: {e}", file=sys.stderr)
        return 2

    result = audit(conn, use_trie=not args.no_trie, boundary=args.boundary)
    result["head"] = head_height(conn)
    conn.close()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("connection: sqlite file:?mode=ro + PRAGMA query_only=ON (read-only, WAL-aware)")
    heads = ", ".join(f"{cid}@{h}" for cid, h in result["head"].items())
    print(f"head: {heads}")
    print(f"sealed BRIDGE_LOCKs: {result['locks_sealed']}")
    print(f"current leaf: row={result['current_leaf']['row']} missing-row(0:unknown)={result['current_leaf']['missing-row']}")
    print(
        f"derived leaf: payload={result['derived_leaf']['payload']} envelope={result['derived_leaf']['envelope']} unreadable={result['derived_leaf']['unreadable']}"
    )
    lv = result["leaves"]
    print(
        f"leaves: agree={lv['agree']} differ={lv['differ']} (of which current-is-missing-row={lv['differ_only_missing_row']}) underivable={lv['underivable']}"
    )
    if args.boundary is not None:
        lc = result["lock_classes"]
        print(
            f"boundary {args.boundary}: derivable={lc['derivable']} grandfathered={lc['grandfathered']} "
            f"missing_data(activation-blocking defect)={lc['missing_data']}"
        )
    if not result["trie_rebuilt"]:
        print("trie rebuild: SKIPPED (aitbc_chain not importable or --no-trie)")
    else:
        rv = result["root_verdicts"]
        print("per-block root verdicts (blocks containing locks):")
        for b in result["blocks"]:
            m = b.get("stored_match")
            verdict = f"stored:{b['stored_root']}"
            if m:
                verdict += f" derived={'MATCH' if m['derived'] else 'MISMATCH' if m['derived'] is False else 'undef'} current={'MATCH' if m['current'] else 'MISMATCH'}"
            print(f"  {b['chain_id']}@{b['height']:<8d} locks={b['locks']} {verdict}")
        print(
            f"root summary: derived_matches_header={rv['derived_matches_header']} derived_mismatch={rv['derived_mismatch']} "
            f"current_matches_header={rv['current_matches_header']} current_mismatch={rv['current_mismatch']} header_absent={rv['header_absent']}"
        )
        if result["breaking_locks"]:
            print("locks breaking derived==header (truncated refs):")
            for bl in result["breaking_locks"]:
                print(
                    f"  {bl['chain_id']}@{bl['height']} tx={bl['tx']} derived_src={bl['derived_source']} current_missing_row={bl['current_leaf_missing_row']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
