#!/usr/bin/env python3
"""bc-2 dress-rehearsal harness — five scratch node processes on one host.

Part of the chain-reset plan (RESET-GENESIS-HARNESS-1). Builds a `bc-2`
genesis with ``scripts/ops/build-genesis.py`` + ``aitbc_chain.genesis_builder``
(treasury 100M AIT + 256 AIT working floats, 5 authority chain parameters,
4 bridge validators = the rehearsal proposers), launches four proposer
instances plus one customer-style follower as ``systemd-run`` transient units
processes with per-instance data dirs, loopback ports and cgroup caps, and
runs the acceptance checks: identical block-0 hash, proposer rotation,
attestation quorum (>=2) on produced blocks — the fleet runs
``PBFT_CONSENSUS_ENABLED=false``, so no PBFT certificate exists in this mode —
restart/rejoin, stopped-proposer skip, fresh SQLite
service stores, and the gates1 golden replay.

Nothing here touches a live unit, env file, port, data dir, wallet or
keystore. Every path lives under one scratch root (``--scratch``, default
``/tmp/bc2-rehearsal``); teardown deletes the whole tree. Rehearsal keys are
minted fresh inside the scratch root and deleted with it — never copied from
or derived from fleet material.

Phases (also runnable individually):

    rehearsal.py keys        mint the rehearsal keyset under <scratch>/keystore
    rehearsal.py genesis     build + verify the genesis doc, distribute to 5 dirs
    rehearsal.py up          launch the 5 systemd-run transient units
    rehearsal.py wait        block until every instance head reaches N
    rehearsal.py check       all acceptance checks against RPCs and chain DBs
    rehearsal.py timing      per-phase wall-clock from journal timestamps
    rehearsal.py rejoin      stop i3, restart it, prove catch-up + slot resume
    rehearsal.py skip        stop i2, prove the rotation skips it
    rehearsal.py stores      coordinator + trading `alembic upgrade head` on
                             scratch SQLite stores
    rehearsal.py golden      run the golden-corpus check twice under gates1
    rehearsal.py untrusted   drop a validator from i4's TRUSTED_PROPOSERS,
                             watch the membership check refuse its blocks
    rehearsal.py stall       two validators down: heads freeze, no fork,
                             then resume on rejoin (post-PONR M2)
    rehearsal.py resync      corrupt one store, prove it dead, wipe +
                             re-init from genesis + resync (post-PONR M7)
    rehearsal.py teardown    stop units, delete the scratch tree, show it empty
    rehearsal.py run         keys -> genesis -> up -> wait -> check ->
                             timing -> rejoin -> skip -> stall -> resync ->
                             stores -> golden -> untrusted -> teardown

Live-host protection: before anything starts, the harness records
``ActiveEnterTimestamp``/``MainPID`` and head height of the live
aitbc-blockchain-node unit and node2's load/memory; it refuses (and tears
down) when the 1-min load average exceeds ``--max-load`` or available memory
drops below ``--min-avail-mib``, and it refuses to run two rehearsals at
once (a ``<scratch>/.lock`` plus a systemd unit-name check).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "blockchain-node" / "src"), str(REPO_ROOT / "cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from aitbc.utils import reset_guard
from aitbc_chain.cross_chain.bridge_types import BRIDGE_LOCKS_PAUSED_DETAIL

CHAIN_ID = "bc-2"
N_PROPOSERS = 4
N_INSTANCES = 5  # 4 proposers + 1 follower
STAKE_PER_VALIDATOR = "1000"

# Treasury: 100,000,000 AIT at UNITS_PER_AIT=36,000,000. Working floats: 256 AIT
# on top (operator-labelled working figures, tuned at dress rehearsal).
UNITS_PER_AIT = 36_000_000
TREASURY_UNITS = 100_000_000 * UNITS_PER_AIT
WORKING_UNITS = 256 * UNITS_PER_AIT
EXPECTED_TOTAL_UNITS = TREASURY_UNITS + WORKING_UNITS

# 11 named service floats at 1 AIT each (retired wallets get 0); the rest of
# the working band sits on one ops float, operator-adjustable at rehearsal.
SERVICE_FLOAT_NAMES = [
    "aiengine",
    "market-service",
    "coordinator-service",
    "trading-service",
    "exchange-service",
    "agent-coordinator",
    "pool-hub",
    "gpu-service",
    "edge-service",
    "ait-sell-escrow",
    "bridge-monitor",
]
SERVICE_FLOAT_UNITS = 1 * UNITS_PER_AIT
# Funded at 1 AIT: the 11 named floats + 2 executors + 3 authorities = 16
# accounts; the ops float holds the remainder of the 256 AIT working band.
N_SMALL_FLOATS = len(SERVICE_FLOAT_NAMES) + 2 + 3
OPS_FLOAT_UNITS = WORKING_UNITS - N_SMALL_FLOATS * SERVICE_FLOAT_UNITS

# Loopback port map: base + 10*i. RPC sits at base+2 matching the fleet
# P2P->RPC offset convention.
PORT_BASE = 18400
PORT_STRIDE = 10

# Instance roles: i0..i3 proposers, i4 follower.
PROPOSER_INSTANCES = list(range(N_PROPOSERS))
FOLLOWER_INSTANCE = N_PROPOSERS  # i4

# cgroup caps matching the live aitbc-blockchain-node unit profile.
UNIT_MEMORY_MAX = "2G"
UNIT_CPU_QUOTA = "50%"
UNIT_TASKS_MAX = "614"

# Every gate collapses to 1 on bc-2 (RESET-VECTORS-2: 0 means NOT activated on
# unmodified code). The complete relevant set; keep in sync with
# tests/golden/profiles.py GATES1_PINS.
GATE_ENV = {
    "STATE_TRANSITION_V2_HEIGHT": "1",
    "STATE_TRANSITION_V3_HEIGHT": "1",
    "STATE_TRANSITION_V4_HEIGHT": "1",
    "STATE_TRANSITION_V5_HEIGHT": "1",
    "STATE_TRANSITION_V6_HEIGHT": "1",
    "STATE_TRANSITION_V7_HEIGHT": "1",
    "STATE_TRANSITION_V8_HEIGHT": "1",
    "STATE_TRANSITION_V9_HEIGHT": "1",
    "STATE_TRANSITION_V10_HEIGHT": "1",
    "STATE_TRANSITION_V11_HEIGHT": "1",
    "STATE_TRANSITION_V12_HEIGHT": "1",
    "STATE_TRANSITION_V13_HEIGHT": "1",
    "STATE_TRANSITION_V14_HEIGHT": "1",
    "BRIDGE_LOCK_LEAF_V2_HEIGHT": "1",
    "ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT": "1",
}

LIVE_UNITS = [
    "aitbc-blockchain-node",
    "aitbc-blockchain-rpc",
    "aitbc-blockchain-p2p",
    "aitbc-wallet",
]

# Rehearsal redis: lease_tracker requires a working broker on producers, and
# pointing GOSSIP_BROADCAST_URL at a dead port crashes them. A dedicated
# scratch instance on 16379 — never the live 6379 broker.
REHEARSAL_REDIS_PORT = 16379
REHEARSAL_REDIS_URL = f"redis://127.0.0.1:{REHEARSAL_REDIS_PORT}"

DEFAULT_LOAD_CEILING = 24.0  # 1-min loadavg; node2 has 32 cores, live ~<10
DEFAULT_MIN_AVAIL_MIB = 4096


@dataclass
class Instance:
    idx: int
    name: str
    role: str  # "proposer" | "follower"
    p2p_port: int
    rpc_port: int
    sync_port: int
    dir: Path


def _fail(msg: str) -> SystemExit:
    print(f"[!] {msg}", file=sys.stderr)
    return SystemExit(1)


def scratch_root(raw: str) -> Path:
    """Validate ``--scratch`` through the shared reset guard.

    Same enforcement point as the legacy destructive tools
    (``aitbc.utils.reset_guard.scratch_root``): absolute path, at least
    three resolved path components, and outside the live prefixes. The
    CLI value is wrapped as the guard's env dict so the harness keeps
    its argument-driven contract — no env marker is required here.
    """
    try:
        return reset_guard.scratch_root({reset_guard.SCRATCH_ENV: raw})
    except reset_guard.ResetGuardError as exc:
        raise _fail(f"--scratch {exc}") from exc


def instances(root: Path) -> list[Instance]:
    out = []
    for i in range(N_INSTANCES):
        role = "proposer" if i in PROPOSER_INSTANCES else "follower"
        base = PORT_BASE + i * PORT_STRIDE
        out.append(
            Instance(
                idx=i,
                name=f"bc2-i{i}",
                role=role,
                p2p_port=base,
                rpc_port=base + 2,
                sync_port=base + 4,
                dir=root / "instances" / f"i{i}",
            )
        )
    return out


def _mint_key() -> dict[str, str]:
    """Rehearsal-only keypair via eth-account; stays inside the scratch root."""
    from eth_account import Account
    from eth_keys import keys as eth_keys

    account = Account.create(secrets.token_bytes(32))
    private = eth_keys.PrivateKey(bytes(account.key))
    return {
        "address": account.address,
        "private_key": account.key.hex(),
        # eth_keys' to_hex() already carries the 0x prefix.
        "public_key": private.public_key.to_hex(),
    }


def phase_keys(root: Path) -> Path:
    key_dir = root / "keystore"
    key_file = key_dir / "keys.json"
    if key_file.exists():
        raise _fail(f"{key_file} exists — teardown first (refusing to overwrite rehearsal keys)")
    key_dir.mkdir(parents=True)
    keys = {
        "proposers": [_mint_key() for _ in range(N_PROPOSERS)],
        "executors": [_mint_key() for _ in range(2)],
        "authorities": {name: _mint_key() for name in ("bond_slash", "bridge_release", "escrow_settlement")},
        "treasury": _mint_key(),
        "service_floats": {name: _mint_key() for name in SERVICE_FLOAT_NAMES},
        "ops_float": _mint_key(),
    }
    key_file.write_text(json.dumps(keys, indent=2))
    key_file.chmod(0o600)
    print(f"[+] minted rehearsal keys -> {key_file} (0600; deleted with the scratch tree)")
    return key_file


def _load_keys(root: Path) -> dict:
    key_file = root / "keystore" / "keys.json"
    if not key_file.exists():
        raise _fail(f"no rehearsal keys at {key_file} — run `rehearsal.py keys` first")
    return json.loads(key_file.read_text())


def _bond_account_addresses() -> list[str]:
    """The two zero-balance accounts ``init_db`` always creates
    (``ensure_bond_accounts``): bond escrow + bond burn, keccak-derived.
    The genesis loader skips already-existing rows, so these must appear in
    the allocation file at balance 0 — the claim then covers every row the
    post-init account table will ever contain."""
    from eth_utils import keccak

    from aitbc_chain.base_models import canonical_address

    return [
        canonical_address("0x" + keccak(b"aitbc.bond.escrow").hex()[:40]),
        canonical_address("0x" + keccak(b"aitbc.bond.burn").hex()[:40]),
    ]


def _allocations(keys: dict) -> list[dict]:
    """Working allocation figures (operator-labelled, tuned at dress rehearsal)."""
    allocs = [{"address": keys["treasury"]["address"], "balance": TREASURY_UNITS, "nonce": 0}]
    funded = [
        *(k["address"] for k in keys["executors"]),
        *(k["address"] for k in keys["authorities"].values()),
        *(k["address"] for k in keys["service_floats"].values()),
    ]
    for addr in funded:
        allocs.append({"address": addr, "balance": SERVICE_FLOAT_UNITS, "nonce": 0})
    allocs.append({"address": keys["ops_float"]["address"], "balance": OPS_FLOAT_UNITS, "nonce": 0})
    for addr in _bond_account_addresses():
        allocs.append({"address": addr, "balance": 0, "nonce": 0})
    return allocs


def _parameters(keys: dict) -> dict[str, str]:
    auth = keys["authorities"]
    executors = ",".join(k["address"] for k in keys["executors"])
    return {
        "governance_executors": executors,
        "escrow_settlement_authority": auth["escrow_settlement"]["address"],
        "bond_slash_authority": auth["bond_slash"]["address"],
        "bridge_release_authority": auth["bridge_release"]["address"],
        "escrow_fee_recipient": auth["escrow_settlement"]["address"],
    }


def _bridge_validators(keys: dict) -> list[dict]:
    return [{"address": k["address"], "public_key": k["public_key"], "epoch": 1} for k in keys["proposers"]]


def phase_genesis(root: Path, *, force: bool = False) -> Path:
    keys = _load_keys(root)
    build_dir = root / "genesis-build"
    build_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"chain_id": CHAIN_ID, "expected_total_units": EXPECTED_TOTAL_UNITS}
    allocations = _allocations(keys)
    parameters = _parameters(keys)
    validators = _bridge_validators(keys)

    files = {
        "manifest.json": manifest,
        "allocations.json": allocations,
        "parameters.json": parameters,
        "bridge-validators.json": validators,
    }
    for name, payload in files.items():
        (build_dir / name).write_text(json.dumps(payload, indent=2))

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "ops" / "build-genesis.py"),
        "--manifest",
        str(build_dir / "manifest.json"),
        "--allocations",
        str(build_dir / "allocations.json"),
        "--parameters",
        str(build_dir / "parameters.json"),
        "--bridge-validators",
        str(build_dir / "bridge-validators.json"),
        "--data-dir",
        str(build_dir / "out"),
    ]
    if force:
        cmd.append("--force")
    child_env = dict(
        os.environ,
        PYTHONPATH=f"{REPO_ROOT}:{REPO_ROOT}/apps/blockchain-node/src",
        # The builder imports ChainSettings — keep it off the host env file
        # and off the live redis, same policy as the rehearsal instances.
        AITBC_CHAIN_ENV_FILE="",
        REDIS_URL="redis://127.0.0.1:16379",
    )
    subprocess.run(cmd, check=True, env=child_env)
    built = build_dir / "out" / "data" / CHAIN_ID / "genesis.json"
    if not built.exists():
        raise _fail(f"builder did not produce {built}")

    # Read-only verification of the artifact we just wrote.
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ops" / "verify-genesis-root.py"), str(built)],
        check=True,
        env=child_env,
    )

    # One built file -> all five instance dirs (never RPC bootstrap).
    for inst in instances(root):
        dest = inst.dir / "data" / CHAIN_ID
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dest / "genesis.json")
    print(f"[+] genesis.json distributed to {N_INSTANCES} instance dirs")
    return built


def _env_lines(root: Path, inst: Instance, keys: dict) -> str:
    """Per-instance env file — scratch-only paths, loopback ports, gates=1.

    ``AITBC_CHAIN_ENV_FILE`` is emptied so ChainSettings never loads the
    host's ``/etc/aitbc/blockchain.env``. ``REDIS_URL`` and
    ``GOSSIP_BROADCAST_URL`` point at the dedicated scratch redis on
    16379 — a real broker the lease tracker needs, never the live 6379.
    """
    mesh = [f"ws://127.0.0.1:{p.rpc_port}/rpc/gossip/ws" for p in instances(root) if p.idx != inst.idx]
    validator_set = json.dumps(
        [{"address": k["address"], "stake": STAKE_PER_VALIDATOR} for k in keys["proposers"]],
        separators=(",", ":"),
    )
    lines = {
        "AITBC_CHAIN_ENV_FILE": "",
        "CHAIN_ID": CHAIN_ID,
        "SUPPORTED_CHAINS": CHAIN_ID,
        "BLOCK_PRODUCTION_CHAINS": CHAIN_ID,
        # DATA_DIR is the base; the db resolves to <dir>/data/<chain>/chain.db
        # and genesis.json sits beside it — the same layout the fleet uses.
        "AITBC_DATA_DIR": str(inst.dir),
        "AITBC_LOG_DIR": str(inst.dir / "logs"),
        "AITBC_CONFIG_DIR": str(inst.dir / "etc"),
        "AITBC_RESET_SCRATCH": str(root),
        "RPC_BIND_HOST": "127.0.0.1",
        "RPC_BIND_PORT": str(inst.rpc_port),
        "P2P_BIND_HOST": "127.0.0.1",
        "P2P_BIND_PORT": str(inst.p2p_port),
        "SYNC_MANAGER_HTTP_PORT": str(inst.sync_port),
        "GOSSIP_BACKEND": "mesh",
        "GOSSIP_MESH_PEER_URLS": ",".join(mesh),
        # GOSSIP_AUTH_ENABLED left unset — fleet default (true). Proposers
        # carry PROPOSER_ID/PROPOSER_KEY so the challenge/response on the
        # restricted topics (blocks.*, pbft.*, consensus.*) signs with the
        # rehearsal validator key. The follower touches only public topics.
        # All five instances share one source IP; the default per-IP ws cap
        # (32) is below 4 peers x ~9 topics — excess connections get a
        # pre-accept close that surfaces as HTTP 403. Single-host transport
        # necessity, not a consensus-mode deviation.
        "GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP": "256",
        # Fleet consensus mode (node2 /etc/aitbc/blockchain.env, anchored
        # reads): PBFT off, multi-validator attestation 2-of-3 non-proposers,
        # subscription on, fleet timing values.
        "MULTI_VALIDATOR_CONSENSUS_ENABLED": "true",
        "MULTI_VALIDATOR_MIN_ATTESTATIONS": "2",
        "MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS": "15",
        # Fleet timing rows from the env-set table (the node0 drift rows
        # written fleet-wide here): linger and PBFT view-change values;
        # PBFT is off but the names match the fleet env files.
        "ATTESTATION_POST_QUORUM_LINGER_SECONDS": "2.0",
        "PBFT_VIEW_CHANGE_TIMEOUT": "30",
        "PBFT_CONSENSUS_ENABLED": "false",
        "VALIDATOR_SET": validator_set,
        "BRIDGE_MULTISIG_ENABLED": "true",
        "BRIDGE_MULTISIG_THRESHOLD": "2",
        # Env-set rows :64/:67/:68 — release admission and merkle-proof
        # requirement stay fleet-true; supported-chains admits only bc-2.
        "BRIDGE_RELEASE_ENABLED": "true",
        "BRIDGE_SUPPORTED_CHAINS": CHAIN_ID,
        "BRIDGE_REQUIRE_MERKLE_PROOF": "true",
        # release_enabled=True's production-safety check refuses startup
        # without a non-empty admin set (env-set: "Keep live"). Scratch
        # mirror: the four rehearsal proposers stand in as the admin set.
        "BRIDGE_ADMIN_ADDRESSES": ",".join(k["address"] for k in keys["proposers"]),
        # Env-set row decided 20 Oct: bc-2 launches with bridge locks
        # paused — lock admission answers 503 until the SEPOLIA-REDEPLOY-1
        # unpause; _check_bridge_paused proves the fence in `check`.
        "BRIDGE_LOCKS_PAUSED": "true",
        "ENABLE_BLOCK_PRODUCTION": "true" if inst.role == "proposer" else "false",
        "MAX_EMPTY_BLOCK_INTERVAL": "60",
        # Flag pins per GATES.md deployed column (commit 3697e778a): the three
        # env-observed-true switches; all other flags keep code defaults.
        "BRIDGE_LOCK_REQUIRE_REPLAY_GUARD": "true",
        "CROSS_CHAIN_REQUIRE_REPLAY_GUARD": "true",
        "SIDE_ROOT_SHADOW_ENABLED": "true",
        "DEFAULT_PEER_RPC_URL": f"http://127.0.0.1:{PORT_BASE + 2}",
        # Literal CSV: 'genesis' admits the genesis producer row; the four
        # validator addresses admit every rotated proposal on import.
        "TRUSTED_PROPOSERS": "genesis," + ",".join(k["address"] for k in keys["proposers"]),
        # Sync pins from the env-set table: auto-sync on, threshold 0 (any
        # gap pulls), and the post-V23-90 hardening value -1 for the state
        # sync gap — all five hosts write these.
        "AUTO_SYNC_ENABLED": "true",
        "AUTO_SYNC_THRESHOLD": "0",
        "STATE_SYNC_MAX_GAP": "-1",
        # Documented deviations, deliberately left at code defaults:
        # BLOCK_TIME_SECONDS stays 10 (fleet 60, env-set row :41) — a faster
        # tick suits the scratch window; PARALLEL_TX_VALIDATION stays unset
        # (fleet true, row :42) — inert on bc-2 where every height is v14,
        # outside its v2–8 window.
        "SYNC_MANAGER_ENABLED": "true",
        "SYNC_STATE_ROOT_VALIDATION_ENABLED": "true",
        "SUBSCRIPTION_ENABLED": "true",  # fleet value (node2 blockchain.env)
        # Sync-manager node identity (settings.proposer_id or p2p_node_id or
        # "unknown"): proposers win on PROPOSER_ID; the follower needs this or
        # its /rpc/subscribe body presents "unknown" and the peer-key binding
        # (issued for this name at join) can never match.
        "P2P_NODE_ID": inst.name,
        # i0 doubles as the hub: follower's sync source, import URL and hub
        # discovery all resolve to its rehearsal RPC.
        "HUB_RPC_URL": f"http://127.0.0.1:{PORT_BASE + 2}",
        "HUB_BLOCKCHAIN_RPC_URL": f"http://127.0.0.1:{PORT_BASE + 2}",
        "AITBC_SYNC_SOURCE": f"http://127.0.0.1:{PORT_BASE + 2}",
        "AITBC_SYNC_IMPORT_URL": f"http://127.0.0.1:{PORT_BASE + 2}",
        # The two broker URLs take the dedicated scratch redis (16379), never
        # the live 6379; COORDINATOR_API_URL stays a dead loopback port so a
        # client that ignores our wiring fails fast instead of touching the
        # live coordinator (8203).
        "REDIS_URL": REHEARSAL_REDIS_URL,
        "GOSSIP_BROADCAST_URL": REHEARSAL_REDIS_URL,
        "COORDINATOR_API_URL": "http://127.0.0.1:18203",
        "AITBC_NODE_METRICS_HOST": "127.0.0.1",
        "AITBC_NODE_METRICS_PORT": str(PORT_BASE + inst.idx * PORT_STRIDE + 6),
        "MEMPOOL_DB_URL": "",
        "DB_KEEPER_CONNECTION": "false",
        **GATE_ENV,
    }
    if inst.role == "proposer":
        own = keys["proposers"][inst.idx]
        lines["VALIDATOR_KEYS"] = json.dumps({own["address"]: own["private_key"]}, separators=(",", ":"))
        lines["PROPOSER_ID"] = own["address"]
        lines["PROPOSER_KEY"] = own["private_key"]
    # Single-quote every value so JSON survives `set -a; . file` sourcing.
    return "\n".join(f"{k}='{v}'" for k, v in sorted(lines.items())) + "\n"


def _write_instance_envs(root: Path, keys: dict) -> None:
    for inst in instances(root):
        (inst.dir / "data").mkdir(parents=True, exist_ok=True)
        (inst.dir / "logs").mkdir(parents=True, exist_ok=True)
        env_file = inst.dir / "instance.env"
        env_file.write_text(_env_lines(root, inst, keys))
        env_file.chmod(0o600)
    _seed_follower_peer_key(root)


def _seed_follower_peer_key(root: Path) -> None:
    """Pre-issue the follower's RPC peer key directly into the hub's
    ``peer_keys.db`` — the same row ``POST /rpc/join`` writes (SHA-256 of the
    key, bound to the follower's ``P2P_NODE_ID``).

    Two fleet behaviours make the seed necessary. Subscription delivery is
    push-only: ``/rpc/subscribe`` needs a node-bound peer key, and the
    websocket streams only new seals — a follower that joins after block 1
    gets no backlog, while pull sync fires only above ``auto_sync_threshold``
    (10). And a follower whose RPC bootstrap wins the genesis race mints its
    own block-0 timestamp, which skews ``proposer_round`` on every later
    block — so the follower must load genesis from its file like the
    proposers, which means all five node units start before any RPC unit
    exists to bootstrap from. A pre-issued key lets the follower authenticate
    from its first process start instead of joining mid-flight.
    """
    hub, follower = instances(root)[0], instances(root)[-1]
    key = f"aitbc-peer-{secrets.token_hex(24)}"
    env_file = follower.dir / "instance.env"
    env_file.write_text(env_file.read_text() + f"BLOCKCHAIN_RPC_API_KEY={key}\n")
    db = hub.dir / "data" / "peer_keys.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS peer_keys ("
            " key_hash TEXT PRIMARY KEY,"
            " node_id TEXT NOT NULL,"
            " issued_ip TEXT NOT NULL,"
            " contact TEXT,"
            " created_at REAL NOT NULL,"
            " revoked_at REAL"
            ")"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_peer_keys_active_node ON peer_keys(node_id) WHERE revoked_at IS NULL"
        )
        conn.execute(
            "INSERT INTO peer_keys (key_hash, node_id, issued_ip, contact, created_at, revoked_at)"
            " VALUES (?, ?, ?, ?, ?, NULL)",
            (hashlib.sha256(key.encode()).hexdigest(), follower.name, "rehearsal-seed", None, time.time()),
        )


def _live_snapshot() -> dict[str, dict[str, str]]:
    snap: dict[str, dict[str, str]] = {}
    for unit in LIVE_UNITS:
        # Keyed Name=value output: --value order does not follow the
        # requested property order (observed: MainPID emitted first), so a
        # positional split mislabels the fields.
        out = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveEnterTimestamp,MainPID"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        fields = {"ActiveEnterTimestamp": "", "MainPID": ""}
        for line in out.stdout.strip().splitlines():
            key, _, value = line.partition("=")
            if key in fields:
                fields[key] = value
        snap[unit] = fields
    return snap


def _load1() -> float:
    return os.getloadavg()[0]


def _avail_mib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


def _check_host_budget(max_load: float, min_avail_mib: int) -> None:
    if _load1() > max_load:
        raise _fail(f"load average {_load1():.1f} > ceiling {max_load} — stopping to protect the live host")
    if _avail_mib() < min_avail_mib:
        raise _fail(f"MemAvailable {_avail_mib()} MiB < floor {min_avail_mib} — stopping to protect the live host")


def _claim_rehearsal(root: Path) -> None:
    """One rehearsal at a time. A lock whose recorded pid is dead is stale
    (a crashed run) and taken over; a live pid refuses."""
    lock = root / ".lock"
    root.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        alive = False
        try:
            pid = int(lock.read_text().strip() or "0")
            os.kill(pid, 0)
            alive = True
        except (ValueError, ProcessLookupError):
            alive = False
        except PermissionError:
            alive = True  # someone else's process — refuse to be safe
        if alive:
            raise _fail(f"{lock} held by live pid — another rehearsal is running. One at a time.")
        print("[*] stale rehearsal lock taken over (recorded pid is gone)")
    lock.write_text(str(os.getpid()))
    out = subprocess.run(
        ["systemctl", "list-units", "bc2-i*", "--no-legend", "--plain"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    live = [line for line in out.stdout.splitlines() if line.strip()]
    if live:
        raise _fail("rehearsal units still active: " + "; ".join(u.split()[0] for u in live))


def _prelude(inst: Instance, repo_root: Path = REPO_ROOT) -> str:
    env_file = inst.dir / "instance.env"
    # PYTHONPATH mirrors the live unit; HOME is the instance dir, never
    # /var/lib/aitbc. repo_root lets rollback.py run the previous release
    # from a git-archive tree while the default keeps this rehearsal's own.
    return (
        f"export HOME={inst.dir} PYTHONPATH={repo_root}:{repo_root}/apps/blockchain-node/src; set -a; . {env_file}; set +a; "
    )


def _rpc_cmd(inst: Instance, python: str) -> str:
    # Fleet split (live values): the node unit runs GOSSIP_BACKEND=mesh while
    # the RPC unit runs gossip over the shared redis broker — the /subscribe/ws
    # block-push path subscribes the process-local broker, which must see the
    # broker-carried blocks to forward them. Overriding after the env file
    # mirrors the live units, where the secrets file wins the same key.
    return (
        f"export GOSSIP_BACKEND=redis; "
        f"exec {python} -m uvicorn aitbc_chain.app:app --host 127.0.0.1 --port {inst.rpc_port} "
        f"--workers 1 --log-level warning --timeout-graceful-shutdown 3 "
        f">>{inst.dir}/logs/rpc.log 2>&1"
    )


def _spawn(inst: Instance, python: str, *, with_rpc: bool = True, repo_root: Path = REPO_ROOT) -> None:
    # Consensus/production process (mirrors aitbc-blockchain-node) + the RPC
    # service (mirrors aitbc-blockchain-rpc: uvicorn aitbc_chain.app:app).
    units = [
        (inst.name, f"exec {python} -m aitbc_chain.main >>{inst.dir}/logs/node.log 2>&1"),
    ]
    if with_rpc:
        units.append((f"{inst.name}-rpc", _rpc_cmd(inst, python)))
    prelude = _prelude(inst, repo_root)
    for unit, cmd in units:
        subprocess.run(
            [
                # Transient systemd-run unit (service form): detached, capped via
                # cgroup properties, stops via `systemctl stop`. (`--scope` would
                # instead run the node in the *foreground* of this process.)
                "systemd-run",
                "--collect",
                f"--unit={unit}",
                f"--property=MemoryMax={UNIT_MEMORY_MAX}",
                f"--property=CPUQuota={UNIT_CPU_QUOTA}",
                f"--property=TasksMax={UNIT_TASKS_MAX}",
                "--",
                "bash",
                "-c",
                prelude + cmd,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )


def _spawn_rpc(inst: Instance, python: str) -> None:
    """The uvicorn RPC unit on its own — delayed until after file genesis load."""
    subprocess.run(
        [
            "systemd-run",
            "--collect",
            f"--unit={inst.name}-rpc",
            f"--property=MemoryMax={UNIT_MEMORY_MAX}",
            f"--property=CPUQuota={UNIT_CPU_QUOTA}",
            f"--property=TasksMax={UNIT_TASKS_MAX}",
            "--",
            "bash",
            "-c",
            _prelude(inst) + _rpc_cmd(inst, python),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _spawn_redis(root: Path) -> None:
    """Dedicated scratch redis — no persistence, loopback only, scratch dir."""
    redis_dir = root / "redis"
    redis_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "systemd-run",
            "--collect",
            "--unit=bc2-redis",
            "--property=MemoryMax=256M",
            "--property=TasksMax=64",
            "--",
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(REHEARSAL_REDIS_PORT),
            "--dir",
            str(redis_dir),
            "--save",
            "",
            "--appendonly",
            "no",
            "--protected-mode",
            "yes",
            # Loopback-only + protected mode; no requirepass — the rehearsal
            # URLs carry no credentials.
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    print(f"[+] bc2-redis up on 127.0.0.1:{REHEARSAL_REDIS_PORT} (scratch-only broker)")


def _unit_pid(name: str) -> str | None:
    out = subprocess.run(
        ["systemctl", "show", name, "-p", "MainPID", "--value"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    pid = out.stdout.strip()
    return pid if pid and pid != "0" else None


def _head(inst: Instance) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{inst.rpc_port}/rpc/head", timeout=3) as r:  # nosec B310
            data = json.loads(r.read())
            return int(data.get("height", data.get("block", {}).get("height", -1)))
    except Exception:
        return None


def _block(inst: Instance, height: int) -> dict | None:
    try:
        with urllib.request.urlopen(  # nosec B310
            f"http://127.0.0.1:{inst.rpc_port}/rpc/blocks/{height}", timeout=3
        ) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _post_json(url: str, body: dict) -> tuple[int, dict]:
    """POST JSON; returns (status, payload) — HTTP errors keep their code."""
    req = urllib.request.Request(  # nosec B310
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # nosec B310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def _unit_field(name: str, prop: str) -> str:
    """One ``systemctl show --value`` field for a scratch unit (journal-side
    timestamp source — the 'measured' label in the timing report). Asked
    for ``--timestamp=utc`` so it shares the block timestamp's instant
    basis: local-zone output made the start->seal delta land ~-7200s."""
    out = subprocess.run(
        ["systemctl", "show", name, f"--property={prop}", "--value", "--timestamp=utc"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return out.stdout.strip()


# zone-abbreviation -> seconds east of UTC for the strings systemctl can
# emit on this fleet (it is asked for UTC, but a locale suffix still
# parses instead of silently comparing different zones).
_TZ_OFFSETS = {"UTC": 0, "GMT": 0, "CET": 3600, "CEST": 7200}


def _parse_systemd_ts(raw: str) -> datetime | None:
    """Parse an ActiveEnterTimestamp value ('Mon 2026-10-20 07:43:42 CEST')
    into naive UTC. An unknown zone name returns None so the report says
    unmeasured instead of comparing different clocks."""
    if not raw:
        return None
    head, _, zone = raw.rpartition(" ")
    offset = _TZ_OFFSETS.get(zone)
    if offset is None:
        return None
    try:
        return datetime.strptime(head, "%a %Y-%m-%d %H:%M:%S") - timedelta(seconds=offset)
    except ValueError:
        return None


def _parse_iso_ts(raw: object) -> datetime | None:
    """Parse an ISO-8601 block timestamp into naive UTC — the same instant
    basis _parse_systemd_ts returns. A naive input is taken as UTC."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)


def _span_seconds(times: list[datetime]) -> float:
    """Latest minus earliest in seconds; 0.0 for fewer than two points."""
    if len(times) < 2:
        return 0.0
    return (max(times) - min(times)).total_seconds()


def phase_up(root: Path, python: str, max_load: float, min_avail_mib: int) -> None:
    before = _live_snapshot()
    (root / "live-before.json").write_text(json.dumps(before, indent=2))
    _check_host_budget(max_load, min_avail_mib)
    keys = _load_keys(root)
    _write_instance_envs(root, keys)
    _spawn_redis(root)
    insts = instances(root)

    # All five node units start before any RPC unit exists: genesis then
    # comes from each instance's own genesis.json — the RPC bootstrap path
    # serves allocations only (no chain_parameter/bridge_validator rows and a
    # locally-minted block-0 timestamp that skews proposer_round), so letting
    # it win makes a late starter diverge on the schedule and the v14 aux
    # root. The follower's peer key was already seeded into i0's
    # peer_keys.db at env-write time, so its subscription authenticates from
    # the first connection — no enrollment window is needed.
    for inst in insts:
        _spawn(inst, python, with_rpc=False)
        time.sleep(0.5)
    deadline = time.time() + 90
    pending = set(range(N_INSTANCES))
    while pending and time.time() < deadline:
        for i in list(pending):
            log = insts[i].dir / "logs" / "node.log"
            if log.exists() and (
                "Successfully created genesis block from genesis.json" in log.read_text()
                or "Genesis block already exists" in log.read_text()
            ):
                pending.discard(i)
        if pending:
            time.sleep(1)
    if pending:
        raise _fail(f"genesis file load not observed for: {sorted(pending)} — refusing to start RPC units")
    for inst in insts:
        _spawn_rpc(inst, python)
        print(f"[+] {inst.name} ({inst.role}) up: rpc=127.0.0.1:{inst.rpc_port} dir={inst.dir}")


def phase_wait(root: Path, height: int, timeout: int, max_load: float, min_avail_mib: int) -> None:
    deadline = time.time() + timeout
    pending = set(range(N_INSTANCES))
    insts = instances(root)
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        for i in list(pending):
            h = _head(insts[i])
            if h is not None and h >= height:
                pending.discard(i)
        if not pending:
            print(f"[+] all instances at height >= {height}")
            return
        time.sleep(3)
    raise _fail(f"timed out waiting for height {height}; pending instances: {sorted(pending)}")


def _sql(db: Path, query: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        return conn.execute(query, params).fetchall()


def _check_block0(insts: list[Instance], failures: list[str]) -> None:
    hashes = set()
    for inst in insts:
        blk = _block(inst, 0) or {}
        h = blk.get("hash") or (blk.get("block") or {}).get("hash")
        hashes.add(h)
    if len(hashes) != 1 or None in hashes or "" in hashes:
        failures.append(f"block-0 hash differs across instances: {sorted(str(h) for h in hashes)}")
    else:
        print(f"[+] block-0 hash identical on all 5: {next(iter(hashes))}")


def _check_db_rows(db: Path, failures: list[str]) -> list[tuple]:
    validators = [
        r[0] for r in _sql(db, "SELECT address FROM bridge_validators WHERE chain_id=? AND is_active=1", (CHAIN_ID,))
    ]
    params = sorted(r[0] for r in _sql(db, "SELECT parameter FROM chain_parameter WHERE chain_id=?", (CHAIN_ID,)))
    if len(validators) != N_PROPOSERS:
        failures.append(f"bridge_validators has {len(validators)} active rows, want {N_PROPOSERS}")
    else:
        print(f"[+] bridge_validators: {len(validators)} active rows")
    want_params = {
        "bond_slash_authority",
        "bridge_release_authority",
        "escrow_fee_recipient",
        "escrow_settlement_authority",
        "governance_executors",
    }
    if set(params) != want_params:
        failures.append(f"chain_parameter rows {params} != expected {sorted(want_params)}")
    else:
        print("[+] chain_parameter: 5 rows incl. governance_executors")
    return _block_rows(db)


def _block_rows(db: Path) -> list[tuple]:
    return _sql(
        db,
        "SELECT height, proposer, block_metadata FROM block WHERE chain_id=? AND height>0 ORDER BY height",
        (CHAIN_ID,),
    )


def _check_certificates_and_rotation(root: Path, db: Path, rows: list[tuple], failures: list[str]) -> None:
    attested_heights = 0
    proposers_seen: set[str] = set()
    for _height, proposer, meta in rows:
        m = json.loads(meta or "{}")
        # Fleet mode: no pbft_certificate exists; the quorum evidence is the
        # ``attestations`` list the proposer stamps at MIN_ATTESTATIONS (2).
        attestations = m.get("attestations") or []
        if len(attestations) >= 2:
            attested_heights += 1
        if proposer:
            proposers_seen.add(proposer.lower())
    if rows and attested_heights == 0:
        failures.append("no attestation quorum (>=2 signatures) found on any produced block")
    else:
        print(f"[+] attestation quorum >=2 on {attested_heights}/{len(rows)} produced blocks")

    key_file = root / "keystore" / "keys.json"
    want = {k["address"].lower() for k in json.loads(key_file.read_text())["proposers"]}
    unknown = proposers_seen - want
    if unknown:
        failures.append(f"blocks sealed by addresses outside VALIDATOR_SET: {sorted(unknown)}")
        return
    # A proposer whose PBFT slot times out is skipped by the rotation, so a
    # missing identity at check time is not yet a failure — wait through two
    # more rotation windows before calling it.
    deadline = time.time() + 240
    while len(proposers_seen) < N_PROPOSERS and time.time() < deadline:
        time.sleep(15)
        proposers_seen |= {p.lower() for _h, p, _m in _block_rows(db) if p}
    if len(proposers_seen) < N_PROPOSERS:
        failures.append(f"only {len(proposers_seen)}/{N_PROPOSERS} proposers sealed a block so far")
    else:
        print(f"[+] rotation: all {N_PROPOSERS} proposers sealed blocks")


def _check_bridge_paused(insts: list[Instance], failures: list[str]) -> None:
    """BRIDGE_LOCKS_PAUSED must fence lock admission with HTTP 503 on the
    scratch rpc — the decided env-set value for the bc-2 launch. The fence
    sits before signature validation, so a well-shaped unsigned body
    reaches it. Refunds stay open; only admission is gated."""
    body = {
        "source_chain": CHAIN_ID,
        "target_chain": "sepolia",
        "token": "native",
        "sender": "0x" + "11" * 20,
        "recipient": "0x" + "22" * 20,
        "amount": 1,
    }
    code, payload = _post_json(f"http://127.0.0.1:{insts[0].rpc_port}/cross-chain/bridge", body)
    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if code != 503:
        failures.append(f"bridge lock admission answered {code}, want 503 — pause fence not enforced")
    elif detail != BRIDGE_LOCKS_PAUSED_DETAIL:
        failures.append(f"bridge lock admission 503 with unexpected detail {detail!r} — not the pause fence")
    else:
        print(f"[+] BRIDGE_LOCKS_PAUSED fence: /cross-chain/bridge -> 503 ({detail})")


def phase_check(root: Path) -> list[str]:
    insts = instances(root)
    failures: list[str] = []

    _check_block0(insts, failures)

    heads = {i.idx: _head(i) for i in insts}
    print(f"[*] heads: {heads}")
    if any(h is None or h < 1 for h in heads.values()):
        failures.append(f"some instance head below 1: {heads}")

    db = insts[0].dir / "data" / CHAIN_ID / "chain.db"
    if not db.exists():
        failures.append(f"chain db missing at {db}")
        return failures
    rows = _check_db_rows(db, failures)
    _check_certificates_and_rotation(root, db, rows, failures)
    _check_bridge_paused(insts, failures)
    return failures


def phase_timing(root: Path) -> None:
    """Per-phase wall-clock report from journal timestamps — measured where
    systemctl answers, estimate where only the code's sleeps are known.

    Runs after `check` and before `rejoin`/`skip`: those phases restart
    units, which would overwrite the original ActiveEnterTimestamp values.
    """
    insts = instances(root)
    starts: dict[str, datetime] = {}
    for inst in insts[:N_PROPOSERS]:
        ts = _parse_systemd_ts(_unit_field(inst.name, "ActiveEnterTimestamp"))
        if ts is not None:
            starts[inst.name] = ts
    if len(starts) >= 2:
        span = _span_seconds(list(starts.values()))
        last = max(starts, key=starts.get)
        print(f"[+] validator start span {span:.1f}s over {len(starts)} units, last: {last} (measured: systemctl)")
        blk = _block(insts[0], 1) or {}
        bts = _parse_iso_ts(blk.get("timestamp") or (blk.get("block") or {}).get("timestamp"))
        if bts is not None:
            delta = (bts - starts[last]).total_seconds()
            if 0 <= delta <= 300:
                print(f"[+] last validator start -> block 1: {delta:.1f}s (measured: journal+block ts)")
            else:
                print(f"[*] last-validator-start -> block 1: unmeasured (clock mismatch: {delta:.1f}s outside 0..300)")
        else:
            print("[*] block 1 timestamp unavailable — start->seal delta unmeasured")
    else:
        print("[*] unit start timestamps unavailable — span is an estimate (0.5s sleep x5 + spawn cost)")


def _untrusted_env(env_text: str, drop: str) -> str:
    """Return env_text with ``drop`` removed from the TRUSTED_PROPOSERS CSV."""

    def _fix(m: re.Match) -> str:
        keep = [p for p in m.group(2).split(",") if p.strip() and p != drop]
        return m.group(1) + ",".join(keep) + "'"

    return re.sub(r"(TRUSTED_PROPOSERS=')([^']*)'", _fix, env_text)


def _restart_node(inst: Instance, python: str) -> None:
    """Restart only the node unit — the rpc unit's env is unchanged."""
    subprocess.run(["systemctl", "stop", inst.name], capture_output=True, timeout=60)
    _spawn(inst, python, with_rpc=False)


def phase_untrusted(root: Path, python: str, timeout: int) -> None:
    """TRUSTED_PROPOSERS refusal, proven live on the follower — no production
    code change: i4's scratch env drops one validator address; the import
    validator (sync_validator.py) then refuses that proposer's blocks with
    'not in trusted set' in node.log. The env is restored and the node
    restarted afterwards so teardown sees a normal fleet."""
    inst = instances(root)[4]
    keys = _load_keys(root)
    victim = keys["proposers"][3]["address"]
    env_file = inst.dir / "instance.env"
    original = env_file.read_text()
    env_file.write_text(_untrusted_env(original, victim))
    _restart_node(inst, python)
    try:
        log = inst.dir / "logs" / "node.log"
        mark = "not in trusted set"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if log.exists() and mark in log.read_text():
                print(f"[+] {inst.name} refused a block from an unlisted proposer — TRUSTED_PROPOSERS membership check live")
                break
            time.sleep(2)
        else:
            raise _fail(f"no trusted-set refusal on {inst.name} within {timeout}s")
    finally:
        env_file.write_text(original)
        _restart_node(inst, python)


def _stop_instance(inst: Instance) -> None:
    subprocess.run(["systemctl", "stop", inst.name], capture_output=True, timeout=60)
    subprocess.run(["systemctl", "stop", f"{inst.name}-rpc"], capture_output=True, timeout=60)


# --- fault-injection phases (RESET-REHEARSAL-FAULTS-1, #351) ---

# poa.py:1919 — the seal refusal that marks a liveness failure in
# multi-validator mode. Stall and gossip-degradation rehearsals both key
# on it: it is the difference between "nodes dead" and "alive but cannot
# collect the attestations the mode requires".
STALL_MARK = re.compile(
    r"Not enough attestations for multi-validator block \d+:"
    r" got \d+ attestation\(s\) and \d+ PBFT commit\(s\), need \d+"
)


def _node_log(inst: Instance) -> str:
    log = inst.dir / "logs" / "node.log"
    return log.read_text() if log.exists() else ""


def phase_stall(root: Path, python: str, timeout: int, max_load: float, min_avail_mib: int) -> None:
    """M2 — two validators down: heads freeze without forking, then resume.

    Multi-validator liveness needs proposer + two remote attestations; with
    only i0 and i1 alive every proposal collects at most one signature, so
    the seal refusal fires each attempt. Heads must stay frozen AND equal —
    equal-and-frozen is the M2 signature on the post-PONR decision tree;
    equal-and-advancing is not consensus trouble, and divergent heads are
    M3. Restoring both stopped validators must resume production.
    """
    insts = instances(root)
    down = [insts[2], insts[3]]
    live = [insts[0], insts[1], insts[4]]
    for inst in down:
        _stop_instance(inst)
    frozen = {inst.idx: _head(inst) for inst in live}
    print(f"[*] stopped {[i.name for i in down]}; live heads {frozen} — watching two empty-block intervals")
    # MAX_EMPTY_BLOCK_INTERVAL is 60s: two intervals of identical heads is
    # the strongest "not advancing" signal an empty chain can give.
    observe_s = 2 * 60 + 15
    deadline = time.time() + observe_s
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        for inst in live:
            h = _head(inst)
            if h is not None and h != frozen[inst.idx]:
                raise _fail(
                    f"{inst.name} head moved {frozen[inst.idx]} -> {h} with two validators down"
                    " — that is a fork or uncontrolled seal, not an M2 stall"
                )
        time.sleep(5)
    if not any(STALL_MARK.search(_node_log(inst)) for inst in live[:2]):
        raise _fail("no 'Not enough attestations' refusal on bc2-i0/bc2-i1 — the freeze is not proven a liveness stall")
    print(f"[+] heads frozen and equal for {observe_s}s; seal refusal logged — M2 stall proven")
    for inst in down:
        _spawn(inst, python)
    h0 = frozen[0]
    deadline = time.time() + timeout
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        h = _head(live[0])
        if h is not None and h0 is not None and h > h0:
            print(f"[+] validators restored; head advanced {h0} -> {h} — production resumed")
            return
        time.sleep(5)
    raise _fail(f"chain did not resume within {timeout}s after restoring two validators")


def _corrupt_store(inst: Instance) -> Path:
    """The M7 fault: overwrite chain.db's header page so sqlite refuses to
    open it ('file is not a database'). Scratch-only — the path lives under
    the instance's own data dir."""
    db = inst.dir / "data" / CHAIN_ID / "chain.db"
    if not db.exists():
        raise _fail(f"no chain.db to corrupt at {db} — is {inst.name} initialised?")
    with open(db, "r+b") as f:
        f.write(b"NOT-A-SQLITE-DB\x00" + bytes(96))
    return db


def _wipe_store_keep_genesis(root: Path, inst: Instance) -> Path:
    """The M7 repair: delete data/<chain> entirely, then restore the
    genesis.json the genesis phase built — the same shape the runbook's
    'delete the data dir, re-init from genesis, resync' produces."""
    data = inst.dir / "data" / CHAIN_ID
    genesis_src = root / "genesis-build" / "out" / "data" / CHAIN_ID / "genesis.json"
    if not genesis_src.exists():
        raise _fail(f"cannot re-init {inst.name}: {genesis_src} missing (genesis phase never ran?)")
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True, exist_ok=True)
    genesis = data / "genesis.json"
    shutil.copy2(genesis_src, genesis)
    return genesis


def phase_resync(root: Path, python: str, timeout: int, max_load: float, min_avail_mib: int) -> None:
    """M7 — corrupt one scratch store, prove the node cannot use it, then
    delete + re-init from genesis + resync to exact head hash.

    Detection accepts either failure shape: the node process dies on the
    corrupt file (unit loses its MainPID), or it stays up while logging the
    sqlite fault. Both prove the store was unusable; the repair is then the
    runbook's own: wipe data/bc-2, restore genesis.json, let genesis load
    and AUTO_SYNC_THRESHOLD=0 pull the missing blocks."""
    insts = instances(root)
    victim, healthy = insts[2], insts[0]
    _stop_instance(victim)
    db = _corrupt_store(victim)
    print(f"[*] corrupted {db} (sqlite header overwritten); restarting {victim.name} node")
    _restart_node(victim, python)
    marks = ("file is not a database", "DatabaseError", "sqlite3.")
    deadline = time.time() + 90
    detected = ""
    while time.time() < deadline and not detected:
        _check_host_budget(max_load, min_avail_mib)
        if _unit_pid(victim.name) is None:
            detected = f"{victim.name} node unit is dead on the corrupt store"
        else:
            log = _node_log(victim)
            hit = next((m for m in marks if m in log), None)
            if hit:
                detected = f"{victim.name} node.log reports {hit!r}"
        if not detected:
            time.sleep(3)
    if not detected:
        raise _fail(f"{victim.name} survived a corrupted chain.db for 90s — the fault did not take")
    print(f"[+] corrupt store detected: {detected}")
    _stop_instance(victim)
    genesis = _wipe_store_keep_genesis(root, victim)
    print(f"[*] wiped data/{CHAIN_ID}, restored {genesis.name} — re-initialising and resyncing")
    _spawn(victim, python)
    deadline = time.time() + timeout
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        hv, hh = _head(victim), _head(healthy)
        if hv is not None and hh is not None and hv >= hh:
            bv, bh = _block(victim, hv), _block(healthy, hv)
            if (bv or {}).get("hash") and bv["hash"] == (bh or {}).get("hash"):
                print(f"[+] {victim.name} re-initialised and resynced: head {hv}, hash matches bc2-i0")
                return
        time.sleep(5)
    raise _fail(f"{victim.name} did not resync to the fleet head within {timeout}s")


def phase_rejoin(root: Path, python: str, timeout: int, max_load: float, min_avail_mib: int) -> None:
    inst = instances(root)[3]
    h0 = _head(inst)
    _stop_instance(inst)
    # Fleet MAX_EMPTY_BLOCK_INTERVAL is 60s — sleep past one round so the
    # chain provably advanced while the node was down, then restart it.
    print(f"[*] stopped {inst.name} at head {h0}; waiting one round, then restarting")
    time.sleep(70)
    _spawn(inst, python)
    deadline = time.time() + timeout
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        h = _head(inst)
        if h is not None and h0 is not None and h > h0:
            print(f"[+] {inst.name} rejoined and caught up: {h0} -> {h}")
            return
        time.sleep(3)
    raise _fail(f"{inst.name} did not catch up within {timeout}s")


def phase_skip(root: Path, timeout: int, max_load: float, min_avail_mib: int) -> None:
    inst = instances(root)[2]
    peer = instances(root)[0]
    _stop_instance(inst)
    print(f"[*] stopped {inst.name}; watching whether the rotation skips it")
    deadline = time.time() + timeout
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        h = _head(peer)
        if h is not None and h >= 6:
            print(f"[+] peer head {h} keeps advancing with {inst.name} down")
            return
        time.sleep(3)
    raise _fail(f"head did not advance past 6 with {inst.name} stopped")


def phase_stores(root: Path, python: str) -> None:
    """Fresh SQLite stores: coordinator + trading `alembic upgrade head` once."""
    for svc, app_dir, env in (
        (
            "coordinator",
            REPO_ROOT / "apps" / "coordinator-api",
            {"DATABASE_ADAPTER": "sqlite", "DATABASE_URL": f"sqlite:///{root}/svc/coordinator/coordinator.db"},
        ),
        (
            "trading",
            REPO_ROOT / "apps" / "trading",
            {"DB_TYPE": "sqlite", "DATABASE_URL": f"sqlite+aiosqlite:///{root}/svc/trading/trading.db"},
        ),
    ):
        db_dir = root / "svc" / svc
        db_dir.mkdir(parents=True, exist_ok=True)
        child_env = dict(
            os.environ,
            AITBC_DATA_DIR=str(db_dir),
            # alembic env.py imports the app's own package (e.g.
            # trading_service) — <app>/src must be importable.
            PYTHONPATH=f"{app_dir}/src:{REPO_ROOT}:{REPO_ROOT}/apps/blockchain-node/src",
            **env,
        )
        # Clear inherited live DB env so nothing leaks to the live store.
        for stale in ("DATABASE_URL", "SQLITE_URL", "DB_HOST", "DB_NAME", "DB_USER", "DB_PASS"):
            child_env.pop(stale, None)
        child_env.update(env)
        r = subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=str(app_dir),
            env=child_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            raise _fail(f"alembic upgrade head failed for {svc}:\n{r.stderr[-2000:]}")
        db = next(db_dir.glob("**/*.db"), None)
        if db is None:
            raise _fail(f"{svc}: no .db file produced under {db_dir}")
        tables = _sql(db, "SELECT name FROM sqlite_master WHERE type='table'")
        print(f"[+] {svc} schema initialised: {db} ({len(tables)} tables)")


def phase_golden(root: Path, python: str) -> None:
    # Module-style invocation — runner.py does `from . import engine, profiles`.
    env = dict(
        os.environ,
        AITBC_DATA_DIR=str(root / "golden-data"),
        CHAIN_ID=CHAIN_ID,
        PYTHONPATH=(f"{REPO_ROOT}/apps/blockchain-node/tests:{REPO_ROOT}/apps/blockchain-node/src:{REPO_ROOT}"),
    )
    for run in (1, 2):
        r = subprocess.run(
            [python, "-m", "golden.runner", "check", "--profile", "gates1"],
            cwd=str(REPO_ROOT / "apps" / "blockchain-node"),
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if r.returncode != 0:
            raise _fail(f"golden check (run {run}) failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
        print(f"[+] golden gates1 check run {run}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'ok'}")


def phase_teardown(root: Path) -> None:
    for inst in instances(root):
        _stop_instance(inst)
    subprocess.run(["systemctl", "stop", "bc2-redis"], capture_output=True, timeout=60)
    for inst in instances(root):
        for _ in range(20):
            if _unit_pid(inst.name) is None:
                break
            time.sleep(0.5)
    lock = root / ".lock"
    if lock.exists():
        lock.unlink()
    after = _live_snapshot()
    before_file = root / "live-before.json"
    before = json.loads(before_file.read_text()) if before_file.exists() else {}
    if before and before != after:
        print("[!] live unit snapshot changed during rehearsal — inspect before reporting", file=sys.stderr)
        print(json.dumps({"before": before, "after": after}, indent=2), file=sys.stderr)
    else:
        print("[+] live unit snapshot unchanged (ActiveEnterTimestamp + MainPID)")
    # Delete the whole scratch tree and show it empty.
    shutil.rmtree(root, ignore_errors=True)
    if root.exists():
        raise _fail(f"teardown incomplete — {root} still exists")
    print(f"[+] scratch tree {root} removed; nothing left behind")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "phase",
        choices=[
            "keys",
            "genesis",
            "up",
            "wait",
            "check",
            "timing",
            "rejoin",
            "skip",
            "stall",
            "resync",
            "stores",
            "golden",
            "untrusted",
            "teardown",
            "run",
        ],
    )
    # Scratch defaults to /tmp deliberately: per-rehearsal ephemeral tree,
    # deleted at teardown; the root is resolved and live-prefix-checked.
    p.add_argument("--scratch", default="/tmp/bc2-rehearsal", help="scratch root (default /tmp/bc2-rehearsal)")  # nosec B108
    p.add_argument("--python", default="/opt/aitbc/venv/bin/python", help="repo venv interpreter")
    p.add_argument("--height", type=int, default=6, help="target height for `wait`")
    p.add_argument("--timeout", type=int, default=240, help="seconds for waits")
    p.add_argument("--max-load", type=float, default=DEFAULT_LOAD_CEILING, help="1-min loadavg ceiling")
    p.add_argument("--min-avail-mib", type=int, default=DEFAULT_MIN_AVAIL_MIB, help="MemAvailable floor MiB")
    args = p.parse_args()

    root = scratch_root(args.scratch)

    if args.phase == "keys":
        phase_keys(root)
        return 0
    if args.phase == "genesis":
        _claim_rehearsal(root)
        phase_genesis(root, force=True)
        return 0
    if args.phase == "up":
        _claim_rehearsal(root)
        phase_up(root, args.python, args.max_load, args.min_avail_mib)
        return 0
    if args.phase == "teardown":
        phase_teardown(root)
        return 0

    if args.phase == "run":
        _claim_rehearsal(root)
        wall: list[tuple[str, float]] = []

        def _timed(name: str, fn) -> None:
            t0 = time.monotonic()
            fn()
            wall.append((name, time.monotonic() - t0))

        try:
            before = _live_snapshot()
            (root / "live-before.json").parent.mkdir(parents=True, exist_ok=True)
            (root / "live-before.json").write_text(json.dumps(before, indent=2))
            failures: list[str] = []
            _timed("keys", lambda: phase_keys(root))
            _timed("genesis", lambda: phase_genesis(root))
            _timed("up", lambda: phase_up(root, args.python, args.max_load, args.min_avail_mib))
            _timed("wait", lambda: phase_wait(root, args.height, args.timeout, args.max_load, args.min_avail_mib))
            _timed("check", lambda: failures.extend(phase_check(root)))
            _timed("timing", lambda: phase_timing(root))
            _timed("rejoin", lambda: phase_rejoin(root, args.python, args.timeout, args.max_load, args.min_avail_mib))
            _timed("skip", lambda: phase_skip(root, args.timeout, args.max_load, args.min_avail_mib))
            _timed("stall", lambda: phase_stall(root, args.python, args.timeout, args.max_load, args.min_avail_mib))
            _timed("resync", lambda: phase_resync(root, args.python, args.timeout, args.max_load, args.min_avail_mib))
            _timed("stores", lambda: phase_stores(root, args.python))
            _timed("golden", lambda: phase_golden(root, args.python))
            _timed("untrusted", lambda: phase_untrusted(root, args.python, args.timeout))
            after = _live_snapshot()
            (root / "live-after.json").write_text(json.dumps(after, indent=2))
            print("[+] phase wall-clock: " + ", ".join(f"{n}={d:.1f}s" for n, d in wall) + " (measured: monotonic)")
            if failures:
                print("[!] acceptance failures:", *failures, sep="\n  - ")
                return 1
            print("[+] all acceptance checks passed")
            return 0
        finally:
            phase_teardown(root)

    # Individual check phases
    dispatch = {
        "wait": lambda: phase_wait(root, args.height, args.timeout, args.max_load, args.min_avail_mib),
        "check": lambda: _report(phase_check(root)),
        "timing": lambda: phase_timing(root),
        "rejoin": lambda: phase_rejoin(root, args.python, args.timeout, args.max_load, args.min_avail_mib),
        "skip": lambda: phase_skip(root, args.timeout, args.max_load, args.min_avail_mib),
        "stall": lambda: phase_stall(root, args.python, args.timeout, args.max_load, args.min_avail_mib),
        "resync": lambda: phase_resync(root, args.python, args.timeout, args.max_load, args.min_avail_mib),
        "stores": lambda: phase_stores(root, args.python),
        "golden": lambda: phase_golden(root, args.python),
        "untrusted": lambda: phase_untrusted(root, args.python, args.timeout),
    }
    dispatch[args.phase]()
    return 0


def _report(failures: list[str]) -> None:
    if failures:
        for f in failures:
            print(f"[!] {f}", file=sys.stderr)
        raise SystemExit(1)
    print("[+] all checks passed")


if __name__ == "__main__":
    raise SystemExit(main())
