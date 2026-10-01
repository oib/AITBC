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

Checkpoint mode (--checkpoint DB):

    Genesis replay is the default, but it only works when the whole history
    replays cleanly. When the genesis era itself diverges (recorded roots
    that current code cannot reproduce), replay has to start from a
    *state-bearing checkpoint*: a second chain.db whose tip C sits below the
    snapshot tip — typically an older ``.backup`` retained from that era, or
    the kept output of an earlier replay run.

    The checkpoint file is copied into the replay target wholesale — the
    exact equivalent of a node that stopped at C and resumes syncing — so
    accounts, chain parameters, escrow/bridge rows and the full
    block/transaction history are all present as pre-state. Blocks 0..C are
    NOT re-executed.

    Before anything is imported the checkpoint is proven on three axes:

    1. lineage — the checkpoint head (C, hash) must equal the snapshot's
       block at height C (same chain, canonical head), and the snapshot's
       block C+1 must name it as parent;
    2. state — the checkpoint's own ``account`` table must recompute to the
       ``state_root`` recorded on block C (same input set as
       ``compute_state_root_full``); "state-bearing" is proved, not assumed;
    3. re-seed — after the copy and ``init_db``'s additive migrations, the
       target DB's recomputed root must still match (catches seeding-time
       mutations such as ensure_bond_accounts inserts).

    Any failed proof aborts before the first block is imported. Replay then
    runs C+1..end through the unchanged import path; ``--to-height`` caps
    the range as usual.

    Checkpoints ladder: replay A→B with ``--keep --workdir``, then feed the
    rebuilt DB as the checkpoint for B→tip. Producing a checkpoint at an
    *arbitrary* height from a tip snapshot alone is not supported — the
    checkpoint must be a real chain.db that stopped at that height
    (the per-block undo journal is not a general rewind mechanism).

    The stronger ladder step is ``--to-height B --compare-state-with
    checkpoint-B.db``: after the per-block root check passes, every
    non-history table of the rebuilt DB is compared wholesale against the
    next checkpoint — catching divergence in aux state (escrow, chain
    parameters, bridge rows, contracts) that the account-only state root
    never sees. Locally stamped columns (created_at/updated_at) and the
    replay-generated undo journal are excluded.

    Example:

        python scripts/ops/replay-chain.py \
            --snapshot /tmp/chain-snapshot.db \
            --checkpoint /tmp/chain-at-20000.db \
            --chain-id ait-hub.aitbc.bubuit.net \
            --env-file /etc/aitbc/aitbc-blockchain-node.env

    ``--genesis`` is not needed in checkpoint mode: genesis block, allocation
    accounts and chain parameters are already inside the checkpoint.

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
from typing import Any, NamedTuple
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
    /rpc/head and /rpc/blocks-range so ChainSync pulls it like a peer.

    ``cap_height`` bounds the view the stub reports: head() then names the
    block at the cap and blocks_range() refuses to serve beyond it, so a
    ``--to-height`` run really stops there instead of importing to the real
    tip and failing the expected-count check afterwards."""

    def __init__(self, db_path: str, chain_id: str, cap_height: int | None = None) -> None:
        import threading

        self._chain_id = chain_id
        self._cap_height = cap_height
        # The HTTP handler threads share this connection — read-only immutable
        # snapshot, serialized by the lock.
        self._db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _head_row(self, *, capped: bool) -> sqlite3.Row:
        sql = "SELECT height, hash, timestamp, tx_count FROM block WHERE chain_id = ?"
        params: list[Any] = [self._chain_id]
        if capped and self._cap_height is not None:
            sql += " AND height <= ?"
            params.append(self._cap_height)
        row = self._db.execute(sql + " ORDER BY height DESC LIMIT 1", params).fetchone()
        if row is None:
            raise RuntimeError(f"snapshot has no blocks for chain {self._chain_id}")
        return row

    def head(self) -> dict[str, Any]:
        row = self._head_row(capped=True)
        return {
            "height": row["height"],
            "hash": row["hash"],
            "timestamp": _iso(row["timestamp"]),
            "tx_count": row["tx_count"],
        }

    def tip_height(self) -> int:
        """The snapshot file's real tip — for messaging, not the capped view."""
        return int(self._head_row(capped=False)["height"])

    def blocks_range(self, start: int, end: int) -> dict[str, Any]:
        if self._cap_height is not None:
            end = min(end, self._cap_height)
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


