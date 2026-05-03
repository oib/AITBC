#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_DIR = Path("/opt/aitbc")
BLOCKCHAIN_SRC = REPO_DIR / "apps" / "blockchain-node" / "src"
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
if str(BLOCKCHAIN_SRC) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_SRC))

from sqlmodel import Session, create_engine, select
from sqlalchemy.exc import SQLAlchemyError

from aitbc_chain.config import ChainSettings
from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.state.merkle_patricia_trie import StateManager

SERVICE_NAME = "aitbc-blockchain-node.service"
DATA_ROOT = Path("/var/lib/aitbc/data")
BACKUP_ROOT = Path("/var/lib/aitbc/backups/mpt-regeneration")
ENV_FILES = [Path("/etc/aitbc/.env"), Path("/etc/aitbc/node.env")]


def _run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def _service_state(service_name: str) -> dict[str, Any]:
    active = _run(["systemctl", "is-active", service_name]).stdout.strip()
    enabled = _run(["systemctl", "is-enabled", service_name]).stdout.strip()
    fragment = _run(["systemctl", "show", service_name, "-p", "FragmentPath", "--value"]).stdout.strip()
    dropins = _run(["systemctl", "show", service_name, "-p", "DropInPaths", "--value"]).stdout.strip()
    return {
        "active": active,
        "enabled": enabled,
        "fragment_path": fragment,
        "drop_in_paths": [item for item in dropins.split() if item],
    }


