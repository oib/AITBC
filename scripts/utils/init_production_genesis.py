#!/usr/bin/env python3
"""
Initialize the production chain (ait-mainnet) with genesis allocations.
This script:
- Ensures the blockchain database is initialized
- Creates the genesis block (if missing)
- Populates account balances according to the production allocation
- Outputs the addresses and their balances
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Add the blockchain node src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps/blockchain-node/src"))

from aitbc_chain.config import settings as cfg
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.models import Block, Account
from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig
from aitbc_chain.mempool import init_mempool
import hashlib
from sqlmodel import select

# Production allocations (loaded from genesis_prod.yaml if available, else fallback)
ALLOCATIONS = {}


def load_allocations() -> dict[str, int]:
    yaml_path = Path("/opt/aitbc/genesis_prod.yaml")
    if yaml_path.exists():
        import yaml
        with yaml_path.open() as f:
            data = yaml.safe_load(f)
        allocations = {}
        for acc in data.get("genesis", {}).get("accounts", []):
            addr = acc["address"]
            balance = int(acc["balance"])
            allocations[addr] = balance
        return allocations
    else:
        # Fallback hardcoded
        return {
            "aitbc1genesis": 10_000_000,
            "aitbc1treasury": 5_000_000,
            "aitbc1aiengine": 2_000_000,
            "aitbc1surveillance": 1_500_000,
            "aitbc1analytics": 1_000_000,
            "aitbc1marketplace": 2_000_000,
            "aitbc1enterprise": 3_000_000,
            "aitbc1multimodal": 1_500_000,
            "aitbc1zkproofs": 1_000_000,
            "aitbc1crosschain": 2_000_000,
            "aitbc1developer1": 500_000,
            "aitbc1developer2": 300_000,
            "aitbc1tester": 200_000,
        }

ALLOCATIONS = load_allocations()

# Authorities (proposers) for PoA
AUTHORITIES = ["aitbc1genesis"]


def compute_genesis_hash(chain_id: str, timestamp: datetime) -> str:
    payload = f"{chain_id}|0|0x00|{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def ensure_genesis_block(chain_id: str) -> Block:
    with session_scope() as session:
        # Check if any block exists for this chain
        head = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()
        if head is not None:
            print(f"[*] Chain already has block at height {head.height}")
            return head

        # Create deterministic genesis timestamp
        timestamp = datetime(2025, 1, 1, 0, 0, 0)
        block_hash = compute_genesis_hash(chain_id, timestamp)
        genesis = Block(
            chain_id=chain_id,
            height=0,
            hash=block_hash,
            parent_hash="0x00",
            proposer="genesis",
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
        )
        session.add(genesis)
        session.commit()
        print(f"[+] Created genesis block: height=0, hash={block_hash}")
        return genesis


def seed_accounts(chain_id: str) -> None:
    with session_scope() as session:
        for address, balance in ALLOCATIONS.items():
            account = session.get(Account, (chain_id, address))
            if account is None:
                account = Account(chain_id=chain_id, address=address, balance=balance, nonce=0)
                session.add(account)
                print(f"[+] Created account {address} with balance {balance}")
            else:
                # Already exists; ensure balance matches if we want to enforce
                if account.balance != balance:
                    account.balance = balance
                    print(f"[~] Updated account {address} balance to {balance}")
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID to initialize")
    parser.add_argument("--db-path", type=Path, help="Path to SQLite database (overrides config)")
    args = parser.parse_args()

    # Override environment for config
    os.environ["CHAIN_ID"] = args.chain_id
    if args.db_path:
        os.environ["DB_PATH"] = str(args.db_path)

    from aitbc_chain.config import ChainSettings
    settings = ChainSettings()

    print(f"[*] Initializing database at {settings.db_path}")
    init_db()
    print("[*] Database initialized")

    # Ensure mempool DB exists (though not needed for genesis)
    mempool_path = settings.db_path.parent / "mempool.db"
    mempool_url = f"sqlite:///{mempool_path}"
    init_mempool(backend="database", db_url=mempool_url, max_size=10000, min_fee=0)
    print(f"[*] Mempool initialized at {mempool_path}")

    # Create genesis block
    ensure_genesis_block(args.chain_id)

    # Seed accounts
    seed_accounts(args.chain_id)

    print("\n[+] Production genesis initialization complete.")
    print(f"[!] Next steps:")
    print(f"    1) Generate keystore for aitbc1genesis and aitbc1treasury using scripts/keystore.py")
    print(f"    2) Update .env with CHAIN_ID={args.chain_id} and PROPOSER_KEY=<private key of aitbc1genesis>")
    print(f"    3) Restart the blockchain node.")


if __name__ == "__main__":
    main()
