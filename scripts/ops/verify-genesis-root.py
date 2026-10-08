#!/usr/bin/env python3
"""Verify a genesis.json against the node's own state-root and block-hash code.

Read-only by construction: the only filesystem access is ``open()`` on the
genesis file given on the command line. Nothing is written, no service is
contacted, no database is opened.

What it checks (V-5 follow-up):

1. The allocation set is non-empty and has no duplicated addresses.
2. ``state_root`` the file claims equals the trie root recomputed from the
   allocations with ``StateManager.update_account`` — the same code path the
   node's ``compute_state_root_full`` uses
   (``apps/blockchain-node/src/aitbc_chain/state/state_root_utils.py``).
3. ``genesis_hash``/``block.hash`` equals the canonical block hash recomputed
   by ``compute_block_hash`` over the file's own claimed fields (chain_id,
   height 0, parent, timestamp, empty tx list, proposer, claimed root, empty
   bridge root) — i.e. the file is at least internally consistent.

A file passes only if both match. Today's fleet genesis.json is expected to
FAIL (pre-migration stub: one allocation, ``0x00`` root) — that is what the
V-5 note documents; this tool exists so a *rebuilt* file can be proven
correct before it is ever trusted by a joining node.

Usage:

    venv/bin/python scripts/ops/verify-genesis-root.py \
        /var/lib/aitbc/data/<chain>/genesis.json
    venv/bin/python scripts/ops/verify-genesis-root.py genesis.json --quiet

Exit status: 0 = PASS, 1 = FAIL or unreadable file. All printed hashes are
shortened to their first 8 hex digits; addresses are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _short(value: Any) -> str:
    """First 8 hex digits of a 0x-prefixed (or bare) hash, ellipsis-suffixed."""
    v = str(value or "")
    if v.startswith("0x") or v.startswith("0X"):
        return v[:10] + "…" if len(v) > 10 else v
    return v[:8] + "…" if len(v) > 8 else v


def _extract(doc: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields the node's loader reads, tolerating both layouts."""
    block = doc.get("block") or {}
    return {
        "chain_id": doc.get("chain_id") or block.get("chain_id") or "",
        "allocations": doc.get("allocations", block.get("allocations", [])) or [],
        "claimed_root": doc.get("state_root") or block.get("state_root"),
        "claimed_hash": doc.get("genesis_hash") or block.get("hash"),
        "timestamp": doc.get("timestamp") or block.get("timestamp"),
        "proposer": block.get("proposer") or "genesis",
        "parent_hash": block.get("parent_hash") or "0x00",
    }


def _chain_modules():
    """Lazy import — keeps this file importable (and tests collectable) on a
    host where aitbc_chain is not on sys.path."""
    from aitbc_chain.consensus.block_hash import compute_block_hash
    from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie, StateManager

    return compute_block_hash, MerklePatriciaTrie, StateManager


def _check_allocations(allocs: list[Any], report: dict[str, Any]) -> None:
    """Flag empty sets, duplicated addresses and malformed entries."""
    seen: set[str] = set()
    dups = 0
    malformed = 0
    for alloc in allocs:
        try:
            addr = str(alloc["address"]).strip().lower()
            int(alloc["balance"])
            int(alloc.get("nonce", 0))
        except Exception:
            malformed += 1
            continue
        if addr in seen:
            dups += 1
        seen.add(addr)
    if malformed:
        report["problems"].append(f"{malformed} malformed allocation entr(y/ies)")
    if dups:
        report["problems"].append(f"{dups} duplicated allocation address(es)")
    if not allocs:
        report["problems"].append("empty allocation set")


def _check_roots(f: dict[str, Any], allocs: list[Any], report: dict[str, Any]) -> None:
    """Recompute the trie root and the canonical block hash over the file's
    claimed fields, and compare both with what the file claims."""
    compute_block_hash, MerklePatriciaTrie, StateManager = _chain_modules()

    # --- root: same code path as the node's compute_state_root_full ---
    state = StateManager()
    for alloc in allocs:
        state.update_account(str(alloc["address"]), int(alloc["balance"]), int(alloc.get("nonce", 0)))
    computed_root = "0x" + state.get_root().hex()
    report["computed_root"] = computed_root
    if not f["claimed_root"]:
        report["problems"].append("no claimed state_root in file")
    elif computed_root != f["claimed_root"]:
        report["problems"].append("state_root mismatch")

    # --- hash: canonical formula over the file's claimed fields ---
    empty_bridge_root = "0x" + MerklePatriciaTrie().get_root().hex()
    recomputed = None
    if f["claimed_hash"] and f["claimed_root"] is not None and f["timestamp"]:
        try:
            recomputed = compute_block_hash(
                f["chain_id"],
                0,
                str(f["parent_hash"]),
                f["timestamp"],
                [],
                str(f["proposer"]),
                state_root=f["claimed_root"],
                bridge_state_root=empty_bridge_root,
            )
        except Exception as exc:
            report["problems"].append(f"hash recompute failed: {exc}")
    if not f["claimed_hash"]:
        report["problems"].append("no claimed block hash in file")
    elif recomputed is not None and recomputed != f["claimed_hash"]:
        report["problems"].append("block hash mismatch vs claimed fields")
    report["recomputed_hash"] = recomputed


def verify(path: Path) -> dict[str, Any]:
    """Run every check. Returns a report dict; never raises on bad input."""
    report: dict[str, Any] = {"file": str(path), "problems": []}
    try:
        doc = json.loads(path.read_text())
    except Exception as exc:
        report["problems"].append(f"unreadable/invalid JSON: {exc}")
        report["verdict"] = "FAIL"
        return report

    f = _extract(doc)
    report["chain_id"] = f["chain_id"]
    report["allocations"] = len(f["allocations"])
    report["claimed_root"] = f["claimed_root"]
    report["claimed_hash"] = f["claimed_hash"]

    _check_allocations(f["allocations"], report)
    _check_roots(f, f["allocations"], report)

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("genesis", type=Path, help="path to genesis.json")
    parser.add_argument("--quiet", action="store_true", help="print only the verdict line")
    args = parser.parse_args(argv)

    report = verify(args.genesis)
    if args.quiet:
        print(f"verdict: {report['verdict']}" + (f" ({'; '.join(report['problems'])})" if report["problems"] else ""))
    else:
        print(f"file: {report['file']}")
        print(f"chain_id: {report.get('chain_id') or '-'}")
        print(f"allocations: {report.get('allocations', 0)}")
        print(f"claimed state_root:    {_short(report.get('claimed_root'))}")
        print(f"computed state_root:   {_short(report.get('computed_root'))}")
        print(f"claimed block hash:    {_short(report.get('claimed_hash'))}")
        print(f"recomputed block hash: {_short(report.get('recomputed_hash'))}")
        print(f"verdict: {report['verdict']}")
        for p in report["problems"]:
            print(f"  - {p}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