class _Checkpoint(NamedTuple):
    """Head of a state-bearing checkpoint DB, before it seeds a replay."""

    height: int
    hash: str
    state_root: str | None
    accounts: int


def _read_checkpoint_head(path: str, chain_id: str) -> _Checkpoint | None:
    """Head block row + account count of a checkpoint DB (read-only).

    Returns None when the file holds no blocks for this chain."""
    db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        head = db.execute(
            "SELECT height, hash, state_root FROM block WHERE chain_id = ? ORDER BY height DESC LIMIT 1",
            (chain_id,),
        ).fetchone()
        if head is None:
            return None
        accounts = db.execute("SELECT COUNT(*) FROM account WHERE chain_id = ?", (chain_id,)).fetchone()[0]
    finally:
        db.close()
    return _Checkpoint(height=int(head[0]), hash=str(head[1]), state_root=head[2], accounts=int(accounts))


def _checkpoint_state_root(path: str, chain_id: str) -> str | None:
    """Recompute the state root over the checkpoint's account table.

    Feeds the exact same input set as ``compute_state_root_full`` — the
    proof that the file is genuinely state-bearing — without opening a
    Session against it."""
    from aitbc_chain.base_models import Account
    from aitbc_chain.state.merkle_patricia_trie import StateManager

    db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        rows = db.execute("SELECT address, balance, nonce FROM account WHERE chain_id = ?", (chain_id,)).fetchall()
    finally:
        db.close()
    if not rows:
        return None
    accounts = {
        address: Account(chain_id=chain_id, address=address, balance=balance, nonce=nonce) for address, balance, nonce in rows
    }
    return "0x" + StateManager().compute_state_root(accounts).hex()


def _validate_checkpoint(path: str, chain_id: str, snapshot: _SnapshotSource, end: int) -> _Checkpoint | None:
    """Prove the checkpoint before it is allowed to seed a replay.

    Three proofs, all abort-before-import: lineage against the snapshot
    (head hash at C, and C+1 naming it as parent), then the state-bearing
    proof (the checkpoint's own account table must recompute to the
    state_root recorded on block C). Prints a FATAL line and returns None
    on any failed proof."""
    ckpt = _read_checkpoint_head(path, chain_id)
    if ckpt is None:
        print(f"FATAL: checkpoint {path} has no blocks for chain {chain_id}", file=sys.stderr)
        return None
    if ckpt.height >= end:
        print(
            f"FATAL: checkpoint tip {ckpt.height} leaves nothing to replay "
            f"(replay end {end}) — pass a checkpoint below the replay range",
            file=sys.stderr,
        )
        return None
    snap_c = snapshot.blocks_range(ckpt.height, ckpt.height)["blocks"]
    if not snap_c:
        print(f"FATAL: snapshot has no block at checkpoint height {ckpt.height}", file=sys.stderr)
        return None
    if snap_c[0]["hash"] != ckpt.hash:
        print(
            f"FATAL: checkpoint head hash {ckpt.hash} != snapshot block "
            f"{ckpt.height} hash {snap_c[0]['hash']} — checkpoint is not on this chain",
            file=sys.stderr,
        )
        return None
    snap_next = snapshot.blocks_range(ckpt.height + 1, ckpt.height + 1)["blocks"]
    if snap_next and snap_next[0]["parent_hash"] != ckpt.hash:
        print(
            f"FATAL: snapshot block {ckpt.height + 1} has parent "
            f"{snap_next[0]['parent_hash']}, not checkpoint head {ckpt.hash} — "
            "checkpoint sits on a different fork",
            file=sys.stderr,
        )
        return None
    if not ckpt.state_root:
        print(f"FATAL: checkpoint block {ckpt.height} carries no recorded state_root", file=sys.stderr)
        return None
    if ckpt.accounts == 0:
        print("FATAL: checkpoint carries no account rows — not state-bearing", file=sys.stderr)
        return None
    computed = _checkpoint_state_root(path, chain_id)
    if computed is None or computed.lower() != ckpt.state_root.lower():
        print(
            f"FATAL: checkpoint state does not reproduce the recorded state root at height "
            f"{ckpt.height} — want {ckpt.state_root}, recomputed {computed} "
            f"over {ckpt.accounts} accounts; the file is not a valid state-bearing checkpoint",
            file=sys.stderr,
        )
        return None
    print(
        f"checkpoint verified: height {ckpt.height}, hash {ckpt.hash}, "
        f"{ckpt.accounts} accounts recompute to recorded state_root {ckpt.state_root}"
    )
    return ckpt


