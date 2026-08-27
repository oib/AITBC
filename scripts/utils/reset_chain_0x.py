#!/usr/bin/env python3
"""Reset the AITBC chain for the canonical 0x address migration.

This is an operational helper. Run it on the proposer/hub node after migrating
environment and wallet files to 0x addresses. It backs up the existing chain
data, creates a fresh genesis block and allocations, computes the state root,
and writes a `genesis.json` that followers can bootstrap from.

Typical usage from the repo root:

    CHAIN_ID=ait-hub.aitbc.bubuit.net DB_PATH=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
    PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/blockchain-node/src \
    python3 scripts/utils/reset_chain_0x.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, UTC
from pathlib import Path

import yaml
from eth_account import Account as EthAccount

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "blockchain-node" / "src"))

from aitbc_chain.config import ChainSettings
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.base_models import Account, Block
from aitbc_chain.state.state_root_utils import compute_state_root_full


def _derive_address(name: str) -> str:
    return EthAccount.from_key(hashlib.sha256(name.encode()).digest()).address


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _wallet_addresses(wallet_dir: Path) -> set[str]:
    addrs: set[str] = set()
    for p in wallet_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text())
            addr = data.get("address")
            if addr:
                addrs.add(str(addr))
        except Exception:
            pass
    return addrs


def _compute_genesis_hash(chain_id: str, timestamp: datetime) -> str:
    payload = f"{chain_id}|0|0x00|{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def main() -> int:
    chain_id = os.environ.get("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
    db_path = Path(os.environ.get("DB_PATH", f"/var/lib/aitbc/data/{chain_id}/chain.db"))
    data_dir = db_path.parent
    genesis_json = data_dir / "genesis.json"

    node_env = _load_env(Path("/etc/aitbc/node.env"))
    blockchain_env = _load_env(Path("/etc/aitbc/blockchain.env"))
    genesis_address = node_env.get("GENESIS_ADDRESS") or blockchain_env.get("GENESIS_WALLET_ADDRESS") or ""

    if not genesis_address:
        print("[!] GENESIS_ADDRESS not found in env", file=sys.stderr)
        return 1

    wallets = _wallet_addresses(Path("/var/lib/aitbc/wallets"))
    wallets.discard(genesis_address)

    allocations: list[dict[str, object]] = [{"address": genesis_address, "balance": 3_600_000_000_000, "nonce": 0}]
    for addr in sorted(wallets):
        allocations.append({"address": addr, "balance": 3_600_000_000, "nonce": 0})
    for name in [
        "aitbc1aiengine",
        "aitbc1surveillance",
        "aitbc1analytics",
        "aitbc1marketplace",
        "aitbc1enterprise",
        "aitbc1multimodal",
        "aitbc1zkproofs",
        "aitbc1crosschain",
        "aitbc1developer1",
        "aitbc1developer2",
        "aitbc1tester",
    ]:
        allocations.append({"address": _derive_address(name), "balance": 1_000_000, "nonce": 0})

    if data_dir.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup = data_dir.with_name(f"{data_dir.name}-pre-0x-migration-{ts}")
        shutil.move(str(data_dir), str(backup))
        print(f"[+] Backed up old chain to {backup}")

    data_dir.mkdir(parents=True, exist_ok=True)

    genesis_prod = Path("/opt/aitbc/genesis_prod.yaml")
    genesis_prod.write_text(yaml.safe_dump({"genesis": {"accounts": allocations}}, sort_keys=False))
    os.chmod(genesis_prod, 0o600)
    print(f"[+] Wrote {genesis_prod}")

    os.environ["CHAIN_ID"] = chain_id
    os.environ["DB_PATH"] = str(db_path)
    settings = ChainSettings()
    print(f"[*] DB path: {settings.db_path}")

    init_db()
    print("[+] Database initialized")

    from sqlmodel import select

    timestamp = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    block_hash = _compute_genesis_hash(chain_id, timestamp)

    with session_scope() as session:
        for alloc in allocations:
            session.add(
                Account(
                    chain_id=chain_id,
                    address=alloc["address"],
                    balance=alloc["balance"],
                    nonce=0,
                )
            )
        session.add(
            Block(
                chain_id=chain_id,
                height=0,
                hash=block_hash,
                parent_hash="0x00",
                proposer=genesis_address,
                timestamp=timestamp,
                tx_count=0,
                state_root=None,
            )
        )
        session.commit()
        print(f"[+] Created block 0: {block_hash}")

    with session_scope() as session:
        state_root = compute_state_root_full(session, chain_id)
        if not state_root:
            print("[!] Failed to compute state root", file=sys.stderr)
            return 1
        block = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == 0)).one()
        block.state_root = state_root
        session.add(block)
        session.commit()
        print(f"[+] State root: {state_root}")

    genesis_data = {
        "chain_id": chain_id,
        "block": {
            "height": 0,
            "hash": block_hash,
            "parent_hash": "0x00",
            "proposer": "genesis",
            "timestamp": timestamp.isoformat(),
            "tx_count": 0,
            "chain_id": chain_id,
            "state_root": state_root,
            "metadata": {
                "chain_type": "mainnet",
                "purpose": "production",
                "consensus_algorithm": "poa",
            },
        },
        "allocations": allocations,
    }
    genesis_json.write_text(json.dumps(genesis_data, indent=2))
    os.chmod(genesis_json, 0o644)
    print(f"[+] Wrote {genesis_json}")
    print("[+] Done. Start the blockchain node to begin block production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
