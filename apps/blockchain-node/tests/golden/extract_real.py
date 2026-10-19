"""Extract the real-history corpus from a chain.db snapshot.

Runs against a checksum-verified, read-only COPY on scratch — never a live
data directory. Produces three corpus artifacts:

- ``genesis-state.json`` — the snapshot's block 0 verbatim plus the genesis
  document's allocations and parameters, with the file checksums and the
  genesis-hash-vs-block-0 comparison recorded for provenance, plus the
  inferred ``bootstrap_accounts``: on this chain the genesis document is
  decorative (its block hash does not match sealed block 0 — the doc
  postdates a re-genesis), so the real initial account set is reconstructed
  as ``tip_balance - received + spent`` per account. Every account that
  ever received an off-ledger credit (direct row writes — service-account
  seeding, validator floats) shows up there; replaying on that bootstrap
  is verified per block against the sealed ``state_root``.
- ``stream-manifest.json`` — counts, checksums, and any empty block whose
  sealed state_root breaks the run (drift exceptions — normally none).
- ``stream/<height>.json`` — one file per *tx-bearing* block: the sealed
  block row plus its transaction rows in ``id`` order, in the same wire
  shape ``replay-chain.py``'s stub serves (``from``/``to`` renames,
  ``payload``/``envelope`` decoded). Sharded per block so no single file
  exceeds the repo's 1MB added-file gate and every vector stays
  attributable to one sealed block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso(value: Any) -> Any:
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _row_dump(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key, val in out.items():
        # block_metadata stays the raw stored string — the Block column is
        # TEXT and apply re-parses it; round-tripping keeps the bytes exact.
        if key in ("payload", "envelope"):
            if isinstance(val, str):
                try:
                    out[key] = json.loads(val)
                except (ValueError, TypeError):
                    pass
            elif val is None and key == "payload":
                out[key] = {}
        elif key.endswith("_at") or key == "timestamp":
            out[key] = _iso(val)
    return out


def _tx_wire(row: dict[str, Any]) -> dict[str, Any]:
    """The served-transaction shape: every stored column plus from/to."""
    out = dict(row)
    out["from"] = out.get("sender", "")
    out["to"] = out.get("recipient", "")
    return out


def _bootstrap_accounts(db: sqlite3.Connection, chain_id: str) -> list[dict[str, Any]]:
    """Infer the effective genesis account set from the sealed flow plus the
    tip account table (see ``extract``'s docstring for the why)."""
    tip_accounts = {
        str(r[0]): {"balance": int(r[1]), "nonce": int(r[2])}
        for r in db.execute(
            "SELECT address, balance, nonce FROM account WHERE chain_id = ?",
            (chain_id,),
        )
    }
    # Replay the sealed flow in apply order to get each address's peak
    # cumulative outflow — the bootstrap credit floor — and its confirmed
    # send count for nonce provenance.
    cumulative: dict[str, int] = {}
    peak: dict[str, int] = {}
    sent: dict[str, int] = {}
    flow_rows = db.execute(
        'SELECT sender, recipient, value, fee FROM "transaction" '
        "WHERE chain_id = ? AND status = 'confirmed' "
        "ORDER BY block_height, id",
        (chain_id,),
    )
    for sender, recipient, value, fee in flow_rows:
        amt = int(value or 0)
        cost = amt + int(fee or 0)
        # Sealed sender/recipient strings predate address canonicalization —
        # both "0x02B8…" and "0x02b8…" forms appear for the same account.
        if sender:
            sender = sender.lower()
            cumulative[sender] = cumulative.get(sender, 0) - cost
            sent[sender] = sent.get(sender, 0) + 1
            peak[sender] = max(peak.get(sender, 0), -cumulative[sender])
        if recipient:
            recipient = recipient.lower()
            cumulative[recipient] = cumulative.get(recipient, 0) + amt
            peak[recipient] = max(peak.get(recipient, 0), -cumulative[recipient])
    bootstrap_accounts = []
    tip_by_lower = {a.lower(): a for a in tip_accounts}
    # Union on the lowercased form: tip rows and flow strings disagree in
    # case on this chain — without the fold the same account is emitted
    # twice, once per case-variant.
    candidates = {a.lower() for a in tip_accounts} | set(sent) | set(peak)
    for addr in sorted(candidates):
        if not (addr.startswith("0x") and len(addr) == 42):
            # bridge_release/bridge_refund pseudo-senders carry ledger rows
            # but never an account row — seeding one would poison the root.
            continue
        tip = tip_accounts.get(tip_by_lower.get(addr, addr))
        # The cumulative column is (received - spent); off-ledger net is what
        # the tip holds beyond it. Senders missing an account row get 0.
        offchain_net = (tip["balance"] if tip else 0) - cumulative.get(addr, 0)
        bootstrap_balance = max(peak.get(addr, 0), offchain_net, 0)
        if bootstrap_balance == 0:
            continue
        bootstrap_accounts.append(
            {
                "address": tip_by_lower.get(addr, addr),
                "balance": bootstrap_balance,
                "nonce": 0,
                # Provenance: the tip-implied net credit — a bootstrap above
                # offchain_net means the account saw off-ledger *debits*
                # mid-history (its net hides the larger gross credit); an
                # unbooked nonce is a nonce gap not explainable by sealed
                # sends.
                "offchain_net": offchain_net,
                "unbooked_nonce": (tip["nonce"] - sent.get(addr, 0)) if tip else None,
            }
        )
    return bootstrap_accounts


def extract(snapshot: Path, genesis: Path, outdir: Path, chain_id: str | None = None) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    genesis = genesis.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(f"file:{snapshot}?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    try:
        if chain_id is None:
            chain_id = str(db.execute("SELECT chain_id FROM block WHERE height = 0 LIMIT 1").fetchone()[0])
        genesis_row = db.execute("SELECT * FROM block WHERE chain_id = ? AND height = 0", (chain_id,)).fetchone()
        if genesis_row is None:
            raise SystemExit(f"snapshot {snapshot} has no block 0 for chain {chain_id}")

        genesis_doc = json.loads(genesis.read_text())
        genesis_block_data = genesis_doc.get("block", {})
        genesis_doc_hash = genesis_doc.get("genesis_hash") or genesis_block_data.get("hash") or ""
        block0 = _row_dump(genesis_row)
        allocations = genesis_doc.get("allocations", genesis_block_data.get("allocations", []))
        parameters = genesis_doc.get("parameters", {})

        # The real initial account set: the doc's allocations only count when
        # the doc's hash matches sealed block 0 (this chain's doc postdates a
        # re-genesis — it describes nothing the chain actually ran). Off-ledger
        # credits (direct account-row writes) are inferred from the sealed
        # history itself: bootstrap balance is the LARGEST cumulative
        # (spent - received) the account ever ran, floored by the tip-implied
        # net credit — the minimum opening balance that lets every sealed send
        # apply. The flow set is unioned over both the account table and the
        # senders recorded in history, so an account whose row was deleted
        # off-ledger still gets a bootstrap.
        hash_match = bool(genesis_doc_hash) and genesis_doc_hash == block0.get("hash")
        bootstrap_accounts = _bootstrap_accounts(db, chain_id)

        genesis_state = {
            "source": {
                "chain_id": chain_id,
                "snapshot_sha256": _sha256_file(snapshot),
                "genesis_json_sha256": _sha256_file(genesis),
                "genesis_doc_hash": genesis_doc_hash,
                "block0_hash": block0.get("hash"),
                "genesis_hash_matches_block0": hash_match,
                "doc_allocations_applied": hash_match,
            },
            "block0": block0,
            "allocations": allocations,
            "parameters": parameters,
            "bootstrap_accounts": sorted(bootstrap_accounts, key=lambda a: a["address"].lower()),
        }
        (outdir / "genesis-state.json").write_text(json.dumps(genesis_state, sort_keys=True, indent=1) + "\n")

        tip = int(db.execute("SELECT MAX(height) FROM block WHERE chain_id = ?", (chain_id,)).fetchone()[0])
        tx_heights = {
            int(r[0])
            for r in db.execute(
                'SELECT DISTINCT block_height FROM "transaction" WHERE chain_id = ? AND block_height IS NOT NULL',
                (chain_id,),
            )
        }
        block_rows = db.execute("SELECT * FROM block WHERE chain_id = ? ORDER BY height", (chain_id,)).fetchall()

        n_empty = 0
        root_breaks: list[dict[str, Any]] = []
        prev_root: Any = None
        stream_dir = outdir / "stream"
        stream_dir.mkdir(exist_ok=True)
        stream_blocks: list[int] = []
        n_txs = 0
        for brow in block_rows:
            b = _row_dump(brow)
            height = int(b["height"])
            if height in tx_heights:
                tx_rows = db.execute(
                    'SELECT * FROM "transaction" WHERE chain_id = ? AND block_height = ? ORDER BY id',
                    (chain_id, height),
                ).fetchall()
                txs = [_tx_wire(_row_dump(t)) for t in tx_rows]
                n_txs += len(txs)
                (stream_dir / f"{height:08d}.json").write_text(
                    json.dumps({"height": height, "block": b, "txs": txs}, sort_keys=True) + "\n"
                )
                stream_blocks.append(height)
            else:
                n_empty += 1
                if prev_root is not None and b.get("state_root") != prev_root:
                    root_breaks.append({"height": height, "state_root": b.get("state_root"), "prev_root": prev_root})
            if b.get("state_root") is not None:
                prev_root = b["state_root"]

        manifest = {
            "kind": "stream-manifest",
            "chain_id": chain_id,
            "source_snapshot_sha256": genesis_state["source"]["snapshot_sha256"],
            "tip_height": tip,
            "tx_bearing_blocks": len(stream_blocks),
            "transactions": n_txs,
            "empty_blocks": n_empty,
            "empty_block_state_root_breaks": root_breaks,
        }
        (outdir / "stream-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=1) + "\n")

        return {
            "chain_id": chain_id,
            "tip_height": tip,
            "tx_bearing_blocks": len(stream_blocks),
            "transactions": n_txs,
            "empty_blocks": n_empty,
            "state_root_breaks": len(root_breaks),
            "genesis_hash_matches_block0": genesis_state["source"]["genesis_hash_matches_block0"],
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", required=True, type=Path, help="read-only chain.db copy on scratch")
    ap.add_argument("--genesis", required=True, type=Path, help="copy of the chain's genesis.json")
    ap.add_argument("--out", required=True, type=Path, help="cases directory to write")
    ap.add_argument("--chain-id", default=None, help="default: the chain_id of block 0")
    args = ap.parse_args(argv)
    summary = extract(args.snapshot, args.genesis, args.out, args.chain_id)
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
