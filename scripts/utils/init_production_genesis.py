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
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the blockchain node src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps/blockchain-node/src"))

from aitbc_chain.database import init_db, session_scope
from aitbc_chain.mempool import init_mempool
from aitbc_chain.models import Account, Block
from sqlmodel import select


def _derive_address(name: str) -> str:
    """Return a deterministic EIP-55 0x address derived from `name`.

    This is only a fallback for local/dev use when no ``genesis_prod.yaml`` is
    supplied. Production deployments should always provide a ``genesis_prod.yaml``
    created by ``setup_production.py`` so that real, securely-generated keys are
    used.
    """
    from eth_account import Account

    return Account.from_key(hashlib.sha256(name.encode()).digest()).address


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
        # Fallback deterministic 0x addresses derived from the legacy names.
        # Do not use this for production; run setup_production.py first.
        return {
            _derive_address("aitbc1genesis"): 10_000_000,
            _derive_address("aitbc1treasury"): 5_000_000,
            _derive_address("aitbc1aiengine"): 2_000_000,
            _derive_address("aitbc1surveillance"): 1_500_000,
            _derive_address("aitbc1analytics"): 1_000_000,
            _derive_address("aitbc1marketplace"): 2_000_000,
            _derive_address("aitbc1enterprise"): 3_000_000,
            _derive_address("aitbc1multimodal"): 1_500_000,
            _derive_address("aitbc1zkproofs"): 1_000_000,
            _derive_address("aitbc1crosschain"): 2_000_000,
            _derive_address("aitbc1developer1"): 500_000,
            _derive_address("aitbc1developer2"): 300_000,
            _derive_address("aitbc1tester"): 200_000,
        }


def compute_genesis_hash(chain_id: str, timestamp: datetime) -> str:
    payload = f"{chain_id}|0|0x00|{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def ensure_genesis_block(chain_id: str, proposer: str) -> Block:
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
            proposer=proposer,
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
        )
        session.add(genesis)
        session.commit()
        print(f"[+] Created genesis block: height=0, hash={block_hash}")
        return genesis


def seed_accounts(chain_id: str, allocations: dict[str, int]) -> None:
    with session_scope() as session:
        for address, balance in allocations.items():
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

    allocations = load_allocations()
    proposer = next(iter(allocations)) if allocations else _derive_address("aitbc1genesis")

    # Create genesis block
    ensure_genesis_block(args.chain_id, proposer)

    # Seed accounts
    seed_accounts(args.chain_id, allocations)

    print("\n[+] Production genesis initialization complete.")
    print("[!] Next steps:")
    print("    1) Generate keystores for the genesis and treasury accounts.")
    print(f"    2) Update .env with CHAIN_ID={args.chain_id} and PROPOSER_KEY=<private key of the genesis account>")
    print("    3) Restart the blockchain node.")


if __name__ == "__main__":
    main()