def _copy_checkpoint(checkpoint_path: str, workdir: Path, chain_id: str) -> Path:
    """Seed the replay target with the checkpoint DB, wholesale.

    The copy lands at the path init_db will open, so replaying from C+1 is
    the exact equivalent of a node that stopped at C resuming sync: accounts,
    chain parameters, escrow/bridge rows and the full block/transaction
    history are all present as pre-state."""
    import shutil

    target = workdir / "data" / chain_id / "chain.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(checkpoint_path, target)
    return target


_HISTORY_TABLES = {
    # Verified per-height by _verify (block hash + state_root), or replay-
    # generated bookkeeping whose contents embed record-time values
    # (block_state_delta's before_json carries pre-image timestamps).
    "block",
    "transaction",
    "receipt",
    "block_state_delta",
    "mempool",
    "sqlite_sequence",
}
# Columns whose values are stamped locally at apply time; they differ between
# the recording run and any replay without the state being wrong.
_VOLATILE_COLUMNS = {"created_at", "updated_at"}


def _table_rows(db: sqlite3.Connection, table: str, chain_id: str) -> list[tuple[Any, ...]]:
    """Deterministic content dump: volatile columns dropped, rows sorted by
    every kept column so equal state compares equal regardless of rowid."""
    cols = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
    keep = [c for c in cols if c not in _VOLATILE_COLUMNS]
    quoted = ", ".join(f'"{c}"' for c in keep)
    sql = f'SELECT {quoted} FROM "{table}"'  # nosec B608 - quoted identifiers from sqlite_master/PRAGMA, values bound
    params: tuple[Any, ...] = ()
    if "chain_id" in cols:
        sql += " WHERE chain_id = ?"
        params = (chain_id,)
    sql += f" ORDER BY {quoted}"
    return db.execute(sql, params).fetchall()


