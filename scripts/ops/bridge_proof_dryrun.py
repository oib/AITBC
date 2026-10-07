#!/usr/bin/env python3
"""Read-only bridge threshold dry-run against a real chain.db (A36-3).

For each of the newest ``--tail`` blocks: builds the canonical 7-field
block-header message exactly as ``build_verification_message`` does,
recovers every signer from the stored ``signature`` plus the
``block_metadata.attestations`` entries, and runs ``check_threshold``
against three candidate validator sets at ``--threshold``:

  (a) the currently registered ACTIVE bridge_validators rows (latest epoch)
  (b) the planned pair (default: --pair defaults)
  (c) the four current consensus attesters (default: --consensus defaults)

Prints block heights, recovered signer addresses, and per-candidate
counts only — never signatures or keys. Exits 1 if case (c) meets the
threshold on NONE of the evaluated blocks.

The DB is opened SQLite mode=ro via URI — the file is never modified.

Usage (on a node, from the repo checkout):
    venv/bin/python scripts/ops/bridge_proof_dryrun.py \
        --db /var/lib/aitbc/data/<chain_id>/chain.db [--tail 5]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field

from aitbc.bridge.multisig import check_threshold, recover_all_signers
from aitbc.bridge.types import BridgeBlockHeader, ValidatorInfo, ValidatorSet
from aitbc.bridge.verification import build_verification_message

# Full 42-char addresses — membership matching is exact-address,
# case-insensitive; short prefixes never match.
DEFAULT_PAIR = [
    "0x2aD555A9e5208A6438b24FbdA4BC83c4c2453e64",
    "0x7dc101a892640bb3e7781d3b618b54cfdb2664a5",
]
DEFAULT_CONSENSUS = [
    "0x19f0730AB8CaF59D7A590bD8d34df6985e709684",
    "0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2",
    "0x5E8EA27121bF641f5f578DB097F201D19397F541",
    "0x2aD555A9e5208A6438b24FbdA4BC83c4c2453e64",
]


@dataclass
class BlockRow:
    height: int
    chain_id: str
    hash: str
    parent_hash: str
    proposer: str
    state_root: str | None
    bridge_state_root: str | None
    signature: str
    attestations: list[dict] = field(default_factory=list)

    def header_message(self) -> dict:
        """The canonical 7-field message — the same call the header verify
        path makes (bridge_validator.py:390)."""
        return build_verification_message(
            BridgeBlockHeader(
                chain_id=self.chain_id,
                height=self.height,
                hash=self.hash,
                parent_hash=self.parent_hash,
                proposer=self.proposer,
                state_root=self.state_root or "",
                bridge_state_root=self.bridge_state_root or "",
                signature=self.signature,
            )
        )


def _vset(members: list[str], chain_id: str, threshold: int) -> ValidatorSet:
    infos = [ValidatorInfo(address=a, public_key="", chain_id=chain_id, epoch=0, is_active=True) for a in members]
    return ValidatorSet(chain_id=chain_id, epoch=0, validators=infos, threshold=threshold, total=len(infos))


def open_ro(db_path: str) -> sqlite3.Connection:
    """Open the chain DB strictly read-only (SQLite URI mode=ro)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def recent_blocks(conn: sqlite3.Connection, tail: int) -> list[BlockRow]:
    rows = conn.execute(
        "SELECT height, chain_id, hash, parent_hash, proposer, state_root,"
        " bridge_state_root, signature, block_metadata"
        " FROM block ORDER BY height DESC LIMIT ?",
        (tail,),
    ).fetchall()
    blocks = []
    for r in rows:
        meta = json.loads(r["block_metadata"]) if r["block_metadata"] else {}
        blocks.append(
            BlockRow(
                height=r["height"],
                chain_id=r["chain_id"],
                hash=r["hash"],
                parent_hash=r["parent_hash"],
                proposer=r["proposer"],
                state_root=r["state_root"],
                bridge_state_root=r["bridge_state_root"],
                signature=r["signature"] or "",
                attestations=meta.get("attestations") or [],
            )
        )
    return blocks


def active_bridge_set(conn: sqlite3.Connection, chain_id: str, threshold: int) -> ValidatorSet:
    """Currently registered active set: latest epoch, is_active rows only."""
    row = conn.execute("SELECT MAX(epoch) AS e FROM bridge_validators WHERE chain_id = ?", (chain_id,)).fetchone()
    epoch = row["e"] if row and row["e"] is not None else 0
    members = [
        r["address"]
        for r in conn.execute(
            "SELECT address FROM bridge_validators WHERE chain_id = ? AND epoch = ? AND is_active = 1",
            (chain_id, epoch),
        )
    ]
    return _vset(members, chain_id, threshold)


def evaluate_block(block: BlockRow, sets: dict[str, ValidatorSet]) -> dict[str, tuple[bool, int]]:
    """Recover signers for one block; run check_threshold per candidate set."""
    message = block.header_message()
    sigs = [a.get("signature", "") for a in block.attestations if a.get("signature")]
    if block.signature and block.signature not in sigs:
        sigs.append(block.signature)
    signers = recover_all_signers(message, sigs)
    result = {}
    for name, vset in sets.items():
        meets, count, _ = check_threshold(signers, vset, vset.threshold)
        result[name] = (meets, count)
    result["signers"] = signers  # type: ignore[assignment]
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", required=True, help="chain.db path (opened mode=ro)")
    p.add_argument("--tail", type=int, default=5, help="blocks to evaluate")
    p.add_argument("--threshold", type=int, default=2)
    p.add_argument("--pair", default=",".join(DEFAULT_PAIR), help="candidate set (b)")
    p.add_argument("--consensus", default=",".join(DEFAULT_CONSENSUS), help="candidate set (c)")
    args = p.parse_args(argv)

    conn = open_ro(args.db)
    blocks = recent_blocks(conn, args.tail)
    if not blocks:
        print("no blocks found")
        return 1
    chain_id = blocks[0].chain_id

    sets = {
        "a_registered": active_bridge_set(conn, chain_id, args.threshold),
        "b_planned_pair": _vset([a.strip() for a in args.pair.split(",") if a.strip()], chain_id, args.threshold),
        "c_attesters": _vset(
            [a.strip() for a in args.consensus.split(",") if a.strip()],
            chain_id,
            args.threshold,
        ),
    }

    print(f"db={args.db} chain={chain_id} threshold={args.threshold}")
    for name, vset in sets.items():
        print(f"set {name}: {[v.address for v in vset.validators]}")
    print()

    c_ok_blocks = 0
    for block in blocks:
        res = evaluate_block(block, sets)
        signers = res.pop("signers")
        counts = {n: f"{c}/{len(sets[n].validators)}{'OK' if m else 'FAIL'}" for n, (m, c) in res.items()}
        print(f"height={block.height} attestations={len(block.attestations)} proposer_signed={bool(block.signature)}")
        print(f"  signers={sorted(signers)}")
        for n, txt in counts.items():
            print(f"  {n}: {txt}")
        if res["c_attesters"][0]:
            c_ok_blocks += 1
        print()

    print(f"blocks evaluated: {len(blocks)}; (c) met threshold on {c_ok_blocks}")
    return 0 if c_ok_blocks > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
