#!/usr/bin/env python3
"""bc-2 dress-rehearsal harness — five scratch node processes on one host.

Part of the chain-reset plan (RESET-GENESIS-HARNESS-1). Builds a `bc-2`
genesis with ``scripts/ops/build-genesis.py`` + ``aitbc_chain.genesis_builder``
(treasury 100M AIT + 256 AIT working floats, 5 authority chain parameters,
4 bridge validators = the rehearsal proposers), launches four proposer
instances plus one customer-style follower as ``systemd-run`` transient units
processes with per-instance data dirs, loopback ports and cgroup caps, and
runs the acceptance checks: identical block-0 hash, proposer rotation, PBFT
3-of-4 certificates, restart/rejoin, stopped-proposer skip, fresh SQLite
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
    rehearsal.py rejoin      stop i3, restart it, prove catch-up + slot resume
    rehearsal.py skip        stop i2, prove the rotation skips it
    rehearsal.py stores      coordinator + trading `alembic upgrade head` on
                             scratch SQLite stores
    rehearsal.py golden      run the golden-corpus check twice under gates1
    rehearsal.py teardown    stop units, delete the scratch tree, show it empty
    rehearsal.py run         keys -> genesis -> up -> wait -> check ->
                             rejoin -> skip -> stores -> golden -> teardown

Live-host protection: before anything starts, the harness records
``ActiveEnterTimestamp``/``MainPID`` and head height of the live
aitbc-blockchain-node unit and node2's load/memory; it refuses (and tears
down) when the 1-min load average exceeds ``--max-load`` or available memory
drops below ``--min-avail-mib``, and it refuses to run two rehearsals at
once (a ``<scratch>/.lock`` plus a systemd unit-name check).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "blockchain-node" / "src"), str(REPO_ROOT / "cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

FORBIDDEN_PREFIXES = (Path("/var/lib/aitbc"), Path("/etc/aitbc"), Path("/root"))
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


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def scratch_root(raw: str) -> Path:
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise _fail(f"--scratch must be an absolute path: {raw}")
    resolved = root.resolve()
    for prefix in FORBIDDEN_PREFIXES:
        if _under(resolved, prefix):
            raise _fail(f"scratch root {resolved} is inside live path {prefix} — refusing")
    return resolved


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
    """The two zero-balance accounts init_db always creates
    (``ensure_bond_accounts``): bond escrow + bond burn, keccak-derived.
    They must be in the allocation set or the live post-init state root
    never matches the genesis claim (parent-state-mismatch on block 1)."""
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
    host's ``/etc/aitbc/blockchain.env``. ``REDIS_URL`` points at a dead
    loopback port: rehearsal gossip is mesh; a real live redis must never
    carry it, and if any code path still opens redis it fails fast.
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
        "GOSSIP_AUTH_ENABLED": "false",  # rehearsal mesh on loopback only
        "MULTI_VALIDATOR_CONSENSUS_ENABLED": "true",
        "MULTI_VALIDATOR_MIN_ATTESTATIONS": "2",
        "MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS": "3",
        "PBFT_CONSENSUS_ENABLED": "true",
        "VALIDATOR_SET": validator_set,
        "BRIDGE_MULTISIG_ENABLED": "true",
        "BRIDGE_MULTISIG_THRESHOLD": "2",
        "ENABLE_BLOCK_PRODUCTION": "true" if inst.role == "proposer" else "false",
        "MAX_EMPTY_BLOCK_INTERVAL": "10",
        "CONSENSUS_PROPOSER_ROUND_SECONDS": "10",
        "DEFAULT_PEER_RPC_URL": f"http://127.0.0.1:{PORT_BASE + 2}",
        "TRUSTED_PROPOSERS": "genesis",
        "SYNC_MANAGER_ENABLED": "true",
        "SYNC_STATE_ROOT_VALIDATION_ENABLED": "true",
        "SUBSCRIPTION_ENABLED": "false",
        # Dead loopback ports for every live-adjacent client default — anything
        # that ignores our backend choice fails fast rather than touching the
        # live redis (6379), coordinator (8203), hub RPC (8202) or metrics (9009).
        "REDIS_URL": REHEARSAL_REDIS_URL,
        "GOSSIP_BROADCAST_URL": REHEARSAL_REDIS_URL,
        "COORDINATOR_API_URL": "http://127.0.0.1:18203",
        "HUB_RPC_URL": "http://127.0.0.1:18202",
        "HUB_BLOCKCHAIN_RPC_URL": "http://127.0.0.1:18202",
        "AITBC_SYNC_SOURCE": "http://127.0.0.1:18202",
        "AITBC_SYNC_IMPORT_URL": "http://127.0.0.1:18202",
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


def _live_snapshot() -> dict[str, dict[str, str]]:
    snap: dict[str, dict[str, str]] = {}
    for unit in LIVE_UNITS:
        out = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveEnterTimestamp,MainPID", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        parts = (out.stdout.strip().split("\n") + ["", ""])[:2]
        snap[unit] = {"ActiveEnterTimestamp": parts[0], "MainPID": parts[1]}
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


def _spawn(inst: Instance, python: str) -> None:
    env_file = inst.dir / "instance.env"
    # PYTHONPATH mirrors the live unit; HOME is the instance dir, never
    # /var/lib/aitbc.
    prelude = (
        f"export HOME={inst.dir} PYTHONPATH={REPO_ROOT}:{REPO_ROOT}/apps/blockchain-node/src; set -a; . {env_file}; set +a; "
    )
    # Consensus/production process (mirrors aitbc-blockchain-node) + the RPC
    # service (mirrors aitbc-blockchain-rpc: uvicorn aitbc_chain.app:app).
    units = (
        (inst.name, f"exec {python} -m aitbc_chain.main >>{inst.dir}/logs/node.log 2>&1"),
        (
            f"{inst.name}-rpc",
            f"exec {python} -m uvicorn aitbc_chain.app:app --host 127.0.0.1 --port {inst.rpc_port} "
            f"--workers 1 --log-level warning --timeout-graceful-shutdown 3 "
            f">>{inst.dir}/logs/rpc.log 2>&1",
        ),
    )
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


def phase_up(root: Path, python: str, max_load: float, min_avail_mib: int) -> None:
    before = _live_snapshot()
    (root / "live-before.json").write_text(json.dumps(before, indent=2))
    _check_host_budget(max_load, min_avail_mib)
    keys = _load_keys(root)
    _write_instance_envs(root, keys)
    _spawn_redis(root)
    for inst in instances(root):
        _spawn(inst, python)
        print(f"[+] {inst.name} ({inst.role}) up: rpc=127.0.0.1:{inst.rpc_port} dir={inst.dir}")
        time.sleep(1)


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


def _sql(db: Path, query: str) -> list[tuple]:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        return conn.execute(query).fetchall()


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
    return _sql(
        db,
        "SELECT height, proposer, block_metadata FROM block WHERE chain_id=? AND height>0 ORDER BY height",
        (CHAIN_ID,),
    )


def _check_certificates_and_rotation(root: Path, rows: list[tuple], failures: list[str]) -> None:
    cert_heights = 0
    proposers_seen: set[str] = set()
    for _height, proposer, meta in rows:
        m = json.loads(meta or "{}")
        cert = m.get("pbft_certificate") or []
        if len(cert) >= 3:
            cert_heights += 1
        if proposer:
            proposers_seen.add(proposer.lower())
    if rows and cert_heights == 0:
        failures.append("no pbft_certificate with >=3 commits found on any produced block")
    else:
        print(f"[+] pbft certificates >=3 commits on {cert_heights}/{len(rows)} produced blocks")

    key_file = root / "keystore" / "keys.json"
    want = {k["address"].lower() for k in json.loads(key_file.read_text())["proposers"]}
    unknown = proposers_seen - want
    if unknown:
        failures.append(f"blocks sealed by addresses outside VALIDATOR_SET: {sorted(unknown)}")
    elif len(proposers_seen) < N_PROPOSERS:
        failures.append(f"only {len(proposers_seen)}/{N_PROPOSERS} proposers sealed a block so far")
    else:
        print(f"[+] rotation: all {N_PROPOSERS} proposers sealed blocks")


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
    _check_certificates_and_rotation(root, rows, failures)
    return failures


def _stop_instance(inst: Instance) -> None:
    subprocess.run(["systemctl", "stop", inst.name], capture_output=True, timeout=60)
    subprocess.run(["systemctl", "stop", f"{inst.name}-rpc"], capture_output=True, timeout=60)


def phase_rejoin(root: Path, python: str, timeout: int, max_load: float, min_avail_mib: int) -> None:
    inst = instances(root)[3]
    h0 = _head(inst)
    _stop_instance(inst)
    print(f"[*] stopped {inst.name} at head {h0}; waiting one round, then restarting")
    time.sleep(12)
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
        child_env = dict(os.environ, AITBC_DATA_DIR=str(db_dir), **env)
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
    runner = REPO_ROOT / "apps" / "blockchain-node" / "tests" / "golden" / "runner.py"
    env = dict(os.environ, AITBC_DATA_DIR=str(root / "golden-data"), CHAIN_ID=CHAIN_ID)
    for run in (1, 2):
        r = subprocess.run(
            [python, str(runner), "check", "--profile", "gates1"],
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
            "rejoin",
            "skip",
            "stores",
            "golden",
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
        try:
            before = _live_snapshot()
            (root / "live-before.json").parent.mkdir(parents=True, exist_ok=True)
            (root / "live-before.json").write_text(json.dumps(before, indent=2))
            phase_keys(root)
            phase_genesis(root)
            phase_up(root, args.python, args.max_load, args.min_avail_mib)
            phase_wait(root, args.height, args.timeout, args.max_load, args.min_avail_mib)
            failures = phase_check(root)
            phase_rejoin(root, args.python, args.timeout, args.max_load, args.min_avail_mib)
            phase_skip(root, args.timeout, args.max_load, args.min_avail_mib)
            phase_stores(root, args.python)
            phase_golden(root, args.python)
            after = _live_snapshot()
            (root / "live-after.json").write_text(json.dumps(after, indent=2))
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
        "rejoin": lambda: phase_rejoin(root, args.python, args.timeout, args.max_load, args.min_avail_mib),
        "skip": lambda: phase_skip(root, args.timeout, args.max_load, args.min_avail_mib),
        "stores": lambda: phase_stores(root, args.python),
        "golden": lambda: phase_golden(root, args.python),
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