def _git_revision() -> str | None:
    result = _run(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_genesis(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as handle:
        return json.load(handle)


def _allocation_digest(genesis: dict[str, Any]) -> str | None:
    allocations = genesis.get("allocations")
    if allocations is None:
        return None
    canonical = json.dumps(sorted(allocations, key=lambda item: item.get("address", "")), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _live_db_files(chain_id: str) -> list[Path]:
    chain_dir = DATA_ROOT / chain_id
    files = [
        chain_dir / "chain.db",
        chain_dir / "chain.db-wal",
        chain_dir / "chain.db-shm",
        chain_dir / "chain.db-journal",
        DATA_ROOT / "mempool.db",
        DATA_ROOT / "mempool.db-wal",
        DATA_ROOT / "mempool.db-shm",
        DATA_ROOT / "mempool.db-journal",
        chain_dir / "mempool.db",
        chain_dir / "mempool.db-wal",
        chain_dir / "mempool.db-shm",
        chain_dir / "mempool.db-journal",
    ]
    return [path for path in files if path.exists()]


def _backup_sources(chain_id: str) -> list[Path]:
    chain_dir = DATA_ROOT / chain_id
    sources: list[Path] = []
    for pattern in [str(chain_dir / "chain.db*"), str(chain_dir / "genesis.json"), str(DATA_ROOT / "mempool.db*"), str(chain_dir / "mempool.db*")]:
        sources.extend(Path(path) for path in glob.glob(pattern))
    sources.extend(path for path in ENV_FILES if path.exists())
    unique: dict[str, Path] = {}
    for path in sources:
        if path.exists():
            unique[str(path)] = path
    return [unique[key] for key in sorted(unique)]


def _integrity_check(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"error: {exc}"


def _db_snapshot(chain_id: str, db_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {
        "db_error": None,
        "head": None,
        "block_count": None,
        "transaction_count": None,
        "account_count": None,
        "computed_state_root": None,
        "head_state_root_matches_computed": None,
    }
    if not db_path.exists() or db_path.stat().st_size == 0:
        data["db_error"] = "database missing or empty"
        return data

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    try:
        with Session(engine) as session:
            head = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()
            blocks = session.exec(select(Block).where(Block.chain_id == chain_id)).all()
            transactions = session.exec(select(Transaction).where(Transaction.chain_id == chain_id)).all()
            accounts = session.exec(select(Account).where(Account.chain_id == chain_id).order_by(Account.address)).all()
            account_dict = {account.address: account for account in accounts}
            computed_root = StateManager().compute_state_root(account_dict)
            computed_root_hex = "0x" + computed_root.hex()
            data.update(
                {
                    "head": None if head is None else {
                        "height": head.height,
                        "hash": head.hash,
                        "state_root": head.state_root,
                        "proposer": head.proposer,
                        "timestamp": head.timestamp.isoformat() if head.timestamp else None,
                    },
                    "block_count": len(blocks),
                    "transaction_count": len(transactions),
                    "account_count": len(accounts),
                    "account_digest": hashlib.sha256(json.dumps(
                        [{"address": account.address, "balance": account.balance, "nonce": account.nonce} for account in accounts],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()).hexdigest(),
                    "computed_state_root": computed_root_hex,
                    "head_state_root_matches_computed": bool(head and head.state_root == computed_root_hex),
                }
            )
    except SQLAlchemyError as exc:
        data["db_error"] = str(exc)
    finally:
        engine.dispose()
    return data


def snapshot(chain_id: str, service_name: str) -> dict[str, Any]:
    settings = ChainSettings()
    db_path = settings.get_db_path(chain_id)
    genesis_path = DATA_ROOT / chain_id / "genesis.json"
    genesis = _load_genesis(genesis_path)
    data: dict[str, Any] = {
        "host": socket.gethostname(),
        "chain_id": chain_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_revision": _git_revision(),
        "service": _service_state(service_name),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "db_size_bytes": db_path.stat().st_size if db_path.exists() else None,
        "db_integrity": _integrity_check(db_path),
        "genesis_path": str(genesis_path),
        "genesis_exists": genesis_path.exists(),
        "genesis_file_sha256": _sha256_file(genesis_path),
        "genesis_allocation_digest": _allocation_digest(genesis),
        "genesis_allocation_count": len(genesis.get("allocations", [])) if genesis else 0,
        "live_db_files": [str(path) for path in _live_db_files(chain_id)],
    }
    data.update(_db_snapshot(chain_id, db_path))
    return data


def backup(chain_id: str, service_name: str, backup_root: Path, timestamp: str | None) -> dict[str, Any]:
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_root / stamp / socket.gethostname() / chain_id
    target.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "host": socket.gethostname(),
        "chain_id": chain_id,
        "timestamp": stamp,
        "target": str(target),
        "preflight": snapshot(chain_id, service_name),
        "files": [],
    }
    for source in _backup_sources(chain_id):
        rel = source.relative_to(source.anchor)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest["files"].append(
            {
                "source": str(source),
                "backup": str(destination),
                "size_bytes": source.stat().st_size,
                "sha256": _sha256_file(source),
                "integrity_check": _integrity_check(destination) if source.name.startswith("chain.db") or source.name.startswith("mempool.db") else None,
            }
        )
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return manifest


def reset(chain_id: str, service_name: str, yes: bool, force: bool) -> dict[str, Any]:
    if not yes:
        raise SystemExit("reset requires --yes")
    service = _service_state(service_name)
    if service["active"] == "active" and not force:
        raise SystemExit(f"{service_name} is active; stop it first or pass --force")
    removed: list[str] = []
    for path in _live_db_files(chain_id):
        path.unlink()
        removed.append(str(path))
    return {"host": socket.gethostname(), "chain_id": chain_id, "removed": removed}


def set_role(chain_id: str, service_name: str, role: str) -> dict[str, Any]:
    dropin_dir = Path("/etc/systemd/system") / f"{service_name}.d"
    dropin_path = dropin_dir / "mpt-regeneration.conf"
    if role == "clear":
        if dropin_path.exists():
            dropin_path.unlink()
        _run(["systemctl", "daemon-reload"], check=True)
        return {"host": socket.gethostname(), "role": role, "dropin": str(dropin_path), "exists": dropin_path.exists()}
    dropin_dir.mkdir(parents=True, exist_ok=True)
    if role == "leader":
        content = (
            "[Service]\n"
            'Environment="AITBC_FORCE_ENABLE_BLOCK_PRODUCTION=true"\n'
            f'Environment="AITBC_FORCE_BLOCK_PRODUCTION_CHAINS={chain_id}"\n'
            'Environment="ENABLE_BLOCK_PRODUCTION=true"\n'
            'Environment="enable_block_production=true"\n'
            f'Environment="BLOCK_PRODUCTION_CHAINS={chain_id}"\n'
            f'Environment="block_production_chains={chain_id}"\n'
        )
    elif role == "follower":
        content = (
            "[Service]\n"
            'Environment="AITBC_FORCE_ENABLE_BLOCK_PRODUCTION=false"\n'
            'Environment="AITBC_FORCE_BLOCK_PRODUCTION_CHAINS="\n'
            'Environment="ENABLE_BLOCK_PRODUCTION=false"\n'
            'Environment="enable_block_production=false"\n'
            'Environment="BLOCK_PRODUCTION_CHAINS="\n'
            'Environment="block_production_chains="\n'
        )
    else:
        raise SystemExit(f"unsupported role: {role}")
    dropin_path.write_text(content)
    _run(["systemctl", "daemon-reload"], check=True)
    return {"host": socket.gethostname(), "role": role, "dropin": str(dropin_path), "exists": dropin_path.exists()}


def verify(chain_id: str, service_name: str, require_nonzero_root: bool) -> dict[str, Any]:
    data = snapshot(chain_id, service_name)
    head = data.get("head")
    ok = data.get("db_error") is None and head is not None and data.get("head_state_root_matches_computed") is True
    if require_nonzero_root and data.get("computed_state_root") == "0x" + ("00" * 32):
        ok = False
    data["ok"] = ok
    return data


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="AITBC coordinated MPT chain regeneration node utility")
    parser.add_argument("--chain-id", default="ait-mainnet")
    parser.add_argument("--service-name", default=SERVICE_NAME)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight")

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    backup_parser.add_argument("--timestamp")

    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--yes", action="store_true")
    reset_parser.add_argument("--force", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--require-nonzero-root", action="store_true")

    role_parser = subparsers.add_parser("set-role")
    role_parser.add_argument("role", choices=["leader", "follower", "clear"])

    args = parser.parse_args()

    if args.command == "preflight":
        print_json(snapshot(args.chain_id, args.service_name))
    elif args.command == "backup":
        print_json(backup(args.chain_id, args.service_name, args.backup_root, args.timestamp))
    elif args.command == "reset":
        print_json(reset(args.chain_id, args.service_name, args.yes, args.force))
    elif args.command == "verify":
        result = verify(args.chain_id, args.service_name, args.require_nonzero_root)
        print_json(result)
        return 0 if result.get("ok") else 2
    elif args.command == "set-role":
        print_json(set_role(args.chain_id, args.service_name, args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
