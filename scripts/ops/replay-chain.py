#!/usr/bin/env python3
"""Replay a chain.db snapshot through the real block-import path.

This is the historical-compatibility check for consensus changes: it serves a
*copy* of a production chain database over a local stub RPC endpoint and runs
``ChainSync.bulk_import_from`` — the same pull-sync path a rebuilt follower,
new validator, or disaster-recovery resync would execute — into a fresh,
empty database. Every block goes through ``import_block`` → ``_append_block``
with state-root validation on, so a divergence shows up as the first height
whose replayed state no longer matches the recorded state root.

The snapshot is opened read-only (``mode=ro&immutable=1``) and is never
written to. The replay target is a scratch directory that is removed on
success unless ``--keep`` is given.

Usage (run on a dev node, e.g. node2 — never against a live DB):

    # Snapshot hub's DB, then replay it locally
    ssh hub 'sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
        ".backup /tmp/chain-snapshot.db"'
    scp hub:/tmp/chain-snapshot.db hub:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json /tmp/

    cd /opt/aitbc && source venv/bin/activate
    PYTHONPATH=apps/blockchain-node/src python scripts/ops/replay-chain.py \
        --snapshot /tmp/chain-snapshot.db \
        --genesis /tmp/genesis.json \
        --chain-id ait-hub.aitbc.bubuit.net \
        --env-file /etc/aitbc/aitbc-blockchain-node.env

    # Stop early or keep the rebuilt DB for inspection:
    python scripts/ops/replay-chain.py --snapshot ... --to-height 27000
    python scripts/ops/replay-chain.py --snapshot ... --keep --workdir /tmp/replay-target

Replay always starts at genesis: the snapshot holds only current state, so a
mid-chain start has no pre-state to verify roots against. ``--to-height``
shortens a run; every historical era before it still replays.

Exit status: 0 when the whole range replays hash/state-root identical,
1 when a block rejects or state diverges (the offending height, block hash,
expected vs replayed root, and the rejection reason are printed).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE lines into os.environ (without overwriting ambient vars)."""
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class _SnapshotSource:
    """Read-only view of a snapshot chain.db, served in the exact shape of
    /rpc/head and /rpc/blocks-range so ChainSync pulls it like a peer."""

    def __init__(self, db_path: str, chain_id: str) -> None:
        import threading

        self._chain_id = chain_id
        # The HTTP handler threads share this connection — read-only immutable
        # snapshot, serialized by the lock.
        self._db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def head(self) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT height, hash, timestamp, tx_count FROM block WHERE chain_id = ? ORDER BY height DESC LIMIT 1",
            (self._chain_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"snapshot has no blocks for chain {self._chain_id}")
        return {
            "height": row["height"],
            "hash": row["hash"],
            "timestamp": _iso(row["timestamp"]),
            "tx_count": row["tx_count"],
        }

    def tip_height(self) -> int:
        return int(self.head()["height"])

    def blocks_range(self, start: int, end: int) -> dict[str, Any]:
        block_rows = self._db.execute(
            "SELECT * FROM block WHERE chain_id = ? AND height >= ? AND height <= ? ORDER BY height",
            (self._chain_id, start, end),
        ).fetchall()
        tx_rows = self._db.execute(
            'SELECT * FROM "transaction" WHERE chain_id = ?'
            " AND block_height >= ? AND block_height <= ? ORDER BY block_height, id",
            (self._chain_id, start, end),
        ).fetchall()
        txs_by_height: dict[int, list[dict[str, Any]]] = {}
        for tx in tx_rows:
            t = _tx_dump(dict(tx))
            t["from"] = t.get("sender", "")
            t["to"] = t.get("recipient", "")
            txs_by_height.setdefault(int(tx["block_height"]), []).append(t)
        blocks = []
        for b in block_rows:
            blocks.append(
                {
                    "chain_id": b["chain_id"],
                    "height": b["height"],
                    "hash": b["hash"],
                    "parent_hash": b["parent_hash"],
                    "proposer": b["proposer"],
                    "timestamp": _iso(b["timestamp"]),
                    "tx_count": b["tx_count"],
                    "state_root": b["state_root"],
                    "bridge_state_root": b["bridge_state_root"],
                    "block_metadata": b["block_metadata"],
                    "signature": b["signature"],
                    "transactions": txs_by_height.get(int(b["height"]), []),
                }
            )
        return {"success": True, "blocks": blocks, "count": len(blocks)}

    def height_states(self, start: int, end: int) -> dict[int, tuple[str, str | None]]:
        """height -> (hash, state_root) for final verification."""
        rows = self._db.execute(
            "SELECT height, hash, state_root FROM block WHERE chain_id = ? AND height >= ? AND height <= ? ORDER BY height",
            (self._chain_id, start, end),
        ).fetchall()
        return {int(r["height"]): (r["hash"], r["state_root"]) for r in rows}


