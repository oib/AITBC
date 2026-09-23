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

# Add the blockchain node src to path. resolve() first: parent.parent of a bare
# __file__ is scripts/, and scripts/apps/blockchain-node/src does not exist, so
# aitbc_chain below failed to import at all.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/blockchain-node/src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aitbc.utils.genesis_accounts import derive_address, derived_key_error, find_derived
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.mempool import init_mempool
from aitbc_chain.models import Account, Block
from sqlmodel import select


GENESIS_PROD_YAML = Path("/opt/aitbc/genesis_prod.yaml")

ALLOW_DERIVED_FLAG = "--allow-derived-keys"


def _derived_fallback() -> dict[str, int]:
    """Allocations at sha256(name) addresses. Disposable local chains only.

    Every private key here is computable from this file. Reachable only behind
    an explicit opt-in; see load_allocations().
    """
    return {
        derive_address("aitbc1genesis"): 10_000_000,
        derive_address("aitbc1treasury"): 5_000_000,
        derive_address("aitbc1aiengine"): 2_000_000,
        derive_address("aitbc1surveillance"): 1_500_000,
        derive_address("aitbc1analytics"): 1_000_000,
        derive_address("aitbc1market"): 2_000_000,
        derive_address("aitbc1enterprise"): 3_000_000,
        derive_address("aitbc1multimodal"): 1_500_000,
        derive_address("aitbc1zkproofs"): 1_000_000,
        derive_address("aitbc1crosschain"): 2_000_000,
        derive_address("aitbc1developer1"): 500_000,
        derive_address("aitbc1developer2"): 300_000,
        derive_address("aitbc1tester"): 200_000,
    }


def load_allocations(allow_derived: bool = False) -> dict[str, int]:
    """Load the genesis allocation set, refusing publicly-derivable addresses.

    A missing genesis_prod.yaml used to fall through to _derived_fallback()
    silently, so a production run that had lost its allocation file looked
    exactly like a correct one and seeded the chain with keys anyone could
    compute. Both that path and a yaml that already contains such an address are
    now hard failures unless the caller opts in.
    """
    if GENESIS_PROD_YAML.exists():
        import yaml

        with GENESIS_PROD_YAML.open() as f:
            data = yaml.safe_load(f)
        allocations = {}
        for acc in data.get("genesis", {}).get("accounts", []):
            addr = acc["address"]
            balance = int(acc["balance"])
            allocations[addr] = balance
        if not allocations:
            sys.exit(f"[!] {GENESIS_PROD_YAML} has no genesis.accounts entries; refusing to seed an empty chain.")
    else:
        if not allow_derived:
            sys.exit(
                f"[!] {GENESIS_PROD_YAML} not found, and the derived-address fallback is not a\n"
                f"    production allocation set -- its private keys are public. Run\n"
                f"    scripts/utils/setup_production.py to generate real keys, or pass\n"
                f"    {ALLOW_DERIVED_FLAG} for a disposable local chain."
            )
        print(f"[!] {GENESIS_PROD_YAML} not found; using derived addresses ({ALLOW_DERIVED_FLAG}).")
        print("[!] Every private key in this allocation set is public. Local chains only.")
        allocations = _derived_fallback()

    derived = find_derived(allocations)
    if derived and not allow_derived:
        sys.exit("[!] " + derived_key_error(derived, override=ALLOW_DERIVED_FLAG))
    return allocations


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
    parser.add_argument(
        ALLOW_DERIVED_FLAG,
        action="store_true",
        help="Permit allocations at sha256(name) addresses whose private keys are public. Local chains only.",
    )
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

    allocations = load_allocations(allow_derived=args.allow_derived_keys)
    proposer = next(iter(allocations))

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