def _compare_state(compare_path: str, target_db: Path, chain_id: str, end: int) -> bool:
    """Wholesale state comparison: every non-history table of the rebuilt DB
    against a second checkpoint DB. This is the ladder's stronger check —
    the per-block state_root only covers ``account``, while aux tables
    (escrow, chain_parameter, bridge state, contracts, stakes, …) are
    consensus state that would diverge silently without this.

    The compare DB's tip must equal the replay end height; a different tip
    makes the comparison meaningless by construction."""
    head = _read_checkpoint_head(compare_path, chain_id)
    if head is None:
        print(f"FATAL: compare target {compare_path} has no blocks for chain {chain_id}", file=sys.stderr)
        return False
    if head.height != end:
        print(
            f"FATAL: compare target tip {head.height} != replay end {end} — "
            "wholesale state compare requires the checkpoint at exactly the replay end",
            file=sys.stderr,
        )
        return False

    src = sqlite3.connect(f"file:{compare_path}?mode=ro&immutable=1", uri=True)
    dst = sqlite3.connect(str(target_db))
    try:
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")} | {
            r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        tables -= _HISTORY_TABLES
        ok = True
        compared = 0
        for table in sorted(tables):
            src_rows = _table_rows(src, table, chain_id)
            dst_rows = _table_rows(dst, table, chain_id)
            if src_rows == dst_rows:
                compared += 1
                continue
            ok = False
            from collections import Counter

            missing = list((Counter(src_rows) - Counter(dst_rows)).elements())
            extra = list((Counter(dst_rows) - Counter(src_rows)).elements())
            print(
                f"state table {table}: DIVERGED — checkpoint has {len(src_rows)} rows, "
                f"replay has {len(dst_rows)} ({len(missing)} missing, {len(extra)} extra)"
            )
            for row in missing[:3]:
                print(f"  want {row}")
            for row in extra[:3]:
                print(f"  got  {row}")
        if ok:
            print(f"STATE COMPARE OK: {compared} non-history tables identical to checkpoint at height {end}")
        return ok
    finally:
        src.close()
        dst.close()


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

    snapshot = _SnapshotSource(args.snapshot, chain_id, cap_height=args.to_height)
    tip = snapshot.tip_height()
    end = min(args.to_height, tip) if args.to_height is not None else tip

    # Checkpoint mode: prove the state-bearing checkpoint, seed the target
    # with its whole DB, then replay from its tip + 1 instead of genesis.
    ckpt = None
    if args.checkpoint:
        ckpt = _validate_checkpoint(args.checkpoint, chain_id, snapshot, end)
        if ckpt is None:
            return 1
    start = ckpt.height + 1 if ckpt is not None else 1
    if start > end:
        print(f"nothing to replay: range {start}..{end} is empty (snapshot tip {tip})", file=sys.stderr)
        return 1

    if ckpt is not None:
        _copy_checkpoint(args.checkpoint, workdir, chain_id)
    init_db(chain_id)
    with session_scope(chain_id) as session:
        if ckpt is not None:
            # Re-seed proof: init_db's additive migrations and helpers (e.g.
            # ensure_bond_accounts) may have touched the account table; the
            # seeded state must still reproduce block C's recorded root.
            from aitbc_chain.state.state_root_utils import compute_state_root_full

            seeded_root = compute_state_root_full(session, chain_id)
            if seeded_root is None or seeded_root.lower() != (ckpt.state_root or "").lower():
                print(
                    f"FATAL: seeded target root {seeded_root} != checkpoint root {ckpt.state_root} — "
                    "seeding mutated the account set; refusing to replay from unverified pre-state",
                    file=sys.stderr,
                )
                return 1
        else:
            _seed_genesis(session, chain_id, args.genesis, snapshot)
    origin = f"checkpoint height {ckpt.height}" if ckpt is not None else "genesis"
    print(f"seeded from {origin}; replaying blocks {start}..{end} of snapshot tip {tip}")

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
    if args.compare_state_with:
        # Ladder layer 2: wholesale state comparison against the checkpoint at
        # the replay end — covers aux tables the account-only state root misses.
        if not _compare_state(args.compare_state_with, workdir / "data" / chain_id / "chain.db", chain_id, end):
            return 1
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", required=True, help="Path to a COPY of chain.db (opened read-only)")
    parser.add_argument(
        "--genesis",
        help="genesis.json path (default: genesis.json next to the snapshot; unused with --checkpoint)",
    )
    parser.add_argument(
        "--checkpoint",
        metavar="DB",
        help="state-bearing chain.db whose tip C seeds the target; replay starts at C+1 "
        "instead of genesis (see module docstring for the pre-import proofs)",
    )
    parser.add_argument("--chain-id", default=os.getenv("CHAIN_ID", ""), help="Chain ID (default: $CHAIN_ID)")
    parser.add_argument("--env-file", help="Optional env file to source (e.g. the node's blockchain env)")
    parser.add_argument("--to-height", type=int, default=None, help="Last block to replay (default: snapshot tip)")
    parser.add_argument(
        "--compare-state-with",
        metavar="DB",
        help="after a successful replay, wholesale-compare every non-history state table "
        "against this chain.db — its tip must equal the replay end height "
        "(the checkpoint-to-checkpoint check; pair with --to-height)",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Blocks per fetch batch (default 500)")
    parser.add_argument("--workdir", help="Scratch dir for the rebuilt DB (default: a temp dir)")
    parser.add_argument("--keep", action="store_true", help="Keep the rebuilt DB after the run")
    args = parser.parse_args(argv)

    if not args.chain_id:
        parser.error("--chain-id or CHAIN_ID required")
    snapshot = Path(args.snapshot)
    if not snapshot.exists():
        parser.error(f"snapshot not found: {snapshot}")
    args.snapshot = str(snapshot.resolve())
    if args.checkpoint:
        checkpoint = Path(args.checkpoint)
        if not checkpoint.exists():
            parser.error(f"checkpoint not found: {checkpoint}")
        args.checkpoint = str(checkpoint.resolve())
        if args.checkpoint == args.snapshot:
            parser.error("--checkpoint and --snapshot are the same file (a tip checkpoint replays nothing)")
        if args.genesis:
            print("note: --genesis ignored in checkpoint mode — genesis state is inside the checkpoint", file=sys.stderr)
            args.genesis = None
    if args.compare_state_with:
        compare = Path(args.compare_state_with)
        if not compare.exists():
            parser.error(f"--compare-state-with DB not found: {compare}")
        args.compare_state_with = str(compare.resolve())
    if not args.checkpoint and not args.genesis:
        candidate = snapshot.parent / "genesis.json"
        if candidate.exists():
            args.genesis = str(candidate)
        else:
            parser.error("--genesis required (no genesis.json next to snapshot)")
    return args


def main() -> None:
    args = _parse_args()

    import asyncio

    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