def _iso(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _tx_dump(row: dict[str, Any]) -> dict[str, Any]:
    """Mirror Transaction.model_dump() over the wire: JSON columns become
    dicts, datetimes become iso strings; everything else passes through."""
    out: dict[str, Any] = dict(row)
    for col in ("payload", "envelope"):
        val = out.get(col)
        if isinstance(val, str):
            try:
                out[col] = json.loads(val)
            except (ValueError, TypeError):
                out[col] = {}
        elif val is None:
            out[col] = {} if col == "payload" else None
    out["created_at"] = _iso(out.get("created_at"))
    return out


def _make_handler(source: _SnapshotSource) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                if parsed.path == "/rpc/head":
                    self._json(source.head())
                elif parsed.path == "/rpc/blocks-range":
                    start = int(qs.get("start", [0])[0])
                    end = int(qs.get("end", [start])[0])
                    self._json(source.blocks_range(start, end))
                else:
                    self._json({"detail": "not found"}, status=404)
            except Exception as exc:  # pragma: no cover - defensive
                self._json({"detail": str(exc)}, status=500)

        def _json(self, obj: Any, status: int = 200) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:  # silence request logs
            pass

    return Handler


def _seed_genesis(session: Any, chain_id: str, genesis_path: str, snapshot: _SnapshotSource) -> None:
    """Seed block 0 + allocation accounts + chain parameters.

    The block row comes from the SNAPSHOT verbatim, not genesis.json: the
    live fleet's genesis.json files are stale (they describe an abandoned
    genesis from before the 0x-address migration), while the snapshot's
    block 0 is ground truth for what the chain actually recorded. Allocations
    still come from genesis.json — they define the initial account set."""
    from aitbc_chain.base_models import Account, Block, ChainParameter, record_chain_parameter_history

    snap_genesis = snapshot.blocks_range(0, 0)["blocks"][0]
    data = json.loads(Path(genesis_path).read_text())
    block_data = data.get("block", {})
    genesis_hash = data.get("genesis_hash") or block_data.get("hash")
    if genesis_hash and genesis_hash != snap_genesis["hash"]:
        print(
            f"WARNING: genesis.json hash {genesis_hash} != snapshot block 0 "
            f"{snap_genesis['hash']} — using the snapshot row (stale genesis file?)",
            file=sys.stderr,
        )
    allocations = data.get("allocations", block_data.get("allocations", []))
    parameters = data.get("parameters", {})

    genesis = Block(
        chain_id=chain_id,
        height=0,
        hash=snap_genesis["hash"],
        parent_hash=snap_genesis["parent_hash"],
        proposer=snap_genesis["proposer"],
        timestamp=datetime.fromisoformat(snap_genesis["timestamp"]),
        tx_count=snap_genesis["tx_count"],
        state_root=snap_genesis["state_root"],
        bridge_state_root=snap_genesis["bridge_state_root"],
        block_metadata=snap_genesis["block_metadata"],
        signature=snap_genesis["signature"],
    )
    session.add(genesis)
    for alloc in allocations:
        session.add(
            Account(
                chain_id=chain_id,
                address=alloc["address"],
                balance=int(alloc["balance"]),
                nonce=int(alloc.get("nonce", 0)),
            )
        )
    for name, value in (parameters or {}).items():
        stored_value = "" if value is None else str(value)
        session.add(ChainParameter(chain_id=chain_id, parameter=str(name), value=stored_value, applied_height=0))
        record_chain_parameter_history(session, chain_id, str(name), stored_value, None, 0)
    session.commit()


async def _run(args: argparse.Namespace) -> int:
    chain_id = args.chain_id
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="aitbc-replay-"))
    workdir.mkdir(parents=True, exist_ok=True)

    # Node env file first (it may carry the version-height ladder, feature
    # flags, etc.); ambient env still wins over the file via _load_env_file's
    # no-clobber rule — invert that here: the file describes the node whose
    # chain is being replayed, so its values are the reference.
    if args.env_file:
        _load_env_file(args.env_file)

    # Bind the scratch target BEFORE aitbc_chain imports — settings capture
    # AITBC_DATA_DIR/CHAIN_ID at module import time. These must win over any
    # env-file values.
    os.environ["AITBC_DATA_DIR"] = str(workdir)
    os.environ["CHAIN_ID"] = chain_id
    # Replay must exercise the code paths a rebuild actually hits: state-root
    # checks on, parallel validation enabled (the fleet runs it). Only default
    # them on — an env-file/ambient value wins.
    os.environ.setdefault("SYNC_STATE_ROOT_VALIDATION_ENABLED", "true")
    os.environ.setdefault("PARALLEL_TX_VALIDATION", "true")

    # Consensus-auth knobs are era-dependent and cannot be expressed as one
    # static config for a full-history replay: the validator set rotated when
    # hub was promoted (pre-rotation attestations verify against keys that are
    # no longer in the set), and the attestation requirement activated
    # mid-history (blocks ~1-1000 carry none). What replay must verify is that
    # state transitions reproduce the recorded roots — proposer block
    # signatures still verify (every historical block is signed), while quorum
    # and schedule checks are disabled here.
    os.environ["MULTI_VALIDATOR_CONSENSUS_ENABLED"] = "false"
    os.environ["VALIDATOR_SET"] = ""
    os.environ["TRUSTED_PROPOSERS"] = ""
    os.environ["MULTI_VALIDATOR_MIN_ATTESTATIONS"] = "0"

    from aitbc_chain.config import settings
    from aitbc_chain.database import init_db, session_scope
    from aitbc_chain.sync import ChainSync

    if not settings.sync_state_root_validation_enabled:
        print("FATAL: sync_state_root_validation_enabled is off — replay would not check state roots", file=sys.stderr)
        return 1

    snapshot = _SnapshotSource(args.snapshot, chain_id)
    tip = snapshot.tip_height()
    start = 1
    end = args.to_height if args.to_height is not None else tip
    if start > end:
        print(f"nothing to replay: range {start}..{end} is empty (snapshot tip {tip})", file=sys.stderr)
        return 1

    init_db(chain_id)
    with session_scope(chain_id) as session:
        _seed_genesis(session, chain_id, args.genesis, snapshot)
    print(f"genesis seeded; replaying blocks {start}..{end} of snapshot tip {tip}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(snapshot))
    port = server.server_address[1]
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sync = ChainSync(
            session_factory=lambda: session_scope(chain_id),
            chain_id=chain_id,
            batch_size=args.batch_size,
            poll_interval=0.0,
        )
        try:
            imported = await sync.bulk_import_from(f"http://127.0.0.1:{port}")
        finally:
            await sync.close()
    finally:
        server.shutdown()

    # bulk_import_from returns the count of accepted blocks; it stops at the
    # first rejection, which is exactly the first divergence we want to report.
    expected = end - start + 1
    ok = _verify(args.snapshot, chain_id, workdir, start, end)
    print(f"imported={imported} expected={expected}")
    if imported != expected or not ok:
        print("REPLAY FAILED — see divergence above", file=sys.stderr)
        return 1
    print(f"REPLAY OK: blocks {start}..{end} hash/state-root identical ({expected} blocks)")
    if not args.keep and not args.workdir:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
    else:
        print(f"rebuilt DB kept at {workdir}/data/{chain_id}/chain.db")
    return 0


def _verify(snapshot_path: str, chain_id: str, workdir: Path, start: int, end: int) -> bool:
    """Compare every replayed block's hash+state_root against the snapshot."""
    src = sqlite3.connect(f"file:{snapshot_path}?mode=ro&immutable=1", uri=True)
    dst = sqlite3.connect(str(workdir / "data" / chain_id / "chain.db"))
    src_rows = {
        r[0]: (r[1], r[2])
        for r in src.execute(
            "SELECT height, hash, state_root FROM block WHERE chain_id=? AND height>=? AND height<=?",
            (chain_id, start, end),
        )
    }
    dst_rows = {
        r[0]: (r[1], r[2])
        for r in dst.execute(
            "SELECT height, hash, state_root FROM block WHERE chain_id=? AND height>=? AND height<=?",
            (chain_id, start, end),
        )
    }
    src.close()
    dst.close()
    first_bad: int | None = None
    for height in sorted(src_rows):
        got = dst_rows.get(height)
        if got is None:
            first_bad = height
            print(f"height {height}: MISSING in replay (expected hash {src_rows[height][0]})")
            break
        want_hash, want_root = src_rows[height]
        got_hash, got_root = got
        if got_hash != want_hash or got_root != want_root:
            first_bad = height
            print(f"height {height}: DIVERGED")
            print(f"  hash        want {want_hash} got {got_hash}")
            print(f"  state_root  want {want_root} got {got_root}")
            break
    if first_bad is not None:
        return False
    extra = [h for h in dst_rows if h not in src_rows]
    if extra:
        print(f"replay produced unexpected heights {sorted(extra)[:5]}")
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", required=True, help="Path to a COPY of chain.db (opened read-only)")
    parser.add_argument(
        "--genesis",
        help="genesis.json path (default: genesis.json next to the snapshot)",
    )
    parser.add_argument("--chain-id", default=os.getenv("CHAIN_ID", ""), help="Chain ID (default: $CHAIN_ID)")
    parser.add_argument("--env-file", help="Optional env file to source (e.g. the node's blockchain env)")
    parser.add_argument("--to-height", type=int, default=None, help="Last block to replay (default: snapshot tip)")
    parser.add_argument("--batch-size", type=int, default=500, help="Blocks per fetch batch (default 500)")
    parser.add_argument("--workdir", help="Scratch dir for the rebuilt DB (default: a temp dir)")
    parser.add_argument("--keep", action="store_true", help="Keep the rebuilt DB after the run")
    args = parser.parse_args()

    if not args.chain_id:
        print("FATAL: --chain-id or CHAIN_ID required", file=sys.stderr)
        sys.exit(2)
    snapshot = Path(args.snapshot)
    if not snapshot.exists():
        print(f"FATAL: snapshot not found: {snapshot}", file=sys.stderr)
        sys.exit(2)
    args.snapshot = str(snapshot.resolve())
    if not args.genesis:
        candidate = snapshot.parent / "genesis.json"
        if candidate.exists():
            args.genesis = str(candidate)
        else:
            print("FATAL: --genesis required (no genesis.json next to snapshot)", file=sys.stderr)
            sys.exit(2)

    import asyncio

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
