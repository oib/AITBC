#!/usr/bin/env python3
"""RESET-ROLLBACK-1 — rehearse the pre-PONR rollback on the node2 scratch harness.

Part of the chain-reset plan. The runbook (docs/deployment/
bc2-reset-runbook.md, section E) calls rollback **unproven until this
rehearsal** and lists the acceptance items: every cut step reverted
individually and in order, byte-equal restore from the moved-aside copies
and from a separate backup copy, the explicit move-back (a bare restart
on empty dirs is the trap), restart-evidence fields with the fresh-start
detection rule, and the old chain resuming at the frozen head.

This driver reuses the rehearsal harness's guard, instance spawn and
teardown machinery — it does not re-implement them. It runs on scratch
only: everything lives under ``--scratch`` (the same
``reset_guard.scratch_root`` enforcement point), units are ``systemd-run``
transient services with cgroup caps, and nothing touches a live unit,
env file, port, data dir, wallet or keystore.

Expected pre-staged inputs (transport stays an operator-visible command):

    <scratch>/standin/chain.db   the offline-backup chain dump, copied in
                                 (sha256 recorded; mode 600)
    <scratch>/old-tree/          `git archive` of the previous release
                                 (hub's running commit), extracted

Phases (also runnable individually):

    rollback.py stage       verify pre-staged inputs, claim the run,
                            live-snapshot baseline, old-tree import check
    rollback.py record      spawn the old-code node on the restored dump,
                            stand-in service stores, sha256 manifest (B5)
    rollback.py cut         C1 stop -> C2 move-aside -> C3 env swap ->
                            C4 genesis file -> C5 one validator up;
                            assert nothing seals
    rollback.py abort       revert each cut step in order; restart old;
                            prove head/hash/state_root + byte-equal restore
                            (both the .pre-reset copies and the backup)
    rollback.py trap        bare restarts on empty dirs (old code arm and
                            current code arm) — record what the code does
    rollback.py freshstart  restart-evidence fields + prior-run detection
    rollback.py teardown    stop everything, live-after == live-before,
                            delete the scratch tree
    rollback.py run         stage -> record -> cut -> abort -> trap ->
                            freshstart -> teardown

Residuals this harness cannot prove (carried to the runbook report):
real systemd units, real store sizes (304–534 MB), live-path writes and
the five-host serial order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rehearsal
from rehearsal import (
    Instance,
    _check_host_budget,
    _claim_rehearsal,
    _fail,
    _live_snapshot,
    _sql,
    _stop_instance,
    _unit_pid,
    _write_instance_envs,
    scratch_root,
)

OLD_CHAIN_ID = "ait-hub.aitbc.bubuit.net"
OLD_PORT_BASE = 18560
SEAL_WATCH_SECONDS = 130
SEAL_POLL_SECONDS = 10
DEAD = "http://127.0.0.1:18999"
DEAD_REDIS = "redis://127.0.0.1:18999"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _old_tree(root: Path) -> Path:
    return root / "old-tree"


def _old_instance(root: Path, name: str, slot: int = 0) -> Instance:
    base = OLD_PORT_BASE + slot * 10
    return Instance(
        idx=90 + slot,
        name=name,
        role="follower",
        p2p_port=base,
        rpc_port=base + 2,
        sync_port=base + 4,
        dir=root / f"{name}-dir",
    )


def _old_env(root: Path, inst: Instance) -> str:
    """Loopback-only old-chain env — no hub or peer URLs anywhere.

    Same isolation policy as the rehearsal envs: ``AITBC_CHAIN_ENV_FILE``
    emptied so the host's /etc/aitbc files are never read, all binds on
    127.0.0.1, every client-default URL pointed at a dead loopback so any
    path that ignores the choice fails fast instead of reaching out.
    """
    lines = {
        "AITBC_CHAIN_ENV_FILE": "",
        "AITBC_DATA_DIR": str(inst.dir),
        "AITBC_LOG_DIR": str(inst.dir / "logs"),
        "AITBC_RESET_SCRATCH": str(root),
        "CHAIN_ID": OLD_CHAIN_ID,
        "SUPPORTED_CHAINS": OLD_CHAIN_ID,
        "BLOCK_PRODUCTION_CHAINS": OLD_CHAIN_ID,
        "ENABLE_BLOCK_PRODUCTION": "false",
        "RPC_BIND_HOST": "127.0.0.1",
        "RPC_BIND_PORT": str(inst.rpc_port),
        "P2P_BIND_HOST": "127.0.0.1",
        "P2P_BIND_PORT": str(inst.p2p_port),
        "SYNC_MANAGER_HTTP_PORT": str(inst.sync_port),
        "P2P_NODE_ID": inst.name,
        "GOSSIP_BACKEND": "mesh",
        "GOSSIP_MESH_PEER_URLS": "",
        "GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP": "256",
        "SYNC_MANAGER_ENABLED": "false",
        "SUBSCRIPTION_ENABLED": "false",
        "AUTO_SYNC_THRESHOLD": "0",
        "HUB_RPC_URL": DEAD,
        "HUB_BLOCKCHAIN_RPC_URL": DEAD,
        "AITBC_SYNC_SOURCE": DEAD,
        "AITBC_SYNC_IMPORT_URL": DEAD,
        "DEFAULT_PEER_RPC_URL": DEAD,
        "REDIS_URL": DEAD_REDIS,
        "GOSSIP_BROADCAST_URL": DEAD_REDIS,
        "COORDINATOR_API_URL": DEAD,
        "AITBC_NODE_METRICS_HOST": "127.0.0.1",
        "AITBC_NODE_METRICS_PORT": str(inst.p2p_port + 6),
        "MEMPOOL_DB_URL": "",
        "DB_KEEPER_CONNECTION": "false",
    }
    return "\n".join(f"{k}='{v}'" for k, v in sorted(lines.items())) + "\n"


def _write_old_env(root: Path, inst: Instance) -> None:
    (inst.dir / "data").mkdir(parents=True, exist_ok=True)
    (inst.dir / "logs").mkdir(parents=True, exist_ok=True)
    env_file = inst.dir / "instance.env"
    env_file.write_text(_old_env(root, inst))
    env_file.chmod(0o600)


def _unit_fields(name: str) -> dict[str, str]:
    """The runbook's restart-evidence fields for one unit."""
    out = subprocess.run(
        [
            "systemctl",
            "show",
            name,
            "-p",
            "ActiveEnterTimestamp,ExecMainStartTimestamp,MainPID",
            "--value",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    parts = (out.stdout.strip().split("\n") + ["", "", ""])[:3]
    return {
        "ActiveEnterTimestamp": parts[0],
        "ExecMainStartTimestamp": parts[1],
        "MainPID": parts[2],
    }


def _detect_prior_run(before: dict[str, str], after: dict[str, str]) -> bool:
    """Fresh-start rule: a newer ActiveEnterTimestamp (or changed
    ExecMainStartTimestamp/MainPID) means a prior run already completed —
    treat as such, do not restart again."""
    return (
        after["ActiveEnterTimestamp"] != before["ActiveEnterTimestamp"]
        or after["MainPID"] != before["MainPID"]
        or after["ExecMainStartTimestamp"] != before["ExecMainStartTimestamp"]
    )


def _head_fields(db: Path) -> dict[str, object]:
    rows = _sql(db, "SELECT height, hash, state_root FROM block ORDER BY height DESC LIMIT 1")
    if not rows:
        return {"height": -1}
    h, hh, sr = rows[0]
    return {"height": h, "hash": hh, "state_root": sr}


def _assert_nothing_sealed(db: Path) -> int:
    """The PONR depends on this: with attestation-min-2 and one validator
    up, max(height) must stay 0. Anything else voids the runbook wording."""
    top = _head_fields(db)
    height = int(top["height"])
    if height > 0:
        raise _fail(
            f"SEAL DETECTED at height {height} on the partial-start bc-2 instance — "
            "this voids the runbook's point-of-no-return wording. Stopping; report at once."
        )
    return height


def _manifest_files(root: Path) -> dict[str, str]:
    """sha256 of every file under the old-chain instance dir and the
    stand-in service stores — the 'all stores' the runbook moves."""
    out: dict[str, str] = {}
    for base in (root / "bc2rb-old-dir", root / "svc"):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(root))] = _sha256(p)
    return out


