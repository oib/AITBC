"""Operational genesis reset helpers for the AITBC CLI.

This is intentionally separate from the read-only ``genesis.py`` commands so
that the destructive reset logic is isolated and can be reviewed independently.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
from eth_account import Account
from eth_keys import keys

from . import error, output, success

DEFAULT_CHAIN_ID = "ait-hub.aitbc.bubuit.net"
DEFAULT_DATA_DIR = Path("/var/lib/aitbc/data")
DEFAULT_WALLET_DIR = Path("/var/lib/aitbc/wallets")
DEFAULT_ETC_DIR = Path("/etc/aitbc")
DEFAULT_BACKUP_ROOT = Path("/root")


SERVICE_UNITS = [
    "aitbc-blockchain-node",
    "aitbc-blockchain-rpc",
    "aitbc-blockchain-p2p",
    "aitbc-wallet",
]


def _now_str() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _replace_or_append(path: Path, name: str, value: str, perms: int = 0o600) -> None:
    text = path.read_text() if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(name)}=.*$", re.MULTILINE)
    line = f"{name}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    path.write_text(text)
    os.chmod(path, perms)


def _chown_aitbc(path: Path) -> None:
    for user, group in [("aitbc", "aitbc"), ("root", "root")]:
        try:
            shutil.chown(path, user, group)
            return
        except Exception:
            continue


def _generate_strong_password(length: int = 32) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*-"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*-" for c in password)
        ):
            return password


def _ensure_wallet_import_password(env_path: Path, provided: str | None = None) -> str:
    env = _load_env(env_path)
    if provided:
        _replace_or_append(env_path, "WALLET_IMPORT_PASSWORD", provided)
        return provided
    current = env.get("WALLET_IMPORT_PASSWORD", "")
    if (
        len(current) >= 12
        and re.search(r"[A-Z]", current)
        and re.search(r"[a-z]", current)
        and re.search(r"\d", current)
        and re.search(r"[^A-Za-z0-9]", current)
    ):
        return current
    password = _generate_strong_password()
    _replace_or_append(env_path, "WALLET_IMPORT_PASSWORD", password)
    return password


def _write_default_wallet(wallet_dir: Path, address: str, public_key: str, private_key_hex: str, chain_id: str) -> Path:
    wallet_dir.mkdir(parents=True, exist_ok=True)
    wallet_path = wallet_dir / "default.json"
    wallet = {
        "wallet_id": "default",
        "type": "simple",
        "address": address,
        "public_key": public_key,
        "private_key": f"0x{private_key_hex}",
        "chain_id": chain_id,
        "created_at": datetime.now(UTC).isoformat() + "Z",
        "balance": 0,
        "transactions": [],
    }
    wallet_path.write_text(json.dumps(wallet, indent=2))
    os.chmod(wallet_path, 0o640)
    _chown_aitbc(wallet_path)
    return wallet_path


def _run_subprocess(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        env=merged_env,
    )


def _stop_services() -> None:
    for unit in SERVICE_UNITS:
        try:
            _run_subprocess(["systemctl", "stop", unit], check=False)
        except Exception:
            pass


def _start_services() -> None:
    for unit in SERVICE_UNITS:
        try:
            _run_subprocess(["systemctl", "start", unit], check=False)
        except Exception:
            pass


def _service_status() -> dict[str, str]:
    status: dict[str, str] = {}
    for unit in SERVICE_UNITS:
        try:
            r = _run_subprocess(["systemctl", "is-active", unit], check=False)
            status[unit] = r.stdout.strip() if r.stdout else "unknown"
        except Exception:
            status[unit] = "unknown"
    return status


def _generate_wallet(
    etc_dir: Path,
    wallet_dir: Path,
    chain_id: str,
    wallet_password: str | None = None,
) -> tuple[str, str]:
    account = Account.create()
    private_key_hex = account.key.hex()
    address = account.address
    public_key_hex = keys.PrivateKey(bytes(account.key)).public_key.to_hex()

    env_files = {
        "node": etc_dir / "node.env",
        "blockchain": etc_dir / "blockchain.env",
        "blockchain_secrets": etc_dir / "blockchain-secrets.env",
        "validator_secrets": etc_dir / "validator-secrets.env",
        "aitbc_blockchain_node": etc_dir / "aitbc-blockchain-node.env",
        "bridge_validator_keys": etc_dir / "bridge-validator-keys.env",
    }

    # Private key: keep in the secrets file and in node.env (wallet daemon reads node.env).
    _replace_or_append(env_files["node"], "GENESIS_PRIVATE_KEY", private_key_hex)
    _replace_or_append(env_files["blockchain_secrets"], "GENESIS_PRIVATE_KEY", private_key_hex)

    # Address/public config.
    _replace_or_append(env_files["node"], "GENESIS_ADDRESS", address)
    _replace_or_append(env_files["blockchain"], "GENESIS_WALLET_ADDRESS", address)

    # Proposer identity.
    _replace_or_append(env_files["node"], "PROPOSER_ID", address)
    _replace_or_append(env_files["blockchain"], "PROPOSER_ID", address)
    _replace_or_append(env_files["aitbc_blockchain_node"], "PROPOSER_ID", address)
    _replace_or_append(env_files["validator_secrets"], "PROPOSER_KEY", f"0x{private_key_hex}")
    _replace_or_append(env_files["bridge_validator_keys"], "PROPOSER_KEY", f"0x{private_key_hex}")

    # Single-proposer validator set for the new chain.
    validator_set = f'[{{"address":"{address}","stake":"1000"}}]'
    for key in ("node", "blockchain", "aitbc_blockchain_node"):
        _replace_or_append(env_files[key], "VALIDATOR_SET", validator_set)

    # Wallet import password (wallet daemon auto-import needs this).
    _ensure_wallet_import_password(env_files["blockchain_secrets"], wallet_password)

    # Write a default file wallet so the CLI active wallet is the new genesis.
    _write_default_wallet(wallet_dir, address, public_key_hex, private_key_hex, chain_id)

    # Ownership: env files should be readable by aitbc services but not world.
    for path in env_files.values():
        if path.exists():
            os.chmod(path, 0o600)
            _chown_aitbc(path)

    return address, public_key_hex


def reset_genesis(
    chain_id: str | None,
    new_wallet: bool,
    password: str | None,
    yes: bool,
    output_format: str,
    data_dir: Path | None = None,
    etc_dir: Path | None = None,
    wallet_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Reset the local chain with a new genesis block and optional new wallet.

    This is a destructive operation: it stops services, backs up the old chain
    data, and rewrites the genesis block.  The caller is responsible for any
    confirmation prompts; ``yes`` only suppresses internal safety checks here.
    """
    if not chain_id:
        chain_id = os.environ.get("CHAIN_ID", DEFAULT_CHAIN_ID)

    data_dir = data_dir or DEFAULT_DATA_DIR
    etc_dir = etc_dir or DEFAULT_ETC_DIR
    wallet_dir = wallet_dir or DEFAULT_WALLET_DIR

    db_path = data_dir / chain_id / "chain.db"
    reset_script = _repo_root() / "scripts" / "utils" / "reset_chain_0x.py"

    if not reset_script.exists():
        error(f"Reset script not found: {reset_script}")
        return None

    backup_root = DEFAULT_BACKUP_ROOT / f"aitbc-genesis-reset-{_now_str()}"
    backup_root.mkdir(parents=True, exist_ok=True)

    success(f"Stopping AITBC services for chain {chain_id}...")
    _stop_services()

    # Clear the wallet daemon DB so it re-imports from env/files on restart.
    wallet_db = Path("/var/lib/aitbc/data/wallet_ledger.db")
    keystore_db = Path("/var/lib/aitbc/data/keystore.db")
    for db in (wallet_db, keystore_db):
        try:
            if db.exists():
                db.unlink()
                success(f"Cleared old wallet daemon DB: {db}")
        except Exception:
            pass

    # Back up env.
    env_backup = backup_root / "etc-aitbc"
    if etc_dir.exists():
        shutil.copytree(etc_dir, env_backup, dirs_exist_ok=True)
        success(f"Backed up env to {env_backup}")

    # Generate or load wallet.
    if new_wallet:
        success("Generating new genesis wallet...")
        address, public_key = _generate_wallet(etc_dir, wallet_dir, chain_id, password)
        success(f"New genesis wallet: {address}")
    else:
        env = _load_env(etc_dir / "node.env")
        address = env.get("GENESIS_ADDRESS") or _load_env(etc_dir / "blockchain.env").get("GENESIS_WALLET_ADDRESS", "")
        if not address:
            error("GENESIS_ADDRESS not set and --new-wallet not given. Use --new-wallet to generate one.")
            _start_services()
            return None
        public_key = ""
        _ensure_wallet_import_password(etc_dir / "blockchain-secrets.env", password)

    # Run the genesis reset script.
    success("Running genesis reset script...")
    env_override = {
        "CHAIN_ID": chain_id,
        "DB_PATH": str(db_path),
    }
    try:
        r = _run_subprocess([sys.executable, str(reset_script)], env=env_override)
        if r.returncode != 0:
            error(f"reset_chain_0x.py failed:\n{r.stderr}")
            _start_services()
            return None
        if r.stdout:
            success(r.stdout)
    except Exception as e:
        error(f"Failed to run reset script: {e}")
        _start_services()
        return None

    # Fix ownership of the new chain DB so the aitbc user can write it.
    chain_data_dir = db_path.parent
    try:
        for item in chain_data_dir.rglob("*"):
            _chown_aitbc(item)
        _chown_aitbc(chain_data_dir)
    except Exception:
        pass

    # Restart services.
    success("Restarting services...")
    _start_services()
    time.sleep(3)

    status = _service_status()
    return {
        "chain_id": chain_id,
        "genesis_address": address,
        "public_key": public_key[:16] + "..." if public_key else None,
        "data_dir": str(chain_data_dir),
        "backup_dir": str(backup_root),
        "service_status": status,
    }