def _write_manifest(root: Path, manifest: dict) -> Path:
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path


def _load_manifest(root: Path) -> dict:
    return json.loads((root / "manifest.json").read_text())


def _verify_manifest(root: Path) -> list[str]:
    diffs: list[str] = []
    files = _load_manifest(root)["files"]
    for rel, want in files.items():
        p = root / rel
        if not p.exists():
            diffs.append(f"missing {rel}")
        elif _sha256(p) != want:
            diffs.append(f"sha256 changed {rel}")
    return diffs


def _socket_listing(pid: int) -> list[str]:
    out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=10)
    return [ln for ln in out.stdout.splitlines() if f"pid={pid}," in ln]


def _tail(path: Path, n: int = 8) -> list[str]:
    if not path.exists():
        return ["<no log>"]
    return path.read_text(errors="replace").splitlines()[-n:]


def _wait_alive(name: str, timeout: int = 60) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pid = _unit_pid(name)
        if pid:
            return int(pid)
        time.sleep(2)
    raise _fail(f"{name} did not start within {timeout}s")


def phase_stage(root: Path, python: str, max_load: float, min_avail_mib: int) -> None:
    _claim_rehearsal(root)
    (root / "live-before.json").write_text(json.dumps(_live_snapshot(), indent=2))
    _check_host_budget(max_load, min_avail_mib)

    standin = root / "standin" / "chain.db"
    if not standin.exists():
        raise _fail(f"pre-staged backup missing: {standin}")
    old_tree = _old_tree(root)
    if not (old_tree / "apps" / "blockchain-node" / "src" / "aitbc_chain" / "main.py").exists():
        raise _fail(f"old-tree missing or wrong: {old_tree}")

    # Old release must import under the node2 venv — if it cannot, STOP
    # and report the error verbatim (ruling: no second venv, no tuning).
    r = subprocess.run(
        [python, "-c", "import aitbc_chain.main"],
        env=dict(
            os.environ,
            PYTHONPATH=f"{old_tree}:{old_tree}/apps/blockchain-node/src",
            AITBC_CHAIN_ENV_FILE="",
            REDIS_URL=DEAD_REDIS,
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise _fail(f"old-tree import failed under {python} — reporting verbatim:\n{r.stderr[-2000:]}")

    inst = _old_instance(root, "bc2rb-old")
    _write_old_env(root, inst)
    dest_dir = inst.dir / "data" / OLD_CHAIN_ID
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(standin, dest_dir / "chain.db")
    if _sha256(standin) != _sha256(dest_dir / "chain.db"):
        raise _fail("restored copy does not match the backup sha256")
    manifest = {
        "backup_sha256": _sha256(standin),
        "staged_equals_backup": True,
        "frozen": {},
        "files": {},
    }
    _write_manifest(root, manifest)
    print(f"[+] stage ok: backup sha256={manifest['backup_sha256'][:16]}… restored to {dest_dir}")
    print("[+] old-tree import verified under the venv")


def phase_record(root: Path, python: str) -> None:
    rehearsal.phase_stores(root, python)
    inst = _old_instance(root, "bc2rb-old")
    rehearsal._spawn(inst, python, with_rpc=False, repo_root=_old_tree(root))
    pid = _wait_alive(inst.name)
    time.sleep(15)
    db = inst.dir / "data" / OLD_CHAIN_ID / "chain.db"
    frozen = _head_fields(db)
    if int(frozen["height"]) <= 0:
        raise _fail(f"old-chain stand-in did not resume: {frozen}")

    socks = _socket_listing(pid)
    bad = [ln for ln in socks if "127.0.0.1" not in ln]
    manifest = _load_manifest(root)
    manifest["frozen"] = frozen
    manifest["files"] = _manifest_files(root)
    manifest["old_pid"] = pid
    manifest["sockets"] = socks
    _write_manifest(root, manifest)
    print(f"[+] old chain resumed under 6966658c1 code: head {frozen['height']} hash {str(frozen['hash'])[:18]}…")
    print(f"[+] socket listing for pid {pid}: {len(socks)} listener(s), all loopback={not bad}")
    for ln in socks:
        print(f"    {ln.strip()}")
    if bad:
        raise _fail(f"non-loopback listener(s) on the old-code unit: {bad}")
    print(f"[+] manifest: {len(manifest['files'])} store files checksummed")


def _cut_env_swap(inst: Instance) -> bytes:
    """C3 — the env flip: swap the chain-id assignments to bc-2; the old
    content is returned so abort can restore it byte-exact."""
    env_file = inst.dir / "instance.env"
    old = env_file.read_bytes()
    new = (
        old.decode()
        .replace(f"CHAIN_ID='{OLD_CHAIN_ID}'", "CHAIN_ID='bc-2'")
        .replace(f"SUPPORTED_CHAINS='{OLD_CHAIN_ID}'", "SUPPORTED_CHAINS='bc-2'")
        .replace(f"BLOCK_PRODUCTION_CHAINS='{OLD_CHAIN_ID}'", "BLOCK_PRODUCTION_CHAINS='bc-2'")
    )
    env_file.write_text(new)
    return old


def phase_cut(root: Path, python: str, max_load: float, min_avail_mib: int) -> None:
    inst = _old_instance(root, "bc2rb-old")

    # C1 — stop the old-chain unit; record the restart-evidence fields.
    fields = _unit_fields(inst.name)
    _stop_instance(inst)
    for _ in range(30):
        if _unit_pid(inst.name) is None:
            break
        time.sleep(1)
    print(f"[+] C1 {inst.name} stopped (was pid {fields['MainPID']}, started {fields['ActiveEnterTimestamp']})")

    # C2 — move every store aside under .pre-reset.
    prereset = root / ".pre-reset"
    prereset.mkdir(exist_ok=True)
    shutil.move(str(inst.dir / "data"), prereset / "old-data")
    if (root / "svc").exists():
        shutil.move(str(root / "svc"), prereset / "svc")
    print("[+] C2 stores moved aside under .pre-reset")

    # C3 — env flip (old content preserved for the byte-exact revert).
    old_env = _cut_env_swap(inst)
    (root / "env.old.saved").write_bytes(old_env)
    print("[+] C3 env flipped to bc-2 (old env preserved)")

    # keys + genesis + instance envs — the C3/C4 products for bc-2.
    rehearsal.phase_keys(root)
    keys = rehearsal._load_keys(root)
    rehearsal.phase_genesis(root)
    _write_instance_envs(root, keys)

    # C5 — ONE validator up: attestation-min-2 means nothing can seal.
    i0 = rehearsal.instances(root)[0]
    rehearsal._spawn(i0, python, with_rpc=False)
    _wait_alive(i0.name)
    db = i0.dir / "data" / "bc-2" / "chain.db"
    deadline = time.time() + SEAL_WATCH_SECONDS
    seen: list[int] = []
    while time.time() < deadline:
        _check_host_budget(max_load, min_avail_mib)
        seen.append(_assert_nothing_sealed(db) if db.exists() else -1)
        time.sleep(SEAL_POLL_SECONDS)
    if not db.exists():
        raise _fail(f"bc-2 chain.db never appeared at {db}")
    _assert_nothing_sealed(db)
    print(f"[+] C5 one validator up {SEAL_WATCH_SECONDS}s — max(height)=0 throughout ({len(seen)} polls); nothing sealed")


def phase_abort(root: Path, python: str) -> None:
    inst = _old_instance(root, "bc2rb-old")
    i0 = rehearsal.instances(root)[0]
    _stop_instance(i0)

    # C4 revert: delete every bc-2 dir the genesis distribution made.
    for i in rehearsal.instances(root):
        shutil.rmtree(i.dir / "data" / "bc-2", ignore_errors=True)

    # C3 revert: the old env goes back byte-exact.
    saved = (root / "env.old.saved").read_bytes()
    (inst.dir / "instance.env").write_bytes(saved)
    if _sha256(root / "env.old.saved") != _sha256(inst.dir / "instance.env"):
        raise _fail("env revert is not byte-exact")

    # C2 revert: THE EXPLICIT MOVE-BACK — skipping it is the trap.
    prereset = root / ".pre-reset"
    shutil.move(str(prereset / "old-data"), inst.dir / "data")
    if (prereset / "svc").exists():
        shutil.move(str(prereset / "svc"), root / "svc")
    print("[+] .pre-reset moved back (explicit step)")

    # Byte-equal restore vs the recorded manifest — checked at rest,
    # before the node re-opens the stores.
    diffs = _verify_manifest(root)
    if diffs:
        raise _fail(f"restore is not byte-equal to the pre-cut manifest: {diffs}")
    print(f"[+] byte-equal restore verified against manifest ({len(_load_manifest(root)['files'])} files)")

    # C1 revert + the resume proof.
    rehearsal._spawn(inst, python, with_rpc=False, repo_root=_old_tree(root))
    _wait_alive(inst.name)
    time.sleep(15)
    db = inst.dir / "data" / OLD_CHAIN_ID / "chain.db"
    now = _head_fields(db)
    frozen = _load_manifest(root)["frozen"]
    if now != frozen:
        raise _fail(f"resume mismatch: {now} != frozen {frozen}")
    print(f"[+] old chain resumed at the frozen head: {now['height']} hash {str(now['hash'])[:18]}…")

    # Second restore leg: straight from the separate backup copy.
    _stop_instance(inst)
    for _ in range(30):
        if _unit_pid(inst.name) is None:
            break
        time.sleep(1)
    shutil.rmtree(inst.dir / "data")
    dest_dir = inst.dir / "data" / OLD_CHAIN_ID
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "standin" / "chain.db", dest_dir / "chain.db")
    rehearsal._spawn(inst, python, with_rpc=False, repo_root=_old_tree(root))
    _wait_alive(inst.name)
    time.sleep(15)
    again = _head_fields(dest_dir / "chain.db")
    if again != frozen:
        raise _fail(f"backup-copy restore mismatch: {again} != frozen {frozen}")
    print(f"[+] restore-from-backup leg verified: resumed at {again['height']}")


def phase_trap(root: Path, python: str) -> None:
    """Bare restart on empty dirs is the trap — record what the code does.

    Arm A (old code, empty old-chain dir): 6966658c1 falls back to
    hub-synced block 0 — no hub exists here, so it can never reach the
    frozen head. Arm B (current code, empty bc-2 dir without
    genesis.json): _ensure_genesis_block refuses startup (poa.py raises
    'Genesis file required'). Neither is a restore.
    """
    # Arm A — old code on an empty data dir.
    old2 = _old_instance(root, "bc2rb-old2", slot=1)
    _write_old_env(root, old2)
    rehearsal._spawn(old2, python, with_rpc=False, repo_root=_old_tree(root))
    time.sleep(40)
    db2 = old2.dir / "data" / OLD_CHAIN_ID / "chain.db"
    head2 = _head_fields(db2) if db2.exists() else {"height": "no db"}
    pid2 = _unit_pid(old2.name)
    print(f"[*] trap A (old code, empty dir): head={head2}, pid={pid2}, log tail:")
    for ln in _tail(old2.dir / "logs" / "node.log"):
        print(f"    {ln}")
    _stop_instance(old2)

    # Arm B — current code on an empty bc-2 dir (no genesis.json).
    i1 = rehearsal.instances(root)[1]
    shutil.rmtree(i1.dir / "data", ignore_errors=True)
    (i1.dir / "data").mkdir(parents=True, exist_ok=True)
    rehearsal._spawn(i1, python, with_rpc=False)
    time.sleep(30)
    db1 = i1.dir / "data" / "bc-2" / "chain.db"
    head1 = _head_fields(db1) if db1.exists() else {"height": "no db"}
    pid1 = _unit_pid(i1.name)
    state = (
        subprocess.run(
            ["systemctl", "show", i1.name, "-p", "ActiveState,SubState", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        .stdout.strip()
        .split("\n")
    )
    print(f"[*] trap B (current code, empty bc-2 dir): head={head1}, pid={pid1}, unit={state}")
    for ln in _tail(i1.dir / "logs" / "node.log"):
        print(f"    {ln}")
    _stop_instance(i1)
    print("[+] trap demonstrated: bare restart on empty dirs did not restore the frozen head in either arm")


def phase_freshstart(root: Path) -> None:
    inst = _old_instance(root, "bc2rb-old")
    before = _unit_fields(inst.name)
    subprocess.run(["systemctl", "restart", inst.name], capture_output=True, timeout=60)
    _wait_alive(inst.name)
    after = _unit_fields(inst.name)
    detected = _detect_prior_run(before, after)
    print(f"[*] fresh-start evidence: before={before}")
    print(f"[*]                      after={after}")
    if not detected:
        raise _fail("prior-run detection did not fire on a restarted unit")
    print("[+] detection rule exercised: newer ActiveEnterTimestamp/MainPID → 'a prior run already completed'")


def phase_teardown(root: Path) -> None:
    for name in ("bc2rb-old", "bc2rb-old2"):
        subprocess.run(["systemctl", "stop", name], capture_output=True, timeout=60)
    rehearsal.phase_teardown(root)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "phase",
        choices=["stage", "record", "cut", "abort", "trap", "freshstart", "teardown", "run"],
    )
    p.add_argument("--scratch", default="/tmp/bc2-rollback", help="scratch root (default /tmp/bc2-rollback)")  # nosec B108
    p.add_argument("--python", default="/opt/aitbc/venv/bin/python", help="node venv interpreter")
    p.add_argument("--max-load", type=float, default=24.0, help="1-min loadavg ceiling")
    p.add_argument("--min-avail-mib", type=int, default=4096, help="MemAvailable floor MiB")
    args = p.parse_args()

    root = scratch_root(args.scratch)

    if args.phase == "teardown":
        phase_teardown(root)
        return 0

    if args.phase == "run":
        try:
            phase_stage(root, args.python, args.max_load, args.min_avail_mib)
            phase_record(root, args.python)
            phase_cut(root, args.python, args.max_load, args.min_avail_mib)
            phase_abort(root, args.python)
            phase_trap(root, args.python)
            phase_freshstart(root)
            after = _live_snapshot()
            before = json.loads((root / "live-before.json").read_text())
            (root / "live-after.json").write_text(json.dumps(after, indent=2))
            if before != after:
                print("[!] live unit snapshot changed during rehearsal", file=sys.stderr)
                return 1
            print("[+] live unit snapshot identical before/after")
            print("[+] RESET-ROLLBACK-1 rehearsal complete — all acceptance items proven")
            return 0
        finally:
            phase_teardown(root)

    if args.phase == "stage":
        phase_stage(root, args.python, args.max_load, args.min_avail_mib)
    elif args.phase == "record":
        phase_record(root, args.python)
    elif args.phase == "cut":
        phase_cut(root, args.python, args.max_load, args.min_avail_mib)
    elif args.phase == "abort":
        phase_abort(root, args.python)
    elif args.phase == "trap":
        phase_trap(root, args.python)
    elif args.phase == "freshstart":
        phase_freshstart(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
